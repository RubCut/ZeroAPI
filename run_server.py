#!/usr/bin/env python3
"""
ZeroAPI Server Runner v2.8.1 - Compact professional UI
- Small header, no emojis, product-ready
- Config: zeroapi_config.json for ports, keys, tunnel autostart
- Auto-detects tunnels: cloudflare, ngrok, localtunnel, bore
- Auto-starts tunnel if configured
"""

import argparse
import sys
import os
import json
import socket
import time
import threading
import logging
import re
import glob
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CONFIG_PATH = Path(__file__).parent / "zeroapi_config.json"

DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8000,
    "api_key": "zeroapi",
    "log_enabled": False,
    "theme": "dark",
    "auto_clear_files": True,
    "allowed_origins": ["*"],
    "default_model": "deepseek",
    "auto_switch_tabs": True,
    "auto_focus_tab": True,
    "notify_on_switch": True,
    "tunnel_auto_detect": True,
    "tunnel_url": "",
    "public_url": "",
    "external_urls": [],
    "tunnel": {
        "enabled": False,
        "provider": "cloudflare",
        "auto_start": False,
        "port": None,
        "subdomain": "",
        "custom_command": "",
        "extra_args": "",
        "url_file": ""
    },
    "models": ["deepseek", "chatgpt", "gemini", "kimi", "glm", "qwen", "meta", "arena", "auto"]
}

def load_config():
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        if "tunnel" in cfg and isinstance(cfg["tunnel"], dict):
            tunnel_merged = DEFAULT_CONFIG["tunnel"].copy()
            tunnel_merged.update(cfg["tunnel"])
            cfg["tunnel"] = tunnel_merged
        merged.update(cfg)
        return merged
    except Exception as e:
        print(f"[!] Failed to load config: {e}, using defaults")
        return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Failed to save config: {e}")

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "127.0.0.1"

def get_header():
    return "ZeroAPI v2.8.1 | OpenAI Compatible API Server"

# Global state
log_enabled = False
server_thread = None
stop_event = threading.Event()
current_browsers = 0
current_providers = []
current_tunnels = []
tunnel_process = None
tunnel_thread = None
tunnel_detected_url = ""
tunnel_status = "idle"

# --- Tunnel Detection ---

def detect_ngrok_tunnels(port):
    tunnels = []
    try:
        import httpx
        for api_port in [4040, 4041, 4042]:
            try:
                r = httpx.get(f"http://127.0.0.1:{api_port}/api/tunnels", timeout=1.5)
                if r.status_code == 200:
                    data = r.json()
                    for t in data.get("tunnels", []):
                        public_url = t.get("public_url", "")
                        config = t.get("config", {})
                        addr = config.get("addr", "")
                        if str(port) in str(addr) or f":{port}" in str(addr) or "localhost" in str(addr).lower():
                            if public_url.startswith("https://"):
                                tunnels.append({
                                    "name": "ngrok",
                                    "url": public_url,
                                    "type": "ngrok",
                                    "provider": "ngrok",
                                    "addr": addr,
                                    "proto": t.get("proto", "")
                                })
                    if tunnels:
                        break
                    for t in data.get("tunnels", []):
                        public_url = t.get("public_url", "")
                        if public_url.startswith("https://"):
                            config = t.get("config", {})
                            addr = str(config.get("addr", ""))
                            if str(port) in addr or len(data.get("tunnels", [])) == 1:
                                tunnels.append({
                                    "name": "ngrok",
                                    "url": public_url,
                                    "type": "ngrok",
                                    "provider": "ngrok",
                                    "addr": addr,
                                    "proto": t.get("proto", "")
                                })
                    if tunnels:
                        break
            except:
                continue
    except:
        pass
    return tunnels

