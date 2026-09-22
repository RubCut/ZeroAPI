#!/usr/bin/env python3
"""
ZeroAPI Server Runner v2.6.0 - UI Mode
- Clears console, shows huge ZeroAPI status, IP + key
- Press L to toggle logs, Q to quit
- Config file: zeroapi_config.json for ports and keys
- Fixes all bugs: auto-creates config, handles IP detection, graceful shutdown
"""

import argparse
import sys
import os
import json
import socket
import time
import threading
import logging
from pathlib import Path

# Ensure repo root in path
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
    "models": ["deepseek", "chatgpt", "gemini", "kimi", "glm", "qwen", "meta", "arena", "auto"]
}

def load_config():
    """Load config from zeroapi_config.json, create default if missing"""
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        # Merge with defaults for missing keys
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
    """Get LAN IP, not 127.0.0.1"""
    try:
        # Connect to external to get LAN IP
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

def get_status_art():
    return r"""
  ____  _____  _   _   _   _  ____
 / ___||_   _|/ \ | | | | | |/ ___|
 \___ \  | | / _ \| | | | | |\___ \
  ___) | | |/ ___ \ |_| |_| | ___) |
 |____/  |_/_/   \_\___/ \___/|____/
    """

# Global state
log_enabled = False
server_thread = None
stop_event = threading.Event()
current_browsers = 0
current_providers = []

def fetch_server_status(port):
    """Try to fetch /health for browser count"""
    global current_browsers, current_providers
    try:
        import httpx
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
        if r.status_code == 200:
            data = r.json()
            current_browsers = data.get("browsers_connected", 0)
            current_providers = data.get("active_providers", [])
    except:
        pass

def ui_loop(cfg):
    global log_enabled
    log_enabled = cfg.get("log_enabled", False)
    port = cfg.get("port", 8000)
    host = cfg.get("host", "0.0.0.0")
    api_key = cfg.get("api_key", "zeroapi")
    lan_ip = get_local_ip()
    
    # Keyboard handling setup
    use_msvcrt = False
    try:
        import msvcrt
        use_msvcrt = True
    except:
        use_msvcrt = False

    # For Unix non-blocking input
    if not use_msvcrt:
        try:
            import tty, termios, select
            has_termios = True
        except:
            has_termios = False
    else:
        has_termios = False

    last_status_fetch = 0
    while not stop_event.is_set():
        # Fetch status every 2 sec
        if time.time() - last_status_fetch > 2:
            fetch_server_status(port)
            last_status_fetch = time.time()

        clear_console()
        print(get_ascii_art())
        print(f"\033[1;36m{'='*62}\033[0m")
        print(f"\033[1;32m  STATUS: RUNNING ✅  |  ZeroAPI v2.6.0 - OpenAI Compatible API\033[0m")
        print(f"\033[1;36m{'='*62}\033[0m")
        print()
        print(f"  \033[1;33m📡 SERVER:\033[0m")
        print(f"     Local:    \033[1;37mhttp://localhost:{port}\033[0m")
        print(f"     LAN:      \033[1;32mhttp://{lan_ip}:{port}\033[0m  \033[0;90m<- use for phone / Smartspacer\033[0m")
        print(f"     Host:     {host}:{port}")
        print()
        print(f"  \033[1;33m🔑 API KEY:\033[0m  \033[1;37m{api_key}\033[0m  \033[0;90m(any string works, this is shown for reference)\033[0m")
        print()
        print(f"  \033[1;33m🤖 MODELS (site names):\033[0m")
        models = cfg.get("models", DEFAULT_CONFIG["models"])
        # Show active vs offline
        for m in models:
            if m == "auto":
                continue
            is_active = m in current_providers
            dot = "\033[1;32m●\033[0m" if is_active else "\033[0;90m○\033[0m"
            status = "\033[1;32mactive\033[0m" if is_active else "\033[0;90moffline\033[0m"
            print(f"     {dot} \033[1;37m{m:<10}\033[0m {status}  \033[0;90m→ /zeroapi/{m}\033[0m")
        print(f"     \033[0;90mAuto: {current_browsers} browsers, {len(current_providers)} providers active\033[0m")
        print()
        print(f"  \033[1;33m🔌 ENDPOINTS:\033[0m")
        print(f"     Dashboard:  http://localhost:{port}/")
        print(f"     API:        http://localhost:{port}/v1/chat/completions")
        print(f"     Models:     http://localhost:{port}/v1/models")
        print(f"     Active:     http://localhost:{port}/api/active-models")
        print(f"     Test:       http://localhost:{port}/test  |  /zeroapi/deepseek")
        print()
        print(f"  \033[1;33m📊 BROWSERS:\033[0m  {current_browsers} connected  |  Providers: {', '.join(current_providers) if current_providers else 'none - open chat tabs'}")
        print()
        logs_status = "\033[1;32mON\033[0m" if log_enabled else "\033[0;90mOFF\033[0m"
        print(f"  \033[1;33m📝 LOGS:\033[0m  {logs_status}  \033[0;90m(Press L to toggle)\033[0m")
        print()
        print(f"\033[1;36m{'='*62}\033[0m")
        print(f"  \033[1;37m[L]\033[0m Toggle logs  |  \033[1;37m[C]\033[0m Clear  |  \033[1;37m[Q]\033[0m Quit  |  \033[1;37m[R]\033[0m Reload config")
        print(f"\033[1;36m{'='*62}\033[0m")
        print()
        print(f"  \033[0;90mExtension: Install from zeroapi-extension/ folder in chrome://extensions (Developer mode)\033[0m")
        print(f"  \033[0;90mThen open chat.deepseek.com / chatgpt.com / gemini.google.com and click 'Use this chat'\033[0m")
        print()

        # Non-blocking key check
        key = None
        if use_msvcrt:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                try:
                    key = ch.decode('utf-8').lower()
                except:
                    key = None
        else:
            # Unix: check stdin with timeout 0.5s
            if has_termios:
                import select
                dr, _, _ = select.select([sys.stdin], [], [], 0.5)
                if dr:
                    # Need to set terminal to raw for single char? For simplicity use input
                    # We'll try to read one char without blocking
                    try:
                        # Save old settings
                        old_settings = termios.tcgetattr(sys.stdin)
                        tty.setcbreak(sys.stdin.fileno())
                        ch = sys.stdin.read(1)
                        key = ch.lower()
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                    except:
                        pass
            else:
                # Fallback: sleep 0.5 and no key handling, user can Ctrl+C
                time.sleep(0.5)
                continue

        if key:
            if key == 'l':
                log_enabled = not log_enabled
                cfg["log_enabled"] = log_enabled
                save_config(cfg)
                # Update loggers
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
        
        time.sleep(0.2)

