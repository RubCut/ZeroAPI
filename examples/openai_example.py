"""
ZeroAPI v2.4.0 - OpenAI SDK Example
Site names as models: deepseek, chatgpt, gemini, etc.
File support: any file type, auto-cleared

Prerequisites:
1. Run ZeroAPI server: python zeroapi.py (UI mode)
2. Install ZeroAPI extension from zeroapi-extension/ folder
3. Open chat.deepseek.com or chatgpt.com or gemini.google.com, click "Use this chat"
"""

from openai import OpenAI
import base64

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="zeroapi"  # any string, see zeroapi_config.json
)

print("=== ZeroAPI v2.4.0 Example ===\n")

# List models - now simple site names
print("Available models (site names):")
try:
    models = client.models.list()
    for model in models.data:
        print(f"  - {model.id}")
except Exception as e:
    print(f"Failed: {e}")
    exit(1)

print("\n" + "="*50 + "\n")

# Simple chat with site-name model
print("1. Chat with deepseek (site name):")
try:
    response = client.chat.completions.create(
        model="deepseek",
        messages=[
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello! Short poem about coding."}
        ]
    )
    print(f"Model: {response.model}\n{response.choices[0].message.content}\nUsage: {response.usage}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "="*50 + "\n")

# File support example
print("2. File support (any type, auto-cleared):")
try:
    # Create fake image for demo
    fake_data = base64.b64encode(b"fake image").decode()
    response = client.chat.completions.create(
        model="gemini",  # Gemini best for files
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{fake_data}"}}
            ]
        }]
    )
    print(f"Response: {response.choices[0].message.content[:200]}")
except Exception as e:
    print(f"Error (no browser?): {e}")

print("\n" + "="*50 + "\n")

# Streaming
print("3. Streaming with auto (any active tab):")
try:
    stream = client.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": "Count 1 to 3"}],
        stream=True
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()
except Exception as e:
    print(f"Error: {e}")

print("\n=== Done ===")
print("Config: zeroapi_config.json for port/key")
print("Test: http://localhost:8000/test")
