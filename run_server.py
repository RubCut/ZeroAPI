#!/usr/bin/env python3
"""
ZeroAPI Server Runner v2.7.0 - UI Mode with Tunnel Detection
- Clears console, shows huge ZeroAPI status, IP + key + tunnel URLs
- Press L to toggle logs, Q to quit
- Config file: zeroapi_config.json for ports and keys
- Auto-detects tunnels: Cloudflare, ngrok, localtunnel, bore, etc.
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

def get_ascii_art():
    return r"""
 ███████╗███████╗██████╗  ██████╗  █████╗ ██████╗ ██╗
 ╚══███╔╝██╔════╝██╔══██╗██╔═══██╗██╔══██╗██╔══██╗██║
   ███╔╝ █████╗  ██████╔╝██║   ██║███████║██████╔╝██║
  ███╔╝  ██╔══╝  ██╔══██╗██║   ██║██╔══██║██╔═══╝ ██║
 ███████╗███████╗██║  ██║╚██████╔╝██║  ██║██║     ██║
 ╚══════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝
    """

# Global state
log_enabled = False
server_thread = None
stop_event = threading.Event()
current_browsers = 0
current_providers = []
current_tunnels = []

# --- Tunnel Detection ---

def detect_ngrok_tunnels(port):
    """Detect ngrok tunnels via API at 4040"""
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
                        # Check if this tunnel forwards to our port
                        if str(port) in str(addr) or f":{port}" in str(addr) or "localhost" in str(addr).lower():
                            # Prefer https
                            if public_url.startswith("https://"):
                                tunnels.append({
                                    "name": "ngrok",
                                    "url": public_url,
                                    "type": "ngrok",
                                    "provider": "ngrok",
                                    "addr": addr,
                                    "proto": t.get("proto", "")
                                })
                        # Even if not matching port exactly, show if only one tunnel
                        elif public_url and not tunnels:
                            # Check if port in public_url? no, but we can still show as candidate
                            pass
                    # If we found matching tunnels, break
                    if tunnels:
                        break
                    # If no matching but tunnels exist, show all https tunnels as possible
                    for t in data.get("tunnels", []):
                        public_url = t.get("public_url", "")
                        if public_url.startswith("https://"):
                            # Only add if addr contains our port or if it's the only tunnel
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
    """Detect cloudflare tunnels - look for trycloudflare.com URLs in logs and processes"""
    tunnels = []
    patterns = [
        r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com",
        r"https://[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-]+\.trycloudflare\.com",
        r"https://[a-zA-Z0-9\-]+\.cfargotunnel\.com",
    ]
    
    # Check env vars first
    for env_key in ["CLOUDFLARE_TUNNEL_URL", "CF_TUNNEL_URL", "TUNNEL_URL", "CLOUDFLARED_URL"]:
        url = os.environ.get(env_key, "")
        if url and "trycloudflare.com" in url or "cfargotunnel.com" in url or "cloudflare" in url.lower():
            if re.match(r"https?://", url):
                tunnels.append({"name": "cloudflare", "url": url.strip(), "type": "cloudflare", "provider": "cloudflare"})
    
    # Check common log file locations
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
                        content = f.read()[-10000:]  # last 10k chars
                        for pat in patterns:
                            matches = re.findall(pat, content)
                            for m in matches:
                                if m not in [t["url"] for t in tunnels]:
                                    tunnels.append({"name": "cloudflare", "url": m, "type": "cloudflare", "provider": "cloudflare", "source": log_file})
                except:
                    continue
        except:
            continue
    
    # Check processes for cloudflared
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
                # Also check for cloudflared tunnel --url http://localhost:8000 type
                if "cloudflared" in line and "tunnel" in line:
                    # Quick tunnel often shows URL in process args? Not typically, but we can note that cloudflared is running
                    pass
    except:
        pass
    
    # Check for tunnel URL files
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
                    # Also check if file itself is a URL
                    if content.startswith("https://") and ("trycloudflare.com" in content or "cfargotunnel" in content):
                        if content not in [t["url"] for t in tunnels]:
                            tunnels.append({"name": "cloudflare", "url": content, "type": "cloudflare", "provider": "cloudflare", "source": tf})
        except:
            continue
    
    return tunnels

def detect_localtunnel(port):
    """Detect localtunnel (lt)"""
    tunnels = []
    # Env vars
    for env_key in ["LT_URL", "LOCALTUNNEL_URL", "LOCAL_TUNNEL_URL"]:
        url = os.environ.get(env_key, "")
        if url and "loca.lt" in url:
            tunnels.append({"name": "localtunnel", "url": url.strip(), "type": "localtunnel", "provider": "localtunnel"})
    
    # Check process
    try:
        if os.name != 'nt':
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=2)
            output = result.stdout
            for line in output.split("\n"):
                if "localtunnel" in line or " lt " in line or "/lt" in line:
                    # lt often shows URL like https://xxx.loca.lt
                    matches = re.findall(r"https://[a-zA-Z0-9\-]+\.loca\.lt", line)
                    for m in matches:
                        if m not in [t["url"] for t in tunnels]:
                            tunnels.append({"name": "localtunnel", "url": m, "type": "localtunnel", "provider": "localtunnel"})
    except:
        pass
    
    # Check files
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
    """Detect generic tunnels from config and env and files"""
    tunnels = []
    
    # From config
    cfg_tunnel = cfg.get("tunnel_url", "") or cfg.get("public_url", "") or cfg.get("external_url", "")
    if cfg_tunnel and cfg_tunnel.startswith("https://"):
        tunnels.append({"name": "custom", "url": cfg_tunnel.strip(), "type": "custom", "provider": "custom", "source": "config"})
    
    for url in cfg.get("external_urls", []):
        if url and url.startswith("https://") and url not in [t["url"] for t in tunnels]:
            tunnels.append({"name": "custom", "url": url.strip(), "type": "custom", "provider": "custom", "source": "config external_urls"})
    
    # Env vars
    for env_key in ["ZEROAPI_TUNNEL_URL", "ZEROAPI_PUBLIC_URL", "TUNNEL_URL", "PUBLIC_URL", "EXTERNAL_URL", "API_PUBLIC_URL"]:
        url = os.environ.get(env_key, "")
        if url and url.startswith("https://") and url not in [t["url"] for t in tunnels]:
            tunnels.append({"name": "env", "url": url.strip(), "type": "custom", "provider": "env", "source": env_key})
    
    # Files
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
                    # Find all https URLs
                    urls = re.findall(r"https://[^\s\"']+", content)
                    for url in urls:
                        # Clean trailing punctuation
                        url = url.rstrip(".,;!\"')]")
                        if url not in [t["url"] for t in tunnels] and len(url) > 10:
                            tunnels.append({"name": "file", "url": url, "type": "custom", "provider": "file", "source": tf})
        except:
            continue
    
    # Check bore, localhost.run, etc. via processes
    try:
        if os.name != 'nt':
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=2)
            output = result.stdout.lower()
            # bore
            if "bore" in output:
                matches = re.findall(r"https://[a-zA-Z0-9\-]+\.bore\.pub", output)
                for m in matches:
                    if m not in [t["url"] for t in tunnels]:
                        tunnels.append({"name": "bore", "url": m, "type": "bore", "provider": "bore"})
            # localhost.run
            if "localhost.run" in output or "ssh" in output and "8000:localhost" in output:
                # localhost.run tunnels are harder to detect URL, but we can note
                pass
    except:
        pass
    
    return tunnels

def detect_tunnels(port, cfg=None):
    """Main detection function - returns list of tunnels"""
    if cfg is None:
        cfg = load_config()
    
    if not cfg.get("tunnel_auto_detect", True):
        # Only use manual config
        return detect_generic_tunnels(port, cfg)
    
    all_tunnels = []
    
    # 1. Config and env generic
    all_tunnels.extend(detect_generic_tunnels(port, cfg))
    
    # 2. ngrok
    all_tunnels.extend(detect_ngrok_tunnels(port))
    
    # 3. Cloudflare
    all_tunnels.extend(detect_cloudflare_tunnels())
    
    # 4. Localtunnel
    all_tunnels.extend(detect_localtunnel(port))
    
    # Deduplicate by URL
    seen = set()
    deduped = []
    for t in all_tunnels:
        url = t["url"].rstrip("/")
        if url not in seen:
            seen.add(url)
            deduped.append(t)
    
    return deduped

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
    global log_enabled, current_tunnels
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
            except Exception as e:
                detected_tunnels = []
            last_tunnel_check = time.time()
            # Merge with server-reported tunnels
            if current_tunnels:
                # Add server tunnels that are not in detected
                for st in current_tunnels:
                    url = st.get("url") if isinstance(st, dict) else str(st)
                    if url not in [t["url"] for t in detected_tunnels]:
                        detected_tunnels.append({"name": st.get("name", "server"), "url": url, "type": st.get("type", "unknown"), "provider": st.get("provider", "unknown")})

        clear_console()
        print(get_ascii_art())
        print(f"\033[1;36m{'='*62}\033[0m")
        print(f"\033[1;32m  STATUS: RUNNING ✅  |  ZeroAPI v2.7.0 - OpenAI Compatible API\033[0m")
        print(f"\033[1;36m{'='*62}\033[0m")
        print()
        print(f"  \033[1;33m📡 SERVER:\033[0m")
        print(f"     Local:    \033[1;37mhttp://localhost:{port}\033[0m")
        print(f"     LAN:      \033[1;32mhttp://{lan_ip}:{port}\033[0m  \033[0;90m<- use for phone / Smartspacer\033[0m")
        print(f"     Host:     {host}:{port}")
        if detected_tunnels:
            print()
            print(f"  \033[1;33m🌐 TUNNELS (public URLs):\033[0m")
            for tun in detected_tunnels:
                name = tun.get("name", "tunnel")
                url = tun.get("url", "")
                typ = tun.get("type", "")
                print(f"     \033[1;32m●\033[0m \033[1;37m{url}\033[0m  \033[0;90m({typ} - {name})\033[0m")
                print(f"       API: \033[0;90m{url}/v1/chat/completions\033[0m")
        print()
        print(f"  \033[1;33m🔑 API KEY:\033[0m  \033[1;37m{api_key}\033[0m  \033[0;90m(any string works)\033[0m")
        print()
        print(f"  \033[1;33m🤖 MODELS (site names):\033[0m")
        models = cfg.get("models", DEFAULT_CONFIG["models"])
        for m in models:
            if m == "auto":
                continue
            is_active = m in current_providers
            dot = "\033[1;32m●\033[0m" if is_active else "\033[0;90m○\033[0m"
            status = "\033[1;32mactive\033[0m" if is_active else "\033[0;90moffline\033[0m"
            print(f"     {dot} \033[1;37m{m:<10}\033[0m {status}  \033[0;90m→ /zeroapi/{m}\033[0m")
        print(f"     \033[0;90mAuto: {current_browsers} browsers, {len(current_providers)} providers active, auto-switch ON\033[0m")
        print()
        print(f"  \033[1;33m🔌 ENDPOINTS:\033[0m")
        print(f"     Dashboard:  http://localhost:{port}/")
        print(f"     API:        http://localhost:{port}/v1/chat/completions")
        print(f"     Models:     http://localhost:{port}/v1/models")
        print(f"     Tunnels:    http://localhost:{port}/api/tunnels")
        print(f"     Test:       http://localhost:{port}/test  |  /zeroapi/deepseek")
        print()
        print(f"  \033[1;33m📊 BROWSERS:\033[0m  {current_browsers} connected  |  Providers: {', '.join(current_providers) if current_providers else 'none'}")
        if detected_tunnels:
            print(f"  \033[1;33m🌐 PUBLIC:\033[0m   {len(detected_tunnels)} tunnel(s) active")
        print()
        logs_status = "\033[1;32mON\033[0m" if log_enabled else "\033[0;90mOFF\033[0m"
        print(f"  \033[1;33m📝 LOGS:\033[0m  {logs_status}  \033[0;90m(Press L to toggle)\033[0m")
        print()
        print(f"\033[1;36m{'='*62}\033[0m")
        print(f"  \033[1;37m[L]\033[0m Toggle logs  |  \033[1;37m[C]\033[0m Clear  |  \033[1;37m[Q]\033[0m Quit  |  \033[1;37m[R]\033[0m Reload  |  \033[1;37m[T]\033[0m Show tunnels")
        print(f"\033[1;36m{'='*62}\033[0m")
        print()
        print(f"  \033[0;90mExtension: zeroapi-extension/ in chrome://extensions (Developer mode)\033[0m")
        print(f"  \033[0;90mTunnel: set tunnel_url in zeroapi_config.json or use ngrok/cloudflared/lt\033[0m")
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
                print("\n\033[1;33mShutting down...\033[0m")
                os._exit(0)
            elif key == 'c':
                clear_console()
            elif key == 'r':
                cfg = load_config()
                log_enabled = cfg.get("log_enabled", False)
            elif key == 't':
                # Show tunnels detailed
                clear_console()
                print(get_ascii_art())
                print("\n  🌐 TUNNEL DETAILS:\n")
                if detected_tunnels:
                    for tun in detected_tunnels:
                        print(f"  Name: {tun.get('name')} | Type: {tun.get('type')} | Provider: {tun.get('provider')}")
                        print(f"  URL: {tun.get('url')}")
                        print(f"  API: {tun.get('url')}/v1/chat/completions")
                        print(f"  Source: {tun.get('source', 'auto-detected')}")
                        print()
                else:
                    print("  No tunnels detected.")
                    print("  To add tunnel:")
                    print("  - ngrok: ngrok http 8000 (auto-detected via http://127.0.0.1:4040)")
                    print("  - cloudflare: cloudflared tunnel --url http://localhost:8000")
                    print("  - localtunnel: lt --port 8000")
                    print("  - Or set in zeroapi_config.json: {\"tunnel_url\": \"https://xxx.trycloudflare.com\"}")
                    print("  - Or env: ZEROAPI_TUNNEL_URL=https://xxx.ngrok.io")
                    print()
                print("  Press any key to continue...")
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
    # Pass tunnel URL if configured
    if cfg.get("tunnel_url"):
        os.environ["ZEROAPI_TUNNEL_URL"] = cfg.get("tunnel_url")
    if cfg.get("public_url"):
        os.environ["ZEROAPI_PUBLIC_URL"] = cfg.get("public_url")

    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        log_level=log_level,
        access_log=cfg.get("log_enabled", False)
    )

def main():
    parser = argparse.ArgumentParser(description="ZeroAPI - OpenAI Compatible Server v2.7.0 with tunnel detection")
    parser.add_argument("--host", help="Host to bind")
    parser.add_argument("--port", type=int, help="Port to bind")
    parser.add_argument("--api-key", help="API key")
    parser.add_argument("--tunnel-url", help="Public tunnel URL (e.g. https://xxx.trycloudflare.com)")
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
        save_config(cfg)

    cfg["host"] = os.environ.get("ZEROAPI_HOST", cfg["host"])
    cfg["port"] = int(os.environ.get("ZEROAPI_PORT", cfg["port"]))
    cfg["api_key"] = os.environ.get("ZEROAPI_API_KEY", cfg["api_key"])
    if os.environ.get("ZEROAPI_TUNNEL_URL"):
        cfg["tunnel_url"] = os.environ.get("ZEROAPI_TUNNEL_URL")
    if os.environ.get("TUNNEL_URL"):
        cfg["tunnel_url"] = os.environ.get("TUNNEL_URL")

    if args.no_ui:
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║  ZeroAPI Server v2.7.0 - OpenAI Compatible API               ║
╠══════════════════════════════════════════════════════════════╣
║  API:        http://{cfg['host']}:{cfg['port']}/v1/chat/completions      ║
║  Dashboard:  http://{cfg['host']}:{cfg['port']}/                        ║
║  LAN:        http://{get_local_ip()}:{cfg['port']}/                     ║
║  API Key:    {cfg['api_key']}                                            ║
╚══════════════════════════════════════════════════════════════╝
        """)
        tunnels = detect_tunnels(cfg['port'], cfg)
        if tunnels:
            print("  🌐 TUNNELS:")
            for t in tunnels:
                print(f"     {t['url']} ({t['type']}) -> {t['url']}/v1/chat/completions")
            print()
        try:
            import uvicorn
            uvicorn.run("server.main:app", host=cfg["host"], port=cfg["port"], reload=args.reload, log_level="info" if cfg["log_enabled"] else "warning")
        except KeyboardInterrupt:
            print("\nShutting down...")
        return

    clear_console()
    print(get_ascii_art())
    print("\n  Starting server...\n")
    time.sleep(0.5)

    t = threading.Thread(target=run_uvicorn, args=(cfg,), daemon=True)
    t.start()
    time.sleep(2)

    try:
        ui_loop(cfg)
    except KeyboardInterrupt:
        print("\n\033[1;33mShutting down...\033[0m")
        stop_event.set()
        os._exit(0)

if __name__ == "__main__":
    main()
