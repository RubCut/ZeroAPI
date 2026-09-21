# ZeroAPI Extension - OpenAI Compatible Browser Bridge

This extension turns ChatGPT, DeepSeek, Gemini, Kimi, GLM, Qwen, Arena or Meta AI into an OpenAI-compatible API server.

Based on [ZeroScript](https://github.com/sebattfg/ZeroScript-Free) by sebattfg.

## How it works

```
OpenAI Client (your app) -> ZeroAPI Server (localhost:8000) -> WebSocket -> Browser Extension -> AI Chat (ChatGPT / DeepSeek / etc.) -> Response back
```

The extension runs inside the AI chat page. When the server receives an API request, it forwards it to the extension, which types the prompt into the chat and captures the AI's response.

## Setup

### 1. Install dependencies and run server

```bash
pip install -r ../requirements.txt
python ../run_server.py
```

Or on Windows double-click `start_api.bat`.

Server will start on http://localhost:8000

### 2. Install extension

- Go to `edge://extensions` or `chrome://extensions`
- Enable Developer mode
- Click Load unpacked
- Select the `zeroapi-extension` folder

### 3. Open AI chat

Go to https://chat.deepseek.com (recommended), https://chatgpt.com, https://gemini.google.com, etc. The extension will auto-connect to the server.

Check popup: should show "API Server: Connected"

### 4. Use OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="zeroapi"
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

## Models / Provider routing

Model name determines which browser tab to use:

- `deepseek-chat`, `deepseek-reasoner` -> DeepSeek tab
- `gpt-4o`, `gpt-4`, `gpt-3.5-turbo`, `chatgpt` -> ChatGPT tab
- `gemini-2.0-flash`, `gemini-1.5-pro` -> Gemini tab
- `kimi-k2`, `kimi` -> Kimi tab
- `glm-4`, `glm` -> GLM tab
- `qwen-turbo`, `qwen` -> Qwen tab
- `llama-3`, `meta` -> Meta AI tab
- `arena` -> Arena tab
- `auto` -> any available tab

If no tab for requested provider is open, it will use any available tab.

## API Endpoints

- `GET /` - Dashboard
- `GET /v1/models` - List models
- `POST /v1/chat/completions` - Chat completions (streaming and non-streaming)
- `POST /v1/completions` - Text completions
- `GET /health` - Health check
- `GET /docs` - Swagger UI
- `WS /ws` - WebSocket for extension

## Streaming

Supports OpenAI streaming via SSE:

```python
stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Count to 5"}],
    stream=True
)

for chunk in stream:
    print(chunk.choices[0].delta.content, end="")
```

## Legacy Roblox mode

The extension still supports the original ZeroScript Roblox mode alongside API mode. If you also run the legacy bridge (`bridge.py` on 17613), the Roblox agent will work as before.

To run both simultaneously:
```bash
python -m server.combined
```

## Troubleshooting

- **No browsers connected**: Open chat.deepseek.com or chatgpt.com with extension installed
- **API Server offline in popup**: Run `python run_server.py` and keep window open
- **Timeout**: AI provider may be slow, try again or check browser tab is visible (not minimized)
- **Model not found**: Use `auto` or check `/v1/models`

## License

GPL-3.0 - Based on ZeroScript
