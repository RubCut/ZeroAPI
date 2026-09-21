#!/bin/bash
echo ""
echo "================================================"
echo " ZeroAPI Server - OpenAI Compatible API"
echo " Based on ZeroScript"
echo "================================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "Python3 not found! Install Python 3.9+"
    exit 1
fi

echo "Installing dependencies..."
python3 -m pip install -r requirements.txt --quiet

echo ""
echo "Starting ZeroAPI server on http://localhost:8000"
echo "Dashboard: http://localhost:8000/"
echo "API: http://localhost:8000/v1/chat/completions"
echo "Docs: http://localhost:8000/docs"
echo ""
echo "Steps:"
echo "1. Keep this window open"
echo "2. Install extension from zeroapi-extension/ folder in chrome://extensions"
echo "3. Open chat.deepseek.com or chatgpt.com"
echo "4. Use OpenAI SDK with base_url=http://localhost:8000/v1"
echo ""

python3 run_server.py
