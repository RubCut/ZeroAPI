#!/bin/bash
cd "$(dirname "$0")"

echo "Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "Python3 not found! Install Python 3.9+"
    exit 1
fi

echo "Installing dependencies..."
python3 -m pip install -r requirements.txt --quiet

echo ""
echo "Starting ZeroAPI with UI mode..."
echo "Config: zeroapi_config.json (edit to change port/key)"
echo ""

python3 zeroapi.py
