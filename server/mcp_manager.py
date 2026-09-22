"""
MCP Manager - simplified version from original bridge.py
Keeps compatibility for tool execution if needed.

MCP servers are read from (first file that defines them wins):
  1. zeroapi_config.json -> "mcp_servers" | "mcpServers"
  2. config.json         -> "mcpServers" (legacy ZeroScript layout)

Example zeroapi_config.json:
    {
      "mcp_servers": {
        "roblox": {"command": "python", "args": ["roblox_mcp_server.py"]}
      },
      "mcp_tools": {"enabled": true, "auto_execute": true, "max_rounds": 5}
    }
"""
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import queue
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(HERE, "zeroapi_config.json")
LEGACY_CONFIG_PATH = os.path.join(HERE, "config.json")

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
            if self.proc is None:
                return
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
        # serialize against start() so a restart cannot race the shutdown
        acquired = self.start_lock.acquire(timeout=10)
        try:
            self._stop_locked()
        finally:
            if acquired:
                self.start_lock.release()

    def _stop_locked(self):
        proc = self.proc
        with self.pend_lock:
            for q in self.pending.values():
                try:
                    q.put_nowait(None)
                except:
                    pass
            self.pending.clear()
        self.proc = None
        if proc:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=8)
                else:
                    proc.terminate()
            except Exception:
                pass

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
        proc = self.proc
        if proc is None or proc.stdin is None:
            return
        with self.write_lock:
            try:
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
            except Exception as e:
                print(f"[{self.id}] notify {method} failed: {e}")

    def _request(self, method, params, timeout):
        proc = self.proc
        if proc is None or proc.poll() is not None or proc.stdin is None:
            raise RuntimeError(f"server '{self.id}' is not running")
        rid = self._next_id()
        q = queue.Queue(maxsize=1)
        with self.pend_lock:
            self.pending[rid] = q
        try:
            payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
            with self.write_lock:
                if self.proc is not proc:
                    raise RuntimeError(f"server '{self.id}' was restarted, request dropped")
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
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
        self.settings: Dict[str, Any] = {}
        self.load_errors: List[str] = []

    def _servers_from_file(self, path) -> Optional[Dict[str, Any]]:
        """Return the MCP server dict from a config file, or None if absent."""
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            self.load_errors.append(f"{os.path.basename(path)}: {e}")
            print(f"[mcp] config load error in {path}: {e}")
            return None
        if not isinstance(cfg, dict):
            return None
        mcp_cfg = cfg.get("mcp_tools") if isinstance(cfg.get("mcp_tools"), dict) else {}
        if mcp_cfg:
            self.settings.update(mcp_cfg)
        for key in ("mcp_servers", "mcpServers"):
            servers = cfg.get(key)
            if isinstance(servers, dict) and servers:
                return servers
        return None

    def load_config(self):
        """Load MCP server definitions plus tool settings from the config files."""
        self.load_errors = []
        servers = self._servers_from_file(CONFIG_PATH)
        if servers is None:
            servers = self._servers_from_file(LEGACY_CONFIG_PATH)
        for sid, spec in (servers or {}).items():
            if not isinstance(spec, dict):
                continue
            if spec.get("disabled") or spec.get("enabled") is False:
                continue
            self.clients[sid] = MCPClient(sid, spec.get("command"), spec.get("args"), spec.get("env"))
        self.settings.setdefault("enabled", True)
        self.settings.setdefault("auto_execute", True)
        self.settings.setdefault("max_rounds", 5)
        print(f"[mcp] configured {len(self.clients)} MCP server(s) from {os.path.basename(CONFIG_PATH)}")

    @property
    def enabled(self) -> bool:
        return bool(self.clients) and bool(self.settings.get("enabled", True))

    @property
    def auto_execute(self) -> bool:
        return self.enabled and bool(self.settings.get("auto_execute", True))

    @property
    def max_rounds(self) -> int:
        try:
            return max(1, int(self.settings.get("max_rounds", 5)))
        except Exception:
            return 5

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

    def refresh(self) -> None:
        """Pull the tool list from every live server that has no cache yet."""
        for client in self.clients.values():
            if not client.is_alive() or client.tools_cache:
                continue
            try:
                client.refresh_tools(timeout=5)
            except Exception:
                pass
        self.rebuild_index()

    def list_tools(self):
        if any(not c.tools_cache for c in self.clients.values()):
            self.refresh()
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

    def openai_tools(self) -> List[Dict[str, Any]]:
        """Tool definitions in the OpenAI ``tools`` wire format."""
        out: List[Dict[str, Any]] = []
        for tool in self.list_tools():
            name = tool.get("name")
            if not name:
                continue
            schema = tool.get("inputSchema") or tool.get("input_schema") or tool.get("parameters") or {}
            if not isinstance(schema, dict):
                schema = {}
            schema.setdefault("type", "object")
            schema.setdefault("properties", {})
            out.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description") or f"MCP tool from server '{tool.get('server')}'",
                    "parameters": schema,
                },
            })
        return out

    def names(self) -> List[str]:
        return [t["function"]["name"] for t in self.openai_tools()]

    def is_mcp_tool(self, name: str) -> bool:
        with self.index_lock:
            has_index = bool(self.index)
        if not has_index:
            self.rebuild_index()
        with self.index_lock:
            return name in self.index

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
        out = []
        for sid, c in self.clients.items():
            out.append({
                "id": sid,
                "alive": c.is_alive(),
                "tools": len(c.tools_cache),
                "tool_names": [t.get("name") for t in (c.tools_cache or [])],
            })
        return out

mcp_manager = MCPManager()
