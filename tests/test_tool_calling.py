"""
ZeroAPI tool (function) calling tests.

They run the real FastAPI app, register a fake browser extension over the
WebSocket and check that:

* tool definitions reach the prompt typed into the "browser",
* a model answer with a tool call becomes proper OpenAI ``tool_calls``,
* streaming emits tool_call deltas with ``finish_reason="tool_calls"``,
* ``role="tool"`` results are folded back into the next prompt,
* plain answers still stream as normal content.

Run: python tests/test_tool_calling.py
"""
import asyncio
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from server.main import app
from server.tool_calling import ToolCallStreamFilter, build_tool_instructions, parse_tool_calls

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read a file",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    },
]


# ── Fake browser ─────────────────────────────────────────────────────────────


class FakeBrowser:
    """Minimal stand-in for the ZeroAPI extension background page."""

    def __init__(self, ws, replies):
        self.ws = ws
        self.replies = list(replies)
        self.prompts = []
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop:
            try:
                raw = self.ws.receive_text()
            except Exception:
                return
            msg = json.loads(raw)
            if msg.get("type") in ("register", "hello"):
                continue
            if msg.get("type") != "chat_request":
                continue
            self.prompts.append(msg.get("prompt", ""))
            answer = self.replies.pop(0) if self.replies else "no reply configured"
            if not msg.get("stream"):
                self.ws.send_text(json.dumps({"type": "chat_response", "id": msg["id"], "content": answer, "done": True}))
            else:
                step = 12
                for i in range(0, len(answer), step):
                    self.ws.send_text(json.dumps({
                        "type": "chat_chunk", "id": msg["id"], "delta": answer[: i + step], "content": answer[: i + step],
                    }))
                    time.sleep(0.01)
                self.ws.send_text(json.dumps({"type": "chat_done", "id": msg["id"], "content": answer, "done": True}))

    def close(self):
        self._stop = True


def register_browser(client, replies, provider="deepseek"):
    ws = client.websocket_connect("/ws").__enter__()
    ws.send_text(json.dumps({
        "type": "register",
        "client_id": f"test-{provider}-{int(time.time() * 1000) % 100000}",
        "provider": provider,
        "url": "https://chat.deepseek.com/",
        "providers": [provider],
        "version": "test",
    }))
    ws.receive_text()  # "registered"
    return ws, FakeBrowser(ws, replies)


# ── Unit level ───────────────────────────────────────────────────────────────


def test_parse_shapes():
    cases = [
        ('```json\n{"name": "bash", "arguments": {"command": "ls"}}\n```', "bash"),
        ('<tool_call>{"name": "read", "arguments": {"path": "a.py"}}</tool_call>', "read"),
        ('###mcp_tool### {"tool": "bash", "parameters": {"command": "pwd"}} ###end_mcp_tool###', "bash"),
        ('{"function": {"name": "read", "arguments": {"path": "x"}}}', "read"),
        ('Text first.\n```json\n{"name": "bash", "args": {"command": "id"}}\n```', "bash"),
        ('jsonCopyDownload({"name": "bash", "arguments": {"command": "pwd"}})', "bash"),
    ]
    for text, expected in cases:
        parsed = parse_tool_calls(text, TOOLS)
        assert parsed.has_calls, f"no calls parsed from {text!r}"
        assert parsed.tool_calls[0]["function"]["name"] == expected
    repeated = parse_tool_calls(
        'jsonCopyDownload({"name":"bash","arguments":{"command":"pwd"}})'
        'jsonCopyDownload({"name":"bash","arguments":{"command":"pwd"}})',
        TOOLS,
    )
    assert len(repeated.tool_calls) == 1
    print("✓ parser handles all tool-call shapes and deduplicates DOM repeats")

    # prose without a tool call stays prose
    parsed = parse_tool_calls("Nothing to run here, all done.", TOOLS)
    assert not parsed.has_calls
    # unknown tool names are not turned into calls
    parsed = parse_tool_calls('```json\n{"name": "not_a_tool", "arguments": {}}\n```', TOOLS)
    assert not parsed.has_calls, "unknown tool must not become a tool call"
    print("✓ parser ignores prose and unknown tool names")

    # arguments are always valid JSON strings
    parsed = parse_tool_calls('```json\n{"name": "bash", "arguments": {"command": "ls"}}\n```', TOOLS)
    assert json.loads(parsed.tool_calls[0]["function"]["arguments"]) == {"command": "ls"}
    parsed = parse_tool_calls('{"name": "bash", "arguments": "not json"}', TOOLS)
    assert json.loads(parsed.tool_calls[0]["function"]["arguments"]) == {"input": "not json"}
    print("✓ tool call arguments are JSON strings")


