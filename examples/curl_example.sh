#!/bin/bash
# ZeroAPI curl examples

echo "=== ZeroAPI curl examples ==="
echo ""

echo "1. List models:"
curl http://localhost:8000/v1/models | jq

echo ""
echo "2. Health check:"
curl http://localhost:8000/health | jq

echo ""
echo "3. Chat completion (non-streaming):"
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-chat",
    "messages": [
      {"role": "user", "content": "Hello! How are you?"}
    ],
    "temperature": 0.7
  }' | jq

echo ""
echo "4. Chat completion (streaming):"
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Write a haiku about AI"}
    ],
    "stream": true
  }'

echo ""
echo "5. With OpenAI API compatibility (using api key header):"
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer zeroapi" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "user", "content": "What is the capital of France?"}
    ]
  }' | jq
