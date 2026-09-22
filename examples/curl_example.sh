#!/bin/bash
# ZeroAPI v2.4.0 - curl examples
# Site names as models: deepseek, chatgpt, gemini, etc.

BASE="http://localhost:8000/v1"
KEY="zeroapi"

echo "=== ZeroAPI v2.4.0 - curl examples ==="
echo ""

echo "1. List models (simple site names):"
curl -s $BASE/models | python -m json.tool | head -20
echo ""

echo "2. Active models only:"
curl -s $BASE/models?active_only=true | python -m json.tool | head -20
echo ""

echo "3. Test API like zeroapi/deepseek:"
curl -s http://localhost:8000/zeroapi/deepseek | python -m json.tool
echo ""

echo "4. Chat completion with deepseek:"
curl -s $BASE/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek",
    "messages": [{"role": "user", "content": "Hello! Who are you?"}]
  }' | python -m json.tool
echo ""

echo "5. Chat with file (image):"
# Fake base64 for demo
IMG=$(echo -n "fake" | base64)
curl -s $BASE/chat/completions \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"gemini\",
    \"messages\": [{
      \"role\": \"user\",
      \"content\": [
        {\"type\": \"text\", \"text\": \"Describe image\"},
        {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/jpeg;base64,$IMG\"}}
      ]
    }]
  }" | python -m json.tool
echo ""

echo "Config: zeroapi_config.json"
echo "Dashboard: http://localhost:8000/"
echo "Test page: http://localhost:8000/test"
