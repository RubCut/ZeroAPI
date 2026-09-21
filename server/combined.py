"""
Combined Server - Runs both ZeroAPI (8000) and legacy ZeroScript bridge (17613) simultaneously
Use this if you want both OpenAI API and Roblox Studio tools at same time.
"""
import asyncio
import threading
import sys
import os

# Add root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.config import HOST, PORT, BRIDGE_PORT

def run_legacy_bridge():
    """Run legacy bridge.py on 17613"""
    print(f"[combined] Starting legacy bridge on {BRIDGE_PORT}...")
    # Import and run bridge main
    import bridge
    # Override port if needed
    bridge.PORT = BRIDGE_PORT
    try:
        asyncio.run(bridge.main())
    except Exception as e:
        print(f"[combined] Legacy bridge error: {e}")

def run_api_server():
    """Run ZeroAPI server on 8000"""
    import uvicorn
    print(f"[combined] Starting ZeroAPI server on {PORT}...")
    uvicorn.run("server.main:app", host=HOST, port=PORT, log_level="info")

if __name__ == "__main__":
    # Start legacy bridge in background thread
    legacy_thread = threading.Thread(target=run_legacy_bridge, daemon=True)
    legacy_thread.start()

    # Run API server in main thread (blocking)
    run_api_server()
