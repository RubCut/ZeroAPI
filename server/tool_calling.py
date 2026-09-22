"""
Tool (function) calling support for ZeroAPI.

Browser chat pages (chat.deepseek.com, chatgpt.com, ...) have no native function
calling, so ZeroAPI emulates the OpenAI tool protocol in three steps:

1. ``build_tool_instructions()`` injects a compact tool spec + call format into
   the prompt that is typed into the browser chat.
2. ``parse_tool_calls()`` reads the model's plain-text answer, extracts the
   tool call(s) it wrote (several shapes are accepted) and converts them into
   OpenAI ``tool_calls`` objects.
3. Tool results sent back by the client as ``role="tool"`` messages are folded
   back into the next prompt by ``server.main.messages_to_prompt_and_files``.

Because the raw tool JSON must never leak to the API client as message content,
``ToolCallStreamFilter`` holds back any text that may be the start of a tool
call while streaming and releases it only if the finished answer turns out to
be regular prose.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ── Call envelope markers ────────────────────────────────────────────────────
# Every shape we can recognise. The first one is what we teach the model to use.
TAG_OPEN = "<tool_call>"
TAG_CLOSE = "</tool_call>"

MCP_OPEN = "###mcp_tool###"
MCP_CLOSE_RE = re.compile(r"###\s*end[_-]?mcp[_-]?tool\s*###", re.I)

# Markers whose appearance means "a tool call may start here" (used by the
# streaming filter). Order does not matter.
HOLD_MARKERS: Tuple[str, ...] = (
    TAG_OPEN,
    MCP_OPEN,
    "```json",
    "```tool_call",
    "```toolcall",
    "```function",
    "```tools",
    "<|tool_call|>",
    "<\uff5ctool\u2581call",  # DeepSeek DSML: <｜tool▁call▁begin｜>
    "<dsml",
)

_FENCE_RE = re.compile(
    r"```[ \t]*(?:jsonc?|tool[_-]?call|tool|function|tools)?[ \t]*\r?\n(?P<body>.*?)```",
    re.S | re.I,
)
_TAG_RE = re.compile(re.escape(TAG_OPEN) + r"\s*(?P<body>.*?)\s*" + re.escape(TAG_CLOSE), re.S)
_PIPE_TAG_RE = re.compile(r"<\|tool_call\|>\s*(?P<body>.*?)\s*<\|/tool_call\|>", re.S)
_MCP_RE = re.compile(re.escape(MCP_OPEN) + r"\s*(?P<body>.*?)\s*(?:" + MCP_CLOSE_RE.pattern + r"|$)", re.S)
# DeepSeek DSML: <｜tool▁call▁begin｜>function<｜tool▁sep｜>name ... json ... <｜tool▁call▁end｜>
_DSML_RE = re.compile(
    r"<\uff5ctool\u2581call\u2581begin\uff5c>.*?(?:<\uff5ctool\u2581sep\uff5c>|function)\s*"
    r"(?P<name>[A-Za-z0-9_.\-]+)(?P<body>.*?)(?:<\uff5ctool\u2581call\u2581end\uff5c>|$)",
    re.S,
)

_CALL_NAME_KEYS = ("name", "tool", "tool_name", "toolname", "function_name", "recipient_name")
_CALL_ARG_KEYS = ("arguments", "parameters", "args", "input", "params", "tool_input")


def make_call_id() -> str:
    """Unique id for a generated tool call (OpenAI uses ``call_`` + 24 chars)."""
    return f"call_{uuid.uuid4().hex[:24]}"


# ── Tool spec helpers ────────────────────────────────────────────────────────


def normalize_tool_specs(tools: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Flatten OpenAI tool definitions into ``[{name, description, parameters}]``."""
    out: List[Dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = fn.get("name") or tool.get("name")
        if not name:
            continue
        params = fn.get("parameters") or fn.get("input_schema") or tool.get("parameters") or {}
        if not isinstance(params, dict):
            params = {}
        out.append(
            {
                "name": str(name),
                "description": str(fn.get("description") or tool.get("description") or ""),
                "parameters": params,
            }
        )
    return out


def tool_names(tools: Optional[Sequence[Dict[str, Any]]]) -> List[str]:
    return [t["name"] for t in normalize_tool_specs(tools)]


def tool_choice_mode(tool_choice: Any) -> Tuple[str, Optional[str]]:
    """Return ``(mode, forced_name)`` where mode is none|auto|required|function."""
    if tool_choice is None:
        return "auto", None
    if isinstance(tool_choice, str):
        tc = tool_choice.lower()
        if tc in ("none", "auto", "required"):
            return tc, None
        return ("function", tool_choice) if tc else ("auto", None)
    if isinstance(tool_choice, dict):
        fn = tool_choice.get("function") if isinstance(tool_choice.get("function"), dict) else tool_choice
        name = fn.get("name")
        t = str(tool_choice.get("type") or "function").lower()
        if name:
            return "function", str(name)
        return t if t else "auto", None
    return "auto", None


def _render_schema(params: Dict[str, Any]) -> str:
    try:
        return json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "{}"


def build_tool_instructions(
    tools: Optional[Sequence[Dict[str, Any]]],
    tool_choice: Any = None,
    parallel_tool_calls: Optional[bool] = None,
) -> str:
    """System-prompt block that teaches the browser model how to call tools."""
    specs = normalize_tool_specs(tools)
    if not specs:
        return ""
    mode, forced = tool_choice_mode(tool_choice)

    lines: List[str] = ["[System Instructions]: You are connected to an API client that can execute tools for you."]
    lines.append("")
    lines.append("TOOLS AVAILABLE:")
    for spec in specs:
        desc = " ".join(spec["description"].split())
        lines.append(f"- {spec['name']}: {desc}" if desc else f"- {spec['name']}")
        lines.append(f"  arguments schema: {_render_schema(spec['parameters'])}")
    lines.append("")
    lines.append("HOW TO CALL A TOOL")
    lines.append("Answer with one fenced json block per call, exactly in this shape:")
    lines.append("")
    lines.append("```json")
    lines.append('{"name": "<tool name>", "arguments": {<arguments object>}}')
    lines.append("```")
    lines.append("")
    lines.append("RULES:")
    lines.append("- `arguments` must follow the tool's schema. Never invent parameter names.")
    lines.append("- Write any short explanation BEFORE the json block, never inside it.")
    lines.append("- Several json blocks in one answer = several tool calls (parallel calls).")
    lines.append("- A reply that contains a json tool block is NOT sent to the user as a final answer: the tool is executed and you get a [Tool result] message back. Then continue the task.")
    lines.append("- Never repeat a tool call whose result you already received; use the result instead.")
    if parallel_tool_calls is False:
        lines.append("- Call only ONE tool per answer.")
    if mode == "required":
        lines.append("- You MUST call one of the tools now, even if you think you already know the answer.")
    elif mode == "function" and forced:
        lines.append(f"- You MUST call the tool `{forced}` now.")
    else:
        lines.append("- If no tool is needed, just answer normally with no json tool block.")
    return "\n".join(lines)


# ── Parsing ──────────────────────────────────────────────────────────────────


def _match_name(name: str, known: Sequence[str]) -> Optional[str]:
    """Resolve a model-written tool name against the client's tool list."""
    if not name:
        return None
    raw = str(name).strip().strip("\"'`")
    if raw.lower().startswith("functions."):
        raw = raw.split(".", 1)[1]
    if not known:
        return raw
    lowered = {k.lower(): k for k in known}
    if raw in known:
        return raw
    if raw.lower() in lowered:
        return lowered[raw.lower()]
    # tolerate namespaced / suffixed names such as "bash_tool" or "fs/read"
    for key, original in lowered.items():
        if raw.lower() in (key.split("/")[-1], key.split(".")[-1]) or key.endswith("." + raw.lower()):
            return original
    return None


def _normalize_arguments(args: Any) -> str:
    """Return a JSON string, as required by the OpenAI wire format."""
    if args is None:
        return "{}"
    if isinstance(args, str):
        text = args.strip()
        if not text:
            return "{}"
        try:
            parsed = json.loads(text)
        except Exception:
            return json.dumps({"input": args}, ensure_ascii=False)
        return json.dumps(parsed, ensure_ascii=False)
    try:
        return json.dumps(args, ensure_ascii=False)
    except Exception:
        return json.dumps({"input": str(args)}, ensure_ascii=False)


def _split_payload(payload: Any) -> List[Any]:
    """A payload may be one call, a list of calls, or a wrapper around them."""
    if isinstance(payload, list):
        out: List[Any] = []
        for item in payload:
            out.extend(_split_payload(item))
        return out
    if isinstance(payload, dict):
        for key in ("tool_calls", "calls", "tools"):
            inner = payload.get(key)
            if isinstance(inner, list) and inner:
                return _split_payload(inner)
    return [payload]


def _normalize_call(payload: Any, known: Sequence[str]) -> Optional[Dict[str, Any]]:
    """Convert one candidate object into an OpenAI tool_call dict."""
    if not isinstance(payload, dict):
        return None
    name = None
    args: Any = None
    fn = payload.get("function")
    if isinstance(fn, dict):
        name = fn.get("name") or fn.get("tool")
        args = next((fn[k] for k in _CALL_ARG_KEYS if k in fn), None)
    elif isinstance(fn, str):
        name = fn
        args = next((payload[k] for k in _CALL_ARG_KEYS if k in payload), None)
    if name is None:
        for key in _CALL_NAME_KEYS:
            if key in payload and isinstance(payload[key], str):
                name = payload[key]
                break
    if name is None and len(payload) == 1:
        # {"bash": {"cmd": "ls"}} style
        k, v = next(iter(payload.items()))
        if isinstance(v, (dict, list, str)):
            name, args = k, v
    if name is None:
        return None
    if args is None:
        args = next((payload[k] for k in _CALL_ARG_KEYS if k in payload), None)
    resolved = _match_name(str(name), known)
    if resolved is None:
        return None
    return {
        "id": payload.get("id") if isinstance(payload.get("id"), str) else make_call_id(),
        "type": "function",
        "function": {"name": resolved, "arguments": _normalize_arguments(args)},
    }


def _json_from_text(text: str) -> List[Any]:
    """Parse ``text`` as JSON, or dig the first balanced JSON value out of it."""
    stripped = text.strip()
    if not stripped:
        return []
    # Drop a leading language hint / comment lines the model may add.
    cleaned = re.sub(r"^\s*(?:json|tool[_-]?call|function)\s*\n", "", stripped, flags=re.I)
    for candidate in (cleaned, stripped):
        try:
            return [json.loads(candidate)]
        except Exception:
            pass
    found = _find_balanced_json(stripped)
    if found is not None:
        return [found[0]]
    return []


def _find_balanced_json(text: str) -> Optional[Tuple[Any, int, int]]:
    """Return ``(value, start, end)`` of the first balanced JSON object/array."""
    for start, ch in enumerate(text):
        if ch not in "[{":
            continue
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
                if depth == 0:
                    chunk = text[start : i + 1]
                    try:
                        return json.loads(chunk), start, i + 1
                    except Exception:
                        break
    return None


@dataclass
class ToolParseResult:
    """Outcome of scanning a model answer for tool calls."""

    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw: str = ""

    @property
    def has_calls(self) -> bool:
        return bool(self.tool_calls)

    def message_content(self) -> Optional[str]:
        """``None`` when the answer is a pure tool call (matches OpenAI)."""
        return self.content if self.content else None


def parse_tool_calls(text: str, tools: Optional[Sequence[Dict[str, Any]]] = None) -> ToolParseResult:
    """Extract tool calls from a plain-text browser answer.

    Recognised shapes: ``<tool_call>{...}</tool_call>``, fenced ```json blocks,
    ``###mcp_tool### ... ###end_mcp_tool###``, ``<|tool_call|>``, DeepSeek DSML
    markup, and (as a last resort) a bare JSON object whose ``name`` matches one
    of the client's tools. Everything outside the call blocks becomes ``content``.
    """
    raw = text or ""
    known = tool_names(tools)
    calls: List[Dict[str, Any]] = []
    spans: List[Tuple[int, int]] = []

    def consume(body: str, span: Tuple[int, int]) -> None:
        added = False
        for payload in _json_from_text(body):
            for item in _split_payload(payload):
                call = _normalize_call(item, known)
                if call:
                    calls.append(call)
                    added = True
        if added:
            spans.append(span)

    for regex in (_TAG_RE, _PIPE_TAG_RE, _MCP_RE, _FENCE_RE):
        for match in regex.finditer(raw):
            span = match.span()
            if any(s <= span[0] < e or s < span[1] <= e for s, e in spans):
                continue
            consume(match.group("body"), span)

    if not calls:
        for match in _DSML_RE.finditer(raw):
            name = _match_name(match.group("name"), known)
            if not name:
                continue
            body = match.group("body")
            args: Any = {}
            found = _find_balanced_json(body)
            if found is not None:
                args = found[0]
            calls.append(
                {"id": make_call_id(), "type": "function", "function": {"name": name, "arguments": _normalize_arguments(args)}}
            )
            spans.append(match.span())

    if not calls:
        # No envelope: accept a bare JSON answer only when it is a real tool call.
        stripped = raw.strip()
        found = _find_balanced_json(stripped)
        if found is not None:
            value, start, end = found
            looks_bare = not stripped[:start].strip() and not stripped[end:].strip()
            for item in _split_payload(value):
                call = _normalize_call(item, known)
                if call and (looks_bare or known):
                    calls.append(call)
                    spans.append((raw.index(stripped) + start, raw.index(stripped) + end))

    if calls:
        first = min(s for s, _ in spans) if spans else len(raw)
        content = raw[:first]
    else:
        content = raw
    content = _tidy(content)
    return ToolParseResult(content=content, tool_calls=calls, raw=raw)


def _tidy(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text or "")
    return text.strip()


# ── Streaming helper ─────────────────────────────────────────────────────────


class ToolCallStreamFilter:
    """Emits prose while holding back anything that may be a tool call.

    Feed the *cumulative* answer text (``feed``), or deltas when the cumulative
    text is not available. Only text that cannot possibly belong to a tool call
    is released; the held tail is resolved by ``finish()``.
    """

    def __init__(self, tools: Optional[Sequence[Dict[str, Any]]] = None):
        self.tools = tools or []
        self.text = ""
        self.emitted = 0  # chars of parsed content already emitted
        self._search_from = 0

    # -- internals ---------------------------------------------------------
    def _hold_start(self) -> Optional[int]:
        """Index where a possible tool call starts, or ``None``."""
        best: Optional[int] = None
        window_start = max(0, self._search_from - max(len(m) for m in HOLD_MARKERS))
        for marker in HOLD_MARKERS:
            idx = self.text.find(marker, window_start)
            if idx >= 0 and (best is None or idx < best):
                best = idx
            # a partially-typed marker at the very end still counts as a hold
            for k in range(min(len(marker) - 1, len(self.text)), 0, -1):
                if self.text.endswith(marker[:k]):
                    candidate = len(self.text) - k
                    if candidate >= self.emitted and (best is None or candidate < best):
                        best = candidate
                    break
        return best

    # -- public API --------------------------------------------------------
    def feed(self, chunk: str) -> str:
        """Add newly arrived text, return the text safe to send as a delta."""
        if not chunk:
            return ""
        if chunk.startswith(self.text):
            self.text = chunk
        else:
            self.text += chunk
        hold = self._hold_start()
        end = len(self.text) if hold is None else hold
        if end > self.emitted:
            out = self.text[self.emitted : end]
            self._search_from = end
            self.emitted = end
            return out
        return ""

    def finish(self, final_text: Optional[str] = None) -> Tuple[str, ToolParseResult]:
        """Resolve the held tail.

        Returns ``(extra_content_delta, parse_result)``: the delta should be sent
        as a final content chunk when no tool call was found.
        """
        if final_text:
            if final_text.startswith(self.text):
                self.text = final_text
            elif len(final_text) > len(self.text):
                self.text = final_text
        parsed = parse_tool_calls(self.text, self.tools)
        if parsed.has_calls:
            content = parsed.content
            delta = content[len(self.text[: self.emitted]) :] if content.startswith(self.text[: self.emitted]) else ""
            return delta, parsed
        delta = self.text[self.emitted :]
        self.emitted = len(self.text)
        return delta, ToolParseResult(content=self.text, tool_calls=[], raw=self.text)


# ── Prompt rendering for tool history ────────────────────────────────────────


def render_assistant_tool_calls(tool_calls: Iterable[Dict[str, Any]]) -> str:
    """Textual form of a previous assistant tool call, for prompt re-injection."""
    lines = []
    for call in tool_calls or []:
        fn = call.get("function") if isinstance(call, dict) else None
        if not isinstance(fn, dict):
            continue
        lines.append(f"{fn.get('name')}({fn.get('arguments') or '{}'})")
    if not lines:
        return ""
    return "[Assistant requested tool calls]: " + "; ".join(lines)


def render_tool_result(name: Optional[str], content: str) -> str:
    label = f"[Tool result{': ' + name if name else ''}]"
    return f"{label} {content}"