def test_stream_filter_holds_tool_calls():
    text = 'Let me check.\n```json\n{"name": "bash", "arguments": {"command": "ls"}}\n```'
    filt = ToolCallStreamFilter(TOOLS)
    visible = ""
    for i in range(1, len(text) + 1):
        visible += filt.feed(text[:i])
    tail, parsed = filt.finish(text)
    assert parsed.has_calls, "tool call not detected in stream"
    assert "bash" not in visible and "```" not in visible, f"tool call leaked into content: {visible!r}"
    assert visible.strip() == "Let me check.", visible
    assert tail == ""
    print("✓ streaming filter hides the raw tool call")

    prose = "Sure, that is all. ```json-ish text```"
    filt = ToolCallStreamFilter(TOOLS)
    out = ""
    for i in range(1, len(prose) + 1):
        out += filt.feed(prose[:i])
    tail, parsed = filt.finish(prose)
    assert not parsed.has_calls
    assert out + tail == prose, f"prose was altered: {out + tail!r}"
    print("✓ streaming filter releases non-tool text unchanged")


def test_instructions_mention_every_tool():
    block = build_tool_instructions(TOOLS, "auto")
    for tool in TOOLS:
        assert tool["function"]["name"] in block
    assert '"arguments"' in block
    print("✓ tool instructions list every tool")


# ── End to end over the API ──────────────────────────────────────────────────


def test_endpoint_returns_tool_calls():
    with TestClient(app) as client:
        ws, fake = register_browser(client, ['I will list the files.\n```json\n{"name": "bash", "arguments": {"command": "ls -la"}}\n```'])
        try:
            r = client.post("/v1/chat/completions", json={
                "model": "deepseek",
                "messages": [{"role": "user", "content": "What files are here?"}],
                "tools": TOOLS,
            })
            assert r.status_code == 200, r.text
            data = r.json()
            choice = data["choices"][0]
            assert choice["finish_reason"] == "tool_calls", choice
            calls = choice["message"]["tool_calls"]
            assert len(calls) == 1 and calls[0]["type"] == "function"
            assert calls[0]["function"]["name"] == "bash"
            assert json.loads(calls[0]["function"]["arguments"]) == {"command": "ls -la"}
            assert "```" not in (choice["message"]["content"] or "")
            assert fake.prompts and "TOOLS AVAILABLE" in fake.prompts[0] and "bash" in fake.prompts[0]
            print("✓ /v1/chat/completions returns tool_calls (non-streaming)")
        finally:
            fake.close()
            ws.__exit__(None, None, None)


def test_endpoint_streams_tool_calls():
    with TestClient(app) as client:
        answer = 'Checking now.\n```json\n{"name": "read", "arguments": {"path": "server/main.py"}}\n```'
        ws, fake = register_browser(client, [answer], provider="chatgpt")
        try:
            with client.stream("POST", "/v1/chat/completions", json={
                "model": "chatgpt",
                "messages": [{"role": "user", "content": "Read main.py"}],
                "tools": TOOLS,
                "stream": True,
            }) as resp:
                assert resp.status_code == 200, resp.read()
                events = []
                for line in resp.iter_lines():
                    if not line:
                        continue
                    text = line.decode() if isinstance(line, bytes) else line
                    if text.startswith("data: ") and text.strip() != "data: [DONE]":
                        events.append(json.loads(text[6:]))
            deltas = [e["choices"][0]["delta"] for e in events]
            content = "".join(d.get("content") or "" for d in deltas)
            finish = [e["choices"][0]["finish_reason"] for e in events if e["choices"][0]["finish_reason"]]
            assert finish == ["tool_calls"], finish
            assert "read" not in content and "```" not in content, f"tool call leaked: {content!r}"
            # Tool calls are a separate assistant message: even a browser model
            # that emitted a preamble must not leak it before tool_call deltas.
            assert content.strip() == "", repr(content)
            names = [tc["function"]["name"] for d in deltas for tc in (d.get("tool_calls") or []) if tc.get("function", {}).get("name")]
            args = "".join(tc["function"]["arguments"] for d in deltas for tc in (d.get("tool_calls") or []) if "arguments" in tc.get("function", {}))
            assert names == ["read"], names
            assert json.loads(args) == {"path": "server/main.py"}
            ids = [tc["id"] for d in deltas for tc in (d.get("tool_calls") or []) if tc.get("id")]
            assert ids and ids[0].startswith("call_")
            print("✓ /v1/chat/completions streams tool_call deltas + finish_reason=tool_calls")
        finally:
            fake.close()
            ws.__exit__(None, None, None)


