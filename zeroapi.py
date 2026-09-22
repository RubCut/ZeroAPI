#!/usr/bin/env python3
"""
ZeroAPI - Main entry point
OpenAI-compatible server with UI mode

Usage:
    python zeroapi.py
    python zeroapi.py --port 8000 --api-key mykey
    python zeroapi.py --no-ui
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_server import main

if __name__ == "__main__":
    main()