def detect_cloudflare_tunnels():
    tunnels = []
    patterns = [
        r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com",
        r"https://[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-]+\.trycloudflare\.com",
        r"https://[a-zA-Z0-9\-]+\.cfargotunnel\.com",
    ]
    for env_key in ["CLOUDFLARE_TUNNEL_URL", "CF_TUNNEL_URL", "TUNNEL_URL", "CLOUDFLARED_URL"]:
        url = os.environ.get(env_key, "")
        if url and ("trycloudflare.com" in url or "cfargotunnel.com" in url or "cloudflare" in url.lower()):
            if re.match(r"https?://", url):
                tunnels.append({"name": "cloudflare", "url": url.strip(), "type": "cloudflare", "provider": "cloudflare"})
    log_paths = [
        "/tmp/cloudflared.log",
        "/tmp/cf.log",
        "/tmp/tunnel.log",
        "./cloudflared.log",
        "./tunnel.log",
        os.path.expanduser("~/.cloudflared/cloudflared.log"),
        "/tmp/cloudflared/*.log",
        "./*.log",
    ]
    for log_pattern in log_paths:
        try:
            for log_file in glob.glob(log_pattern):
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()[-10000:]
                        for pat in patterns:
                            matches = re.findall(pat, content)
                            for m in matches:
                                if m not in [t["url"] for t in tunnels]:
                                    tunnels.append({"name": "cloudflare", "url": m, "type": "cloudflare", "provider": "cloudflare", "source": log_file})
                except:
                    continue
        except:
            continue
    try:
        if os.name != 'nt':
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=2)
            output = result.stdout
            for line in output.split("\n"):
                if "cloudflared" in line and "trycloudflare.com" in line:
                    for pat in patterns:
                        matches = re.findall(pat, line)
                        for m in matches:
                            if m not in [t["url"] for t in tunnels]:
                                tunnels.append({"name": "cloudflare", "url": m, "type": "cloudflare", "provider": "cloudflare", "source": "process"})
    except:
        pass
    tunnel_files = [
        "cloudflare_tunnel_url.txt",
        ".cloudflare_url",
        "/tmp/cf_tunnel_url",
        "/tmp/cloudflare_tunnel_url.txt",
        "./tunnel_url.txt",
        "/tmp/tunnel_url.txt",
    ]
    for tf in tunnel_files:
        try:
            if os.path.exists(tf):
                with open(tf, 'r') as f:
                    content = f.read().strip()
                    for pat in patterns:
                        matches = re.findall(pat, content)
                        for m in matches:
                            if m not in [t["url"] for t in tunnels]:
                                tunnels.append({"name": "cloudflare", "url": m, "type": "cloudflare", "provider": "cloudflare", "source": tf})
                    if content.startswith("https://") and ("trycloudflare.com" in content or "cfargotunnel" in content):
                        if content not in [t["url"] for t in tunnels]:
                            tunnels.append({"name": "cloudflare", "url": content, "type": "cloudflare", "provider": "cloudflare", "source": tf})
        except:
            continue
    return tunnels

def detect_localtunnel(port):
    tunnels = []
    for env_key in ["LT_URL", "LOCALTUNNEL_URL", "LOCAL_TUNNEL_URL"]:
        url = os.environ.get(env_key, "")
        if url and "loca.lt" in url:
            tunnels.append({"name": "localtunnel", "url": url.strip(), "type": "localtunnel", "provider": "localtunnel"})
    try:
        if os.name != 'nt':
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=2)
            output = result.stdout
            for line in output.split("\n"):
                if "localtunnel" in line or " lt " in line or "/lt" in line:
                    matches = re.findall(r"https://[a-zA-Z0-9\-]+\.loca\.lt", line)
                    for m in matches:
                        if m not in [t["url"] for t in tunnels]:
                            tunnels.append({"name": "localtunnel", "url": m, "type": "localtunnel", "provider": "localtunnel"})
    except:
        pass
    for tf in ["localtunnel_url.txt", "/tmp/lt_url", "./lt_url.txt"]:
        try:
            if os.path.exists(tf):
                with open(tf, 'r') as f:
                    content = f.read().strip()
                    matches = re.findall(r"https://[a-zA-Z0-9\-]+\.loca\.lt", content)
                    for m in matches:
                        if m not in [t["url"] for t in tunnels]:
                            tunnels.append({"name": "localtunnel", "url": m, "type": "localtunnel", "provider": "localtunnel"})
                    if "loca.lt" in content and content.startswith("https://"):
                        if content not in [t["url"] for t in tunnels]:
                            tunnels.append({"name": "localtunnel", "url": content, "type": "localtunnel", "provider": "localtunnel"})
        except:
            continue
    return tunnels