def test_tool_results_are_folded_back():
    with TestClient(app) as client:
        ws, fake = register_browser(client, ["Done: the directory holds 3 files."])
        try:
            r = client.post("/v1/chat/completions", json={
                "model": "deepseek",
                "messages": [
                    {"role": "user", "content": "List files"},
                    {"role": "assistant", "content": None, "tool_calls": [
                        {"id": "call_abc", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
                    ]},
                    {"role": "tool", "tool_call_id": "call_abc", "name": "bash", "content": "a.py b.py c.py"},
                ],
                "tools": TOOLS,
            })
            assert r.status_code == 200, r.text
            choice = r.json()["choices"][0]
            assert choice["finish_reason"] == "stop"
            assert "3 files" in choice["message"]["content"]
            sent = fake.prompts[-1]
            assert "[Tool result: bash]" in sent and "a.py b.py c.py" in sent, sent
            assert "call_abc" not in sent
            print("✓ tool results are folded back into the next prompt")
        finally:
            fake.close()
            ws.__exit__(None, None, None)


def test_plain_streaming_still_works():
    with TestClient(app) as client:
        ws, fake = register_browser(client, ["Hello! " * 40])
        try:
            with client.stream("POST", "/v1/chat/completions", json={
                "model": "deepseek",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            }) as resp:
                body = b"".join(resp.iter_bytes())
            text = body.decode()
            assert "data: [DONE]" in text
            assert '"finish_reason": "stop"' in text.replace('"finish_reason":"stop"', '"finish_reason": "stop"')
            assert "Hello!" in text
            print("✓ streaming without tools unchanged")
        finally:
            fake.close()
            ws.__exit__(None, None, None)


def test_streaming_with_tools_but_no_tool_call():
    """Tools offered, model answers normally -> plain streamed answer + stop."""
    with TestClient(app) as client:
        answer = "Everything is already done, no tools needed."
        ws, fake = register_browser(client, [answer], provider="gemini")
        try:
            with client.stream("POST", "/v1/chat/completions", json={
                "model": "gemini",
                "messages": [{"role": "user", "content": "status?"}],
                "tools": TOOLS,
                "stream": True,
                "stream_options": {"include_usage": True},
            }) as resp:
                body = b"".join(resp.iter_bytes()).decode()
            events = [json.loads(l[6:]) for l in body.splitlines() if l.startswith("data: ") and l.strip() != "data: [DONE]"]
            content = "".join((e["choices"][0]["delta"].get("content") or "") for e in events if e["choices"])
            finish = [e["choices"][0]["finish_reason"] for e in events if e["choices"] and e["choices"][0]["finish_reason"]]
            assert content == answer, repr(content)
            assert finish == ["stop"], finish
            assert "TOOLS AVAILABLE" in fake.prompts[0]
            usage = [e["usage"] for e in events if not e["choices"]]
            assert usage and usage[0]["prompt_tokens"] > 0
            print("✓ streaming with tools but no tool call returns plain content + stop + usage")
        finally:
            fake.close()
            ws.__exit__(None, None, None)


def test_tool_choice_none_disables_tools():
    with TestClient(app) as client:
        ws, fake = register_browser(client, ['No tools used.\n```json\n{"name": "bash", "arguments": {"command": "rm -rf /"}}\n```'])
        try:
            r = client.post("/v1/chat/completions", json={
                "model": "deepseek",
                "messages": [{"role": "user", "content": "hello"}],
                "tools": TOOLS,
                "tool_choice": "none",
            })
            data = r.json()
            choice = data["choices"][0]
            assert choice["finish_reason"] == "stop"
            assert choice["message"]["tool_calls"] in (None, [])
            assert "TOOLS AVAILABLE" not in fake.prompts[0]
            print("✓ tool_choice=none keeps the request tool-free")
        finally:
            fake.close()
            ws.__exit__(None, None, None)


if __name__ == "__main__":
    test_parse_shapes()
    test_stream_filter_holds_tool_calls()
    test_instructions_mention_every_tool()
    test_endpoint_returns_tool_calls()
    test_endpoint_streams_tool_calls()
    test_tool_results_are_folded_back()
    test_plain_streaming_still_works()
    test_streaming_with_tools_but_no_tool_call()
    test_tool_choice_none_disables_tools()
    print("\nAll tool calling tests passed!")
