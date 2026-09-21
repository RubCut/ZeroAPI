#!/usr/bin/env python3
"""
ZeroAPI Server Runner
Launches the OpenAI-compatible API server.

Usage:
    python run_server.py
    python run_server.py --port 8000 --host 0.0.0.0
"""

import argparse
import sys
import os

# Ensure repo root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import uvicorn
except ImportError:
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    import uvicorn

from server.config import HOST, PORT

def main():
    parser = argparse.ArgumentParser(description="ZeroAPI - OpenAI Compatible Server")
    parser.add_argument("--host", default=HOST, help=f"Host to bind (default: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port to bind (default: {PORT})")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  ZeroAPI Server v2.0.0 - OpenAI Compatible API               ║
║  Based on ZeroScript by sebattfg                             ║
╠══════════════════════════════════════════════════════════════╣
║  API:        http://{args.host}:{args.port}/v1/chat/completions      ║
║  Dashboard:  http://{args.host}:{args.port}/                        ║
║  WebSocket:  ws://{args.host}:{args.port}/ws                         ║
║  Docs:       http://{args.host}:{args.port}/docs                     ║
╠══════════════════════════════════════════════════════════════╣
║  1. Install extension from zeroapi-extension/ folder         ║
║  2. Open chat.deepseek.com or chatgpt.com                    ║
║  3. Use OpenAI SDK with base_url=http://localhost:{args.port}/v1  ║
╚══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )

if __name__ == "__main__":
    main()