def detect_generic_tunnels(port, cfg):
    tunnels = []
    cfg_tunnel = cfg.get("tunnel_url", "") or cfg.get("public_url", "") or cfg.get("external_url", "")
    if cfg_tunnel and cfg_tunnel.startswith("https://"):
        tunnels.append({"name": "custom", "url": cfg_tunnel.strip(), "type": "custom", "provider": "custom", "source": "config"})
    for url in cfg.get("external_urls", []):
        if url and url.startswith("https://") and url not in [t["url"] for t in tunnels]:
            tunnels.append({"name": "custom", "url": url.strip(), "type": "custom", "provider": "custom", "source": "config external_urls"})
    tunnel_cfg = cfg.get("tunnel", {})
    if isinstance(tunnel_cfg, dict):
        nested_url = tunnel_cfg.get("url", "") or tunnel_cfg.get("tunnel_url", "") or tunnel_cfg.get("public_url", "")
        if nested_url and nested_url.startswith("https://") and nested_url not in [t["url"] for t in tunnels]:
            tunnels.append({"name": "tunnel-config", "url": nested_url.strip(), "type": "custom", "provider": "custom", "source": "tunnel.url"})
    for env_key in ["ZEROAPI_TUNNEL_URL", "ZEROAPI_PUBLIC_URL", "TUNNEL_URL", "PUBLIC_URL", "EXTERNAL_URL", "API_PUBLIC_URL"]:
        url = os.environ.get(env_key, "")
        if url and url.startswith("https://") and url not in [t["url"] for t in tunnels]:
            tunnels.append({"name": "env", "url": url.strip(), "type": "custom", "provider": "env", "source": env_key})
    generic_files = [
        "tunnel_url.txt", ".tunnel_url", "public_url.txt", ".public_url",
        "/tmp/tunnel_url", "/tmp/public_url", "/tmp/zeroapi_tunnel",
        "./.tunnel", "./tunnel.txt"
    ]
    for tf in generic_files:
        try:
            if os.path.exists(tf):
                with open(tf, 'r') as f:
                    content = f.read().strip()
                    urls = re.findall(r"https://[^\s\"']+", content)
                    for url in urls:
                        url = url.rstrip(".,;!\"')]")
                        if url not in [t["url"] for t in tunnels] and len(url) > 10:
                            tunnels.append({"name": "file", "url": url, "type": "custom", "provider": "file", "source": tf})
        except:
            continue
    try:
        if os.name != 'nt':
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=2)
            output = result.stdout.lower()
            if "bore" in output:
                matches = re.findall(r"https://[a-zA-Z0-9\-]+\.bore\.pub", output)
                for m in matches:
                    if m not in [t["url"] for t in tunnels]:
                        tunnels.append({"name": "bore", "url": m, "type": "bore", "provider": "bore"})
    except:
        pass
    return tunnels

def detect_tunnels(port, cfg=None):
    if cfg is None:
        cfg = load_config()
    if not cfg.get("tunnel_auto_detect", True):
        return detect_generic_tunnels(port, cfg)
    all_tunnels = []
    all_tunnels.extend(detect_generic_tunnels(port, cfg))
    all_tunnels.extend(detect_ngrok_tunnels(port))
    all_tunnels.extend(detect_cloudflare_tunnels())
    all_tunnels.extend(detect_localtunnel(port))
    seen = set()
    deduped = []
    for t in all_tunnels:
        url = t["url"].rstrip("/")
        if url not in seen:
            seen.add(url)
            deduped.append(t)
    return deduped