def run_uvicorn(cfg):
    """Run uvicorn server in thread"""
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

    # Set env vars for config module
    os.environ["ZEROAPI_HOST"] = host
    os.environ["ZEROAPI_PORT"] = str(port)
    os.environ["ZEROAPI_API_KEY"] = cfg.get("api_key", "zeroapi")

    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        log_level=log_level,
        access_log=cfg.get("log_enabled", False)
    )

def main():
    parser = argparse.ArgumentParser(description="ZeroAPI - OpenAI Compatible Server v2.6.0")
    parser.add_argument("--host", help="Host to bind")
    parser.add_argument("--port", type=int, help="Port to bind")
    parser.add_argument("--api-key", help="API key (any string, for display)")
    parser.add_argument("--no-ui", action="store_true", help="Disable UI mode, just run server")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    cfg = load_config()

    # Override from args
    if args.host:
        cfg["host"] = args.host
    if args.port:
        cfg["port"] = args.port
    if args.api_key:
        cfg["api_key"] = args.api_key

    # Also check env vars
    cfg["host"] = os.environ.get("ZEROAPI_HOST", cfg["host"])
    cfg["port"] = int(os.environ.get("ZEROAPI_PORT", cfg["port"]))
    cfg["api_key"] = os.environ.get("ZEROAPI_API_KEY", cfg["api_key"])

    if args.no_ui:
        # Simple mode without UI
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║  ZeroAPI Server v2.6.0 - OpenAI Compatible API               ║
╠══════════════════════════════════════════════════════════════╣
║  API:        http://{cfg['host']}:{cfg['port']}/v1/chat/completions      ║
║  Dashboard:  http://{cfg['host']}:{cfg['port']}/                        ║
║  LAN:        http://{get_local_ip()}:{cfg['port']}/                     ║
║  API Key:    {cfg['api_key']}                                            ║
╚══════════════════════════════════════════════════════════════╝
        """)
        try:
            import uvicorn
            uvicorn.run("server.main:app", host=cfg["host"], port=cfg["port"], reload=args.reload, log_level="info" if cfg["log_enabled"] else "warning")
        except KeyboardInterrupt:
            print("\nShutting down...")
        return

    # UI mode: run server in background thread, UI in main
    clear_console()
    print(get_ascii_art())
    print("\n  Starting server...\n")
    time.sleep(0.5)

    # Start server thread
    t = threading.Thread(target=run_uvicorn, args=(cfg,), daemon=True)
    t.start()

    # Wait a bit for server to start
    time.sleep(2)

    # Run UI loop (blocking, handles keys)
    try:
        ui_loop(cfg)
    except KeyboardInterrupt:
        print("\n\033[1;33mShutting down...\033[0m")
        stop_event.set()
        os._exit(0)

if __name__ == "__main__":
    main()
