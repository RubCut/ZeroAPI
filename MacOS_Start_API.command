#!/bin/bash
cd "$(dirname "$0")"
echo ""
echo "================================================"
echo " ZeroAPI Server - OpenAI Compatible API"
echo " Based on ZeroScript"
echo "================================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "Python3 not found! Install from python.org"
    read -p "Press Enter to exit..."
    exit 1
fi

echo "Installing dependencies..."
python3 -m pip install -r requirements.txt --quiet

echo ""
echo "Starting ZeroAPI server on http://localhost:8000"
echo "Dashboard: http://localhost:8000/"
echo ""

python3 run_server.py

read -p "Press Enter to exit..."