# --- Tunnel Auto-start ---

def build_tunnel_command(cfg, port):
    tunnel_cfg = cfg.get("tunnel", {})
    if not isinstance(tunnel_cfg, dict):
        tunnel_cfg = {}
    provider = tunnel_cfg.get("provider", cfg.get("tunnel_provider", "cloudflare")).lower()
    tunnel_port = tunnel_cfg.get("port") or cfg.get("tunnel_port") or port
    subdomain = tunnel_cfg.get("subdomain", "") or cfg.get("tunnel_subdomain", "")
    extra_args = tunnel_cfg.get("extra_args", "") or cfg.get("tunnel_extra_args", "")
    custom_cmd = tunnel_cfg.get("custom_command", "") or tunnel_cfg.get("command", "") or cfg.get("tunnel_command", "")
    if provider == "custom" and custom_cmd:
        return custom_cmd
    if provider == "cloudflare":
        cmd = f"cloudflared tunnel --url http://localhost:{tunnel_port}"
        if extra_args:
            cmd += f" {extra_args}"
        return cmd
    elif provider == "ngrok":
        cmd = f"ngrok http {tunnel_port}"
        if subdomain:
            cmd += f" --subdomain={subdomain}"
        if extra_args:
            cmd += f" {extra_args}"
        return cmd
    elif provider in ("localtunnel", "lt"):
        cmd = f"lt --port {tunnel_port}"
        if subdomain:
            cmd += f" --subdomain {subdomain}"
        if extra_args:
            cmd += f" {extra_args}"
        return cmd
    elif provider == "bore":
        cmd = f"bore local {tunnel_port} --to bore.pub"
        if extra_args:
            cmd += f" {extra_args}"
        return cmd
    elif provider in ("none", "", "disabled"):
        return None
    else:
        if custom_cmd:
            return custom_cmd
        return None

def tunnel_output_reader(proc, port):
    global tunnel_detected_url, tunnel_status
    url_patterns = [
        r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com",
        r"https://[a-zA-Z0-9\-]+\.cfargotunnel\.com",
        r"https://[a-zA-Z0-9\-]+\.ngrok\.io",
        r"https://[a-zA-Z0-9\-]+\.ngrok-free\.app",
        r"https://[a-zA-Z0-9\-]+\.loca\.lt",
        r"https://[a-zA-Z0-9\-]+\.bore\.pub",
        r"https://[^\s]+\.trycloudflare\.com",
        r"https://[^\s]+\.loca\.lt",
        r"https://[^\s]+\.ngrok\.io",
    ]
    try:
        while True:
            if proc.poll() is not None:
                break
            try:
                line = proc.stdout.readline() if proc.stdout else ""
                if not line and proc.stderr:
                    line = proc.stderr.readline()
            except:
                line = ""
            if not line:
                time.sleep(0.5)
                continue
            line_str = line.decode('utf-8', errors='ignore') if isinstance(line, bytes) else str(line)
            for pat in url_patterns:
                matches = re.findall(pat, line_str)
                for m in matches:
                    url = m.rstrip(".,;!\"')]")
                    if url not in [t["url"] for t in detect_tunnels(port)]:
                        tunnel_detected_url = url
                        tunnel_status = "running"
                        try:
                            with open("/tmp/cloudflared.log", "a") as f:
                                f.write(f"\n{tunnel_detected_url}\n")
                            with open("tunnel_url.txt", "w") as f:
                                f.write(tunnel_detected_url)
                            os.environ["ZEROAPI_TUNNEL_URL"] = tunnel_detected_url
                        except:
                            pass
                        print(f"\n[zeroapi] Tunnel URL detected: {url}\n")
            if log_enabled:
                print(f"[tunnel] {line_str.strip()}")
    except Exception as e:
        print(f"[zeroapi] Tunnel reader error: {e}")
        tunnel_status = "failed"

