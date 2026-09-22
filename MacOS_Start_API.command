#!/bin/bash
cd "$(dirname "$0")"

clear
echo "Starting ZeroAPI with UI mode..."

if ! command -v python3 &> /dev/null; then
    echo "Python3 not found! Install from python.org"
    read -p "Press Enter to exit..."
    exit 1
fi

python3 -m pip install -r requirements.txt --quiet
python3 zeroapi.py

read -p "Press Enter to exit..."
