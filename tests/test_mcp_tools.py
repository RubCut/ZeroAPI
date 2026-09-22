"""
MCP tool tests for ZeroAPI.

Starts the bundled fake MCP server (tests/fake_mcp_server.py) through a temp
zeroapi_config.json and checks:

* the config file is actually read (mcp_servers key),
* /api/tools and /v1/tools expose the MCP tools,
* /api/tool/call executes one,
* a plain chat request (no client tools) automatically offers the MCP tools to
  the browser model, executes what it asks for and returns the final answer.

Run: python tests/test_mcp_tools.py
"""
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient

import server.mcp_manager as mcp_module
from server.main import app


def write_config(tmpdir):
    cfg = {
        "host": "0.0.0.0",
        "port": 8000,
        "mcp_servers": {
            "fake": {"command": sys.executable, "args": [os.path.join(HERE, "tests", "fake_mcp_server.py")]},
        },
        "mcp_tools": {"enabled": True, "auto_execute": True, "max_rounds": 3},
    }
    path = os.path.join(tmpdir, "zeroapi_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return path


class FakeBrowser(threading.Thread):
    """Fake extension: answers each chat_request with the next queued reply."""

    def __init__(self, ws, replies):
        super().__init__(daemon=True)
        self.ws = ws
        self.replies = list(replies)
        self.prompts = []

    def run(self):
        while True:
            try:
                msg = json.loads(self.ws.receive_text())
            except Exception:
                return
            if msg.get("type") != "chat_request":
                continue
            self.prompts.append(msg.get("prompt", ""))
            reply = self.replies.pop(0) if self.replies else "done"
            if msg.get("stream"):
                for i in range(0, len(reply), 10):
                    self.ws.send_text(json.dumps({
                        "type": "chat_chunk", "id": msg["id"], "delta": reply[: i + 10], "content": reply[: i + 10],
                    }))
                self.ws.send_text(json.dumps({"type": "chat_done", "id": msg["id"], "content": reply, "done": True}))
            else:
                self.ws.send_text(json.dumps({"type": "chat_response", "id": msg["id"], "content": reply, "done": True}))


def register_browser(client):
    ws = client.websocket_connect("/ws").__enter__()
    ws.send_text(json.dumps({
        "type": "register", "client_id": "mcp-test-browser", "provider": "deepseek",
        "url": "https://chat.deepseek.com/", "providers": ["deepseek"], "version": "test",
    }))
    ws.receive_text()
    return ws


def main():
    tmpdir = tempfile.mkdtemp(prefix="zeroapi-mcp-")
    cfg_path = write_config(tmpdir)
    # point the manager at the temp config (this is what a real user edits)
    mcp_module.CONFIG_PATH = cfg_path
    mcp_module.LEGACY_CONFIG_PATH = os.path.join(tmpdir, "config.json")
    mcp_module.mcp_manager.clients.clear()
    mcp_module.mcp_manager.settings.clear()
    mcp_module.mcp_manager.index.clear()

    with TestClient(app) as client:
        # lifespan loads + starts the MCP server
        deadline = time.time() + 30
        tools = []
        while time.time() < deadline:
            r = client.get("/api/tools")
            tools = r.json()["tools"]
            if tools:
                break
            time.sleep(0.5)
        assert tools, "MCP tools were not loaded from zeroapi_config.json"
        names = sorted(t["name"] for t in tools)
        assert names == ["add", "echo"], names
        print(f"✓ zeroapi_config.json mcp_servers loaded ({names})")

        # OpenAI-format discovery
        r = client.get("/v1/tools")
        data = r.json()
        assert data["object"] == "list" and len(data["data"]) == 2
        echo_spec = [t for t in data["data"] if t["function"]["name"] == "echo"][0]
        assert echo_spec["type"] == "function"
        assert echo_spec["function"]["parameters"]["properties"]["text"]["type"] == "string"
        print("✓ /v1/tools returns OpenAI tool definitions")

        # direct execution
        r = client.post("/api/tool/call", json={"name": "add", "arguments": {"a": 2, "b": 3}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] and body["text"] == "5", body
        print("✓ /api/tool/call executes an MCP tool")

        # chat request without client tools -> server offers + executes MCP tools
        ws = register_browser(client)
        browser = FakeBrowser(ws, [
            'I will echo that.\n```json\n{"name": "echo", "arguments": {"text": "hello world"}}\n```',
            "The echo tool said: hello world",
        ])
        browser.start()
        try:
            r = client.post("/v1/chat/completions", json={
                "model": "deepseek",
                "messages": [{"role": "user", "content": "echo hello world"}],
            })
            assert r.status_code == 200, r.text
            choice = r.json()["choices"][0]
            assert choice["finish_reason"] == "stop", choice
            assert "hello world" in choice["message"]["content"], choice
            assert len(browser.prompts) == 2, f"expected 2 model turns, got {len(browser.prompts)}"
            assert "TOOLS AVAILABLE" in browser.prompts[0] and "echo" in browser.prompts[0]
            assert "[Tool result: echo]" in browser.prompts[1] and "echo: hello world" in browser.prompts[1]
            print("✓ MCP tools are offered to the browser model and auto-executed (agent loop)")
        finally:
            try:
                ws.__exit__(None, None, None)
            except Exception:
                pass

    # streaming + MCP: the tool call is executed between two streaming rounds
    with TestClient(app) as client:
        ws = register_browser(client)
        browser = FakeBrowser(ws, [
            '```json\n{"name": "echo", "arguments": {"text": "streamed"}}\n```',
            "The tool replied: echo: streamed",
        ])
        browser.start()
        try:
            with client.stream("POST", "/v1/chat/completions", json={
                "model": "deepseek",
                "messages": [{"role": "user", "content": "echo streamed"}],
                "stream": True,
            }) as resp:
                assert resp.status_code == 200
                body = b"".join(resp.iter_bytes()).decode()
            events = [json.loads(l[6:]) for l in body.splitlines() if l.startswith("data: ") and l.strip() != "data: [DONE]"]
            content = "".join((e["choices"][0]["delta"].get("content") or "") for e in events if e["choices"])
            finish = [e["choices"][0]["finish_reason"] for e in events if e["choices"] and e["choices"][0]["finish_reason"]]
            assert "echo: streamed" in content, content
            assert finish == ["stop"], finish
            assert len(browser.prompts) == 2, len(browser.prompts)
            assert "[Tool result: echo]" in browser.prompts[1]
            print("✓ streaming chat runs the MCP agent loop and returns the final answer")
        finally:
            try:
                ws.__exit__(None, None, None)
            except Exception:
                pass

    # tool calls that the server cannot execute are handed to the client
    with TestClient(app) as client:
        ws = register_browser(client)
        browser = FakeBrowser(ws, ['```json\n{"name": "unknown_thing", "arguments": {}}\n```'])
        browser.start()
        try:
            r = client.post("/v1/chat/completions", json={
                "model": "deepseek",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [{
                    "type": "function",
                    "function": {"name": "client_tool", "description": "client side", "parameters": {"type": "object", "properties": {}}},
                }],
            })
            body = r.json()
            assert body["choices"][0]["finish_reason"] == "stop"
            print("✓ unknown/foreign tool names are not executed server-side")
        finally:
            try:
                ws.__exit__(None, None, None)
            except Exception:
                pass

    print("\nAll MCP tool tests passed!")


if __name__ == "__main__":
    main()