def start_tunnel_from_config(cfg):
    global tunnel_process, tunnel_thread, tunnel_status, tunnel_detected_url
    tunnel_cfg = cfg.get("tunnel", {})
    if not isinstance(tunnel_cfg, dict):
        tunnel_cfg = {}
    enabled = tunnel_cfg.get("enabled", False) or tunnel_cfg.get("auto_start", False) or cfg.get("tunnel_enabled", False) or cfg.get("tunnel_auto_start", False)
    if not enabled:
        return None
    provider = tunnel_cfg.get("provider", cfg.get("tunnel_provider", "cloudflare"))
    if not provider or provider in ("none", "disabled"):
        return None
    port = tunnel_cfg.get("port") or cfg.get("tunnel_port") or cfg.get("port", 8000)
    command = build_tunnel_command(cfg, port)
    if not command:
        print(f"[zeroapi] Tunnel enabled but no command for provider {provider}")
        return None
    print(f"[zeroapi] Starting tunnel: provider={provider} port={port}")
    print(f"[zeroapi] Command: {command}")
    tunnel_status = "starting"
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=False
        )
        tunnel_process = proc
        t = threading.Thread(target=tunnel_output_reader, args=(proc, port), daemon=True)
        t.start()
        tunnel_thread = t
        time.sleep(2)
        if proc.poll() is not None:
            print(f"[zeroapi] Tunnel process exited with code {proc.poll()}, trying alternative...")
            if provider in ("localtunnel", "lt") and not command.startswith("npx"):
                alt_cmd = f"npx localtunnel --port {port}"
                print(f"[zeroapi] Trying: {alt_cmd}")
                proc = subprocess.Popen(alt_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                tunnel_process = proc
                t = threading.Thread(target=tunnel_output_reader, args=(proc, port), daemon=True)
                t.start()
                tunnel_thread = t
                time.sleep(2)
        print(f"[zeroapi] Tunnel PID={proc.pid} status={tunnel_status}")
        return proc
    except Exception as e:
        print(f"[zeroapi] Failed to start tunnel: {e}")
        tunnel_status = "failed"
        return None

def stop_tunnel():
    global tunnel_process, tunnel_status
    if tunnel_process:
        try:
            tunnel_process.terminate()
            try:
                tunnel_process.wait(timeout=3)
            except:
                tunnel_process.kill()
            print("[zeroapi] Tunnel stopped")
        except:
            pass
        tunnel_process = None
    tunnel_status = "idle"

def fetch_server_status(port):
    global current_browsers, current_providers, current_tunnels
    try:
        import httpx
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
        if r.status_code == 200:
            data = r.json()
            current_browsers = data.get("browsers_connected", 0)
            current_providers = data.get("active_providers", []) or data.get("available_providers", [])
            current_tunnels = data.get("tunnels", []) or data.get("tunnel_urls", [])
    except:
        pass

def ui_loop(cfg):
    global log_enabled, current_tunnels, tunnel_detected_url, tunnel_status
    log_enabled = cfg.get("log_enabled", False)
    port = cfg.get("port", 8000)
    host = cfg.get("host", "0.0.0.0")
    api_key = cfg.get("api_key", "zeroapi")
    lan_ip = get_local_ip()

    use_msvcrt = False
    try:
        import msvcrt
        use_msvcrt = True
    except:
        use_msvcrt = False

    if not use_msvcrt:
        try:
            import tty, termios
            has_termios = True
        except:
            has_termios = False
    else:
        has_termios = False

    last_status_fetch = 0
    last_tunnel_check = 0
    detected_tunnels = []

    while not stop_event.is_set():
        if time.time() - last_status_fetch > 2:
            fetch_server_status(port)
            last_status_fetch = time.time()
        if time.time() - last_tunnel_check > 5:
            try:
                detected_tunnels = detect_tunnels(port, cfg)
            except:
                detected_tunnels = []
            last_tunnel_check = time.time()
            if current_tunnels:
                for st in current_tunnels:
                    url = st.get("url") if isinstance(st, dict) else str(st)
                    if url not in [t["url"] for t in detected_tunnels]:
                        detected_tunnels.append({"name": st.get("name", "server"), "url": url, "type": st.get("type", "unknown"), "provider": st.get("provider", "unknown")})
            if tunnel_detected_url and tunnel_detected_url not in [t["url"] for t in detected_tunnels]:
                detected_tunnels.append({"name": "autostart", "url": tunnel_detected_url, "type": "auto", "provider": "autostart", "source": "autostart"})

        clear_console()
        print()
        print(f" {get_header()}")
        print(f" {'-'*56}")
        print(f" Status: RUNNING | Port: {port} | Browsers: {current_browsers}")
        print(f" {'-'*56}")
        print()
        print(f" Server")
        print(f"   Local:   http://localhost:{port}")
        print(f"   Network: http://{lan_ip}:{port}")
        if detected_tunnels:
            for tun in detected_tunnels:
                url = tun.get("url", "")
                typ = tun.get("type", "custom")
                print(f"   Public:  {url} [{typ}]")
                print(f"            {url}/v1/chat/completions")
            if tunnel_status == "starting":
                print(f"   Tunnel:  starting...")
            elif tunnel_status == "running" and tunnel_detected_url:
                print(f"   Tunnel:  running PID={tunnel_process.pid if tunnel_process else '?'}")
        else:
            tunnel_cfg = cfg.get("tunnel", {})
            if tunnel_cfg.get("enabled") or tunnel_cfg.get("auto_start"):
                print(f"   Public:  {tunnel_status} ({tunnel_cfg.get('provider','?')}) waiting for URL...")
            else:
                print(f"   Public:  (none)")
        print()
        print(f" Auth")
        print(f"   API Key: {api_key}")
        print()
        print(f" Models")
        models = cfg.get("models", DEFAULT_CONFIG["models"])
        active_line = []
        for m in models:
            if m == "auto":
                continue
            if m in current_providers:
                active_line.append(f"{m} [active]")
            else:
                active_line.append(f"{m}")
        print(f"   {'  '.join(active_line)}")
        print(f"   {current_browsers} browsers, {len(current_providers)} providers, auto-switch: {'on' if cfg.get('auto_switch_tabs') else 'off'}")
        print()
        print(f" Endpoints")
        print(f"   /  /v1/models  /v1/chat/completions  /api/tunnels  /health")
        print(f"   Dashboard: http://localhost:{port}/")
        print()
        logs_state = "ON" if log_enabled else "OFF"
        tun_count = len(detected_tunnels)
        print(f" Logs: {logs_state} | Tunnels: {tun_count} | Providers: {', '.join(current_providers) if current_providers else 'none'}")
        print(f" {'-'*56}")
        print(f" [L] Logs  [T] Tunnels  [S] Tunnel Start/Stop  [R] Reload  [C] Clear  [Q] Quit")
        print(f" {'-'*56}")
        print()

        key = None
        if use_msvcrt:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                try:
                    key = ch.decode('utf-8').lower()
                except:
                    key = None
        else:
            if has_termios:
                import select
                dr, _, _ = select.select([sys.stdin], [], [], 0.5)
                if dr:
                    try:
                        old_settings = termios.tcgetattr(sys.stdin)
                        tty.setcbreak(sys.stdin.fileno())
                        ch = sys.stdin.read(1)
                        key = ch.lower()
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                    except:
                        pass
            else:
                time.sleep(0.5)
                continue

        if key:
            if key == 'l':
                log_enabled = not log_enabled
                cfg["log_enabled"] = log_enabled
                save_config(cfg)
                logging.getLogger("zeroapi").setLevel(logging.INFO if log_enabled else logging.WARNING)
                logging.getLogger("uvicorn").setLevel(logging.INFO if log_enabled else logging.WARNING)
            elif key == 'q':
                stop_event.set()
                stop_tunnel()
                print("\nShutting down...")
                os._exit(0)
            elif key == 'c':
                clear_console()
            elif key == 'r':
                cfg = load_config()
                log_enabled = cfg.get("log_enabled", False)
            elif key == 's':
                if tunnel_process and tunnel_process.poll() is None:
                    print("\nStopping tunnel...")
                    stop_tunnel()
                    time.sleep(1)
                else:
                    print("\nStarting tunnel...")
                    if not cfg.get("tunnel", {}).get("enabled"):
                        cfg["tunnel"]["enabled"] = True
                        cfg["tunnel"]["auto_start"] = True
                        save_config(cfg)
                    start_tunnel_from_config(cfg)
                    time.sleep(2)
            elif key == 't':
                clear_console()
                print()
                print(f" {get_header()}")
                print(f" {'-'*56}")
                print(f" Tunnel Details")
                print(f" {'-'*56}")
                print()
                if detected_tunnels:
                    for tun in detected_tunnels:
                        print(f"  {tun.get('provider')} / {tun.get('type')} - {tun.get('name')}")
                        print(f"    URL: {tun.get('url')}")
                        print(f"    API: {tun.get('url')}/v1/chat/completions")
                        print(f"    Source: {tun.get('source', 'auto')}")
                        print()
                    if tunnel_process:
                        running = tunnel_process.poll() is None
                        print(f"  Process: PID={tunnel_process.pid} Status={tunnel_status} Running={running}")
                        if tunnel_detected_url:
                            print(f"  Detected: {tunnel_detected_url}")
                else:
                    print("  No tunnels detected.")
                    print()
                    print("  Configure autostart in zeroapi_config.json:")
                    print('    { "tunnel": { "enabled": true, "provider": "cloudflare", "auto_start": true } }')
                    print()
                    print("  Manual:")
                    print(f"    ngrok http {port}")
                    print(f"    cloudflared tunnel --url http://localhost:{port}")
                    print(f"    lt --port {port}")
                    print(f"    bore local {port} --to bore.pub")
                    print()
                    print("  Or set env: ZEROAPI_TUNNEL_URL=https://xxx.trycloudflare.com")
                print()
                print(f" {'-'*56}")
                print(" Press any key to return...")
                if use_msvcrt:
                    msvcrt.getch()
                else:
                    try:
                        input()
                    except:
                        time.sleep(2)
        time.sleep(0.2)

def run_uvicorn(cfg):
    try:
        import uvicorn
    except ImportError:
        print("Installing dependencies...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        import uvicorn
    host = cfg.get("host", "0.0.0.0")
    port = cfg.get("port", 8000)
    log_level = "info" if cfg.get("log_enabled", False) else "warning"
    os.environ["ZEROAPI_HOST"] = host
    os.environ["ZEROAPI_PORT"] = str(port)
    os.environ["ZEROAPI_API_KEY"] = cfg.get("api_key", "zeroapi")
    if cfg.get("tunnel_url"):
        os.environ["ZEROAPI_TUNNEL_URL"] = cfg.get("tunnel_url")
    if cfg.get("public_url"):
        os.environ["ZEROAPI_PUBLIC_URL"] = cfg.get("public_url")
    tunnel_cfg = cfg.get("tunnel", {})
    if isinstance(tunnel_cfg, dict) and tunnel_cfg.get("url"):
        os.environ["ZEROAPI_TUNNEL_URL"] = tunnel_cfg.get("url")
    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        log_level=log_level,
        access_log=cfg.get("log_enabled", False)
    )

def main():
    parser = argparse.ArgumentParser(description="ZeroAPI v2.8.1 - OpenAI Compatible Server")
    parser.add_argument("--host", help="Host to bind")
    parser.add_argument("--port", type=int, help="Port to bind")
    parser.add_argument("--api-key", help="API key")
    parser.add_argument("--tunnel-url", help="Public tunnel URL")
    parser.add_argument("--tunnel-provider", help="Tunnel provider: cloudflare, ngrok, localtunnel, bore, custom")
    parser.add_argument("--tunnel-autostart", action="store_true", help="Auto-start tunnel")
    parser.add_argument("--no-ui", action="store_true", help="Disable UI mode")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    cfg = load_config()

    if args.host:
        cfg["host"] = args.host
    if args.port:
        cfg["port"] = args.port
    if args.api_key:
        cfg["api_key"] = args.api_key
    if args.tunnel_url:
        cfg["tunnel_url"] = args.tunnel_url
        cfg["tunnel"]["url"] = args.tunnel_url
    if args.tunnel_provider:
        cfg["tunnel"]["provider"] = args.tunnel_provider
        cfg["tunnel"]["enabled"] = True
        cfg["tunnel"]["auto_start"] = True
    if args.tunnel_autostart:
        cfg["tunnel"]["enabled"] = True
        cfg["tunnel"]["auto_start"] = True

    cfg["host"] = os.environ.get("ZEROAPI_HOST", cfg["host"])
    cfg["port"] = int(os.environ.get("ZEROAPI_PORT", cfg["port"]))
    cfg["api_key"] = os.environ.get("ZEROAPI_API_KEY", cfg["api_key"])
    if os.environ.get("ZEROAPI_TUNNEL_URL"):
        cfg["tunnel_url"] = os.environ.get("ZEROAPI_TUNNEL_URL")
    if os.environ.get("TUNNEL_URL"):
        cfg["tunnel_url"] = os.environ.get("TUNNEL_URL")
    if os.environ.get("ZEROAPI_TUNNEL_PROVIDER"):
        cfg["tunnel"]["provider"] = os.environ.get("ZEROAPI_TUNNEL_PROVIDER")
        cfg["tunnel"]["enabled"] = True

    tunnel_cfg = cfg.get("tunnel", {})
    if tunnel_cfg.get("enabled") and tunnel_cfg.get("auto_start"):
        print(f"[zeroapi] Tunnel autostart enabled: {tunnel_cfg.get('provider')} - starting in 3s")
        def delayed_tunnel_start():
            time.sleep(3)
            start_tunnel_from_config(cfg)
        threading.Thread(target=delayed_tunnel_start, daemon=True).start()

    if args.no_ui:
        print(f"""
 ZeroAPI v2.8.1 - OpenAI Compatible API Server
 ------------------------------------------------------------
 API:       http://{cfg['host']}:{cfg['port']}/v1/chat/completions
 Dashboard: http://{cfg['host']}:{cfg['port']}/
 Network:   http://{get_local_ip()}:{cfg['port']}/
 API Key:   {cfg['api_key']}
 ------------------------------------------------------------
""")
        tunnels = detect_tunnels(cfg['port'], cfg)
        if tunnels:
            print(" Public URLs:")
            for t in tunnels:
                print(f"   {t['url']} [{t['type']}]")
                print(f"   -> {t['url']}/v1/chat/completions")
            print()
        if tunnel_cfg.get("enabled"):
            print(f" Tunnel autostart: {tunnel_cfg.get('provider')} enabled")
        try:
            import uvicorn
            uvicorn.run("server.main:app", host=cfg["host"], port=cfg["port"], reload=args.reload, log_level="info" if cfg["log_enabled"] else "warning")
        except KeyboardInterrupt:
            print("\nShutting down...")
            stop_tunnel()
        return

    clear_console()
    print(f"\n {get_header()}")
    print(f" Starting server on {cfg['host']}:{cfg['port']}...\n")
    time.sleep(0.5)

    t = threading.Thread(target=run_uvicorn, args=(cfg,), daemon=True)
    t.start()
    time.sleep(2)

    try:
        ui_loop(cfg)
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop_tunnel()
        stop_event.set()
        os._exit(0)

if __name__ == "__main__":
    main()
