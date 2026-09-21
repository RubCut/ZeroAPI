#!/usr/bin/env python3
"""
ZeroAPI - Main entry point
OpenAI-compatible server based on ZeroScript

Usage:
    python zeroapi.py
    python zeroapi.py --port 8000
    python zeroapi.py --help
"""

import sys
import os

# Add current dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run server
from run_server import main

if __name__ == "__main__":
    main()
