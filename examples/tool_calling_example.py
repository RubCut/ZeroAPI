#!/usr/bin/env python3
"""
ZeroAPI tool calling example - a minimal agent loop, the same way opencode works.

The client sends its tools with the request, ZeroAPI returns OpenAI `tool_calls`,
the client executes them locally and sends the results back until the model stops
asking for tools.

Run:
    python zeroapi.py                 # start the server
    python examples/tool_calling_example.py
"""
import json
import os
import subprocess
from openai import OpenAI

BASE_URL = os.environ.get("ZEROAPI_URL", "http://localhost:8000/v1")
MODEL = os.environ.get("ZEROAPI_MODEL", "deepseek")

client = OpenAI(base_url=BASE_URL, api_key=os.environ.get("ZEROAPI_KEY", "zeroapi"))

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command and return its output",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "Command to run"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
]


def run_tool(name, arguments):
    """Local tool execution - exactly what opencode / LangChain do on their side."""
    args = json.loads(arguments or "{}")
    if name == "bash":
        proc = subprocess.run(args.get("command", "true"), shell=True, capture_output=True, text=True, timeout=60)
        return (proc.stdout or "") + (proc.stderr or "")
    if name == "read_file":
        try:
            with open(args["path"], "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()[:4000]
        except Exception as exc:
            return f"ERROR: {exc}"
    return f"ERROR: unknown tool {name}"


def agent(question, stream=False, max_steps=5):
    messages = [{"role": "user", "content": question}]
    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS, stream=stream)
        text_parts, tool_calls = [], []

        if stream:
            finish = None
            for chunk in resp:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue
                if choice.finish_reason:
                    finish = choice.finish_reason
                delta = choice.delta
                if delta.content:
                    text_parts.append(delta.content)
                    print(delta.content, end="", flush=True)
                for call in (delta.tool_calls or []):
                    while len(tool_calls) <= (call.index or 0):
                        tool_calls.append({"id": "", "name": "", "arguments": ""})
                    slot = tool_calls[call.index]
                    if call.id:
                        slot["id"] = call.id
                    if call.function and call.function.name:
                        slot["name"] = call.function.name
                    if call.function and call.function.arguments:
                        slot["arguments"] += call.function.arguments
            print()
        else:
            choice = resp.choices[0]
            finish = choice.finish_reason
            text_parts.append(choice.message.content or "")
            tool_calls = [
                {"id": c.id, "name": c.function.name, "arguments": c.function.arguments}
                for c in (choice.message.tool_calls or [])
            ]
            print(choice.message.content or "")

        print(f"[step {step}] finish_reason={finish} tool_calls={[c['name'] for c in tool_calls]}")

        if not tool_calls:
            return "".join(text_parts).strip()

        messages.append({
            "role": "assistant",
            "content": "".join(text_parts).strip() or None,
            "tool_calls": [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in tool_calls
            ],
        })
        for call in tool_calls:
            output = run_tool(call["name"], call["arguments"])
            print(f"    -> {call['name']}({call['arguments']}) = {output.strip()[:200]!r}")
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": output})

    return "max tool steps reached"


if __name__ == "__main__":
    print(f"ZeroAPI at {BASE_URL}, model={MODEL}\n")
    print("=== streaming agent loop ===")
    print(agent("Which files are in this project? Use the bash tool, then answer in one sentence.", stream=True))
    print("\n=== non-streaming agent loop ===")
    print(agent("Read README.md and tell me the first heading.", stream=False))
