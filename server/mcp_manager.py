"""
MCP Manager - simplified version from original bridge.py
Keeps compatibility for tool execution if needed.
"""
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import queue
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(HERE, "config.json")

PRIMARY_SERVER_ID = "roblox"

class MCPClient:
    def __init__(self, server_id, command, args, env=None):
        self.id = server_id
        self.command = command
        self.args = list(args or [])
        self.env = env or {}
        self.proc = None
        self.req_id = 1
        self.write_lock = threading.Lock()
        self.call_lock = threading.Lock()
        self.pending = {}
        self.pend_lock = threading.Lock()
        self.tools_cache = []
        self.start_lock = threading.Lock()
        self._reader_thread = None

    def _resolve(self, s):
        return os.path.expandvars(os.path.expanduser(str(s)))

    def start(self):
        with self.start_lock:
            if self.is_alive():
                return
            cmd = [self._resolve(self.command)] + [self._resolve(a) for a in self.args]
            if cmd[0].lower().endswith(".py"):
                script = cmd[0]
                if not os.path.isabs(script):
                    script = os.path.join(HERE, script)
                cmd = [sys.executable, script] + cmd[1:]
            if sys.platform == "win32":
                base = os.path.basename(cmd[0]).lower()
                if base in ("npx", "npm", "yarn", "pnpm", "bunx"):
                    cmd = ["cmd.exe", "/c"] + cmd
            env = dict(os.environ)
            for k, v in self.env.items():
                env[k] = self._resolve(v)
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                    errors="replace",
                    cwd=HERE,
                    env=env,
                )
            except Exception as e:
                print(f"[{self.id}] failed to start: {e}")
                raise
            with self.pend_lock:
                self.pending.clear()
            self._reader_thread = threading.Thread(target=self._reader, args=(self.proc,), daemon=True)
            self._reader_thread.start()
            threading.Thread(target=self._stderr_drain, args=(self.proc,), daemon=True).start()
            self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "zeroapi-bridge", "version": "2.0"},
            }, timeout=30)
            self._notify("notifications/initialized")
            for _ in range(6):
                if self.refresh_tools(timeout=3):
                    break
                if not self.is_alive():
                    break
                time.sleep(1.0)

    def is_alive(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        with self.pend_lock:
            for q in self.pending.values():
                try:
                    q.put_nowait(None)
                except:
                    pass
            self.pending.clear()
        if self.proc:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True, timeout=8)
                else:
                    self.proc.terminate()
            except:
                pass
        self.proc = None

    def _reader(self, proc):
        stream = proc.stdout
        while True:
            try:
                line = stream.readline()
            except:
                break
            if line == "":
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except:
                continue
            mid = msg.get("id")
            if mid is None:
                continue
            with self.pend_lock:
                q = self.pending.get(mid)
            if q is not None:
                try:
                    q.put_nowait(msg)
                except:
                    pass

    def _stderr_drain(self, proc):
        try:
            for line in iter(proc.stderr.readline, ""):
                pass
        except:
            pass

    def _next_id(self):
        with self.write_lock:
            rid = self.req_id
            self.req_id += 1
            return rid

    def _notify(self, method, params=None):
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        with self.write_lock:
            self.proc.stdin.write(json.dumps(payload) + "\n")
            self.proc.stdin.flush()

    def _request(self, method, params, timeout):
        if not self.is_alive():
            raise RuntimeError(f"server '{self.id}' is not running")
        rid = self._next_id()
        q = queue.Queue(maxsize=1)
        with self.pend_lock:
            self.pending[rid] = q
        try:
            payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
            with self.write_lock:
                self.proc.stdin.write(json.dumps(payload) + "\n")
                self.proc.stdin.flush()
            try:
                return q.get(timeout=timeout)
            except queue.Empty:
                return None
        finally:
            with self.pend_lock:
                self.pending.pop(rid, None)

    def refresh_tools(self, timeout=20):
        msg = self._request("tools/list", {}, timeout=timeout)
        if msg and "result" in msg:
            self.tools_cache = msg["result"].get("tools", [])
        return self.tools_cache

    def call_tool(self, name, arguments, timeout):
        with self.call_lock:
            if not self.is_alive():
                self.start()
            msg = self._request("tools/call", {"name": name, "arguments": arguments}, timeout)
            if msg is None:
                raise TimeoutError(f"No response from server '{self.id}' after {timeout}s.")
            if msg.get("error"):
                raise RuntimeError(msg["error"].get("message", json.dumps(msg["error"])))
            content = msg.get("result", {}).get("content", [])
            text = "\n".join(it.get("text", "") for it in content if it.get("type") == "text")
            images = [{"data": it["data"], "mimeType": it.get("mimeType", "image/jpeg")} for it in content if it.get("type") == "image" and it.get("data")]
            return {"text": text, "images": images}

class MCPManager:
    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}
        self.index = {}
        self.index_lock = threading.Lock()

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                servers = cfg.get("mcpServers", {})
                for sid, spec in servers.items():
                    self.clients[sid] = MCPClient(sid, spec.get("command"), spec.get("args"), spec.get("env"))
            except Exception as e:
                print(f"config load error: {e}")
        print(f"configured {len(self.clients)} MCP server(s)")

    def start_all(self):
        threads = []
        for sid, client in self.clients.items():
            def _run(sid=sid, client=client):
                try:
                    client.start()
                except Exception as e:
                    print(f"[{sid}] failed to start: {e}")
            t = threading.Thread(target=_run, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        self.rebuild_index()

    def rebuild_index(self):
        with self.index_lock:
            self.index = {}
            for sid, client in self.clients.items():
                for t in (client.tools_cache or []):
                    name = t.get("name")
                    if not name:
                        continue
                    advertised = name if name not in self.index else f"{sid}/{name}"
                    self.index[advertised] = (client, name)

    def list_tools(self):
        out = []
        for sid, client in self.clients.items():
            for t in (client.tools_cache or []):
                name = t.get("name")
                advertised = name
                with self.index_lock:
                    for k, (holder, real) in self.index.items():
                        if holder is client and real == name:
                            advertised = k
                            break
                tt = dict(t)
                tt["name"] = advertised
                tt["server"] = sid
                out.append(tt)
        return out

    def call(self, name, arguments, timeout):
        with self.index_lock:
            entry = self.index.get(name)
        if entry is None:
            self.rebuild_index()
            with self.index_lock:
                entry = self.index.get(name)
        if entry is None:
            raise RuntimeError(f"unknown tool '{name}'")
        holder, real_name = entry
        return holder.call_tool(real_name, arguments, timeout)

    def health(self):
        return [{"id": sid, "alive": c.is_alive(), "tools": len(c.tools_cache)} for sid, c in self.clients.items()]

mcp_manager = MCPManager()
