"""
ZeroAPI - OpenAI SDK Example
Shows how to use ZeroAPI as a drop-in replacement for OpenAI API.

Prerequisites:
1. Run ZeroAPI server: python run_server.py
2. Install ZeroAPI extension in Chrome/Edge
3. Open chat.deepseek.com or chatgpt.com in browser
4. Install openai: pip install openai
"""

from openai import OpenAI

# Configure client to use ZeroAPI server
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="zeroapi"  # any string works, auth is optional
)

print("=== ZeroAPI Example ===")
print("Testing connection to ZeroAPI server...\n")

# List models
print("Available models:")
try:
    models = client.models.list()
    for model in models.data:
        print(f"  - {model.id} (by {model.owned_by})")
except Exception as e:
    print(f"Failed to list models: {e}")
    print("Is the server running? python run_server.py")
    exit(1)

print("\n" + "="*50 + "\n")

# Simple chat completion
print("1. Simple chat completion (non-streaming):")
try:
    response = client.chat.completions.create(
        model="deepseek-chat",  # will route to DeepSeek tab, or any tab if not found
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello! Write a short poem about coding."}
        ],
        temperature=0.7,
        max_tokens=200
    )
    print(f"Model: {response.model}")
    print(f"Response: {response.choices[0].message.content}")
    print(f"Usage: {response.usage}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "="*50 + "\n")

# Streaming chat completion
print("2. Streaming chat completion:")
try:
    stream = client.chat.completions.create(
        model="auto",  # auto-select any available browser
        messages=[
            {"role": "user", "content": "Count from 1 to 5 slowly, one number per line."}
        ],
        stream=True
    )
    
    print("Streaming response: ", end="", flush=True)
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print("\n")
except Exception as e:
    print(f"Streaming error: {e}")

print("\n" + "="*50 + "\n")

# Using different providers via model name
print("3. Provider routing via model name:")
print("   - deepseek-chat -> DeepSeek tab")
print("   - gpt-4o -> ChatGPT tab")
print("   - gemini-2.0-flash -> Gemini tab")
print("   - kimi-k2 -> Kimi tab")
print("   - auto -> any available tab")
print("\nExample with forced provider:")

try:
    # You can also force provider via extra parameter (if supported)
    # For now, model name determines provider
    response = client.chat.completions.create(
        model="gpt-4o",  # will try to find ChatGPT tab
        messages=[
            {"role": "user", "content": "What is 2+2? Answer very briefly."}
        ]
    )
    print(f"Response from {response.model}: {response.choices[0].message.content}")
except Exception as e:
    print(f"Error (maybe no ChatGPT tab open?): {e}")
    print("Open https://chatgpt.com in browser with extension")

print("\n=== Done ===")
