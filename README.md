# ZeroAPI - OpenAI Compatible Server from ZeroScript

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-GPL--3.0-blue)
![Version](https://img.shields.io/badge/version-2.0.0-brightgreen)

**ZeroAPI** transforms [ZeroScript](https://github.com/sebattfg/ZeroScript-Free) (Roblox Studio AI agent) into an **OpenAI-compatible API server** that routes requests through your browser's AI chats.

Use ChatGPT, DeepSeek, Gemini, Kimi, GLM, Qwen, Arena or Meta AI **as if they were OpenAI API**, without API keys. Your browser is the engine.

> 🌐 Original ZeroScript: [zerodev.tools/zeroscript](https://zerodev.tools/zeroscript) - Forked and transformed into OpenAI API server.

## What is this?

**Original ZeroScript:**
```
AI Chat (browser) -> Extension -> Bridge -> Roblox Studio
```

**ZeroAPI (this fork):**
```
Your App (OpenAI SDK) -> ZeroAPI Server (localhost:8000) -> Extension -> AI Chat (browser) -> Response
```

- **OpenAI-compatible**: Works with any OpenAI SDK, LangChain, OpenWebUI, etc.
- **No API keys**: Uses your existing ChatGPT / DeepSeek / Gemini logged-in sessions
- **Multi-provider**: Routes via model name to different browser tabs
- **Streaming**: Full SSE streaming support
- **Browser automation**: Based on ZeroScript's proven provider abstraction
- **Legacy support**: Still keeps Roblox Studio MCP tools as optional

## Supported Providers

| Provider | Site | Model IDs |
|----------|------|-----------|
| **DeepSeek** (recommended) | chat.deepseek.com | `deepseek-chat`, `deepseek-reasoner` |
| **ChatGPT** | chatgpt.com | `gpt-4o`, `gpt-4`, `gpt-3.5-turbo`, `o1` |
| **Gemini** | gemini.google.com | `gemini-2.0-flash`, `gemini-1.5-pro` |
| **Kimi** | kimi.ai | `kimi-k2`, `kimi` |
| **GLM** | chat.z.ai | `glm-4`, `glm` |
| **Qwen** | chat.qwen.ai | `qwen-turbo`, `qwen` |
| **Meta AI** | meta.ai | `llama-3`, `meta` |
| **Arena** | arena.ai | `arena` |

Use `auto` to route to any available browser tab.

## Quick Start

### 1. Install & Run Server

**Windows:**
Double-click `start_api.bat`

**macOS:**
Double-click `MacOS_Start_API.command` (first time: System Settings > Privacy & Security > Open Anyway)

**Manual:**
```bash
pip install -r requirements.txt
python run_server.py
```

Server starts at:
- Dashboard: http://localhost:8000/
- API: http://localhost:8000/v1/chat/completions
- Docs: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/ws

### 2. Install Browser Extension

- Go to `chrome://extensions` or `edge://extensions`
- Enable **Developer mode**
- Click **Load unpacked**
- Select `zeroapi-extension` folder

### 3. Open AI Chat

Open https://chat.deepseek.com or https://chatgpt.com - extension auto-connects. Check popup shows "API Server: Connected".

### 4. Use OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="zeroapi"  # any string
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "Hello! Write a poem about AI"}]
)

print(response.choices[0].message.content)
```

Streaming:

```python
stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Count to 5"}],
    stream=True
)

for chunk in stream:
    print(chunk.choices[0].delta.content, end="")
```

curl:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard UI |
| GET | `/v1/models` | List models |
| GET | `/v1/models/{id}` | Get model |
| POST | `/v1/chat/completions` | Chat completions (OpenAI compatible) |
| POST | `/v1/completions` | Text completions |
| GET | `/health` | Health check |
| GET | `/api/status` | Detailed status |
| WS | `/ws` | WebSocket for extension |
| GET | `/docs` | Swagger UI |

### OpenAI Compatibility

Supports:
- `model`, `messages`, `temperature`, `max_tokens`, `stream`
- `tools` / `tool_choice` (passed through, parsing via ZeroScript parser if needed)
- `system`, `user`, `assistant` roles
- Streaming via SSE (`data: {...}\n\n` + `data: [DONE]`)

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Your App       │      │  ZeroAPI Server  │      │  Browser        │
│  OpenAI SDK     │─HTTP─▶  FastAPI (8000)  │─WS──▶  Extension      │
│                 │      │  /v1/chat/...    │      │  Content Script │
└─────────────────┘      └──────────────────┘      └────────┬────────┘
                                                            │ DOM
                                                   ┌────────▼────────┐
                                                   │  AI Chat Page   │
                                                   │  DeepSeek/GPT/  │
                                                   │  Gemini/etc     │
                                                   └─────────────────┘
```

**Core components (from ZeroScript):**
- `server/ws_manager.py` - WebSocket manager for browser clients (adapted from bridge.py)
- `server/main.py` - FastAPI OpenAI-compatible server
- `server/mcp_manager.py` - MCP tool manager (kept for Roblox compatibility)
- `zeroapi-extension/core/api_handler.js` - New: handles chat requests via ZSProvider
- `zeroapi-extension/providers/*.js` - Provider abstraction (DeepSeek, ChatGPT, etc.)
- `zeroapi-extension/core/config.js`, `parser.js` - ZeroScript core (tool parsing)

## Legacy Roblox Mode

This fork keeps original ZeroScript functionality:

1. Run legacy bridge: `python bridge.py` (port 17613)
2. Install `zeroscript-extension` (original)
3. Open Roblox Studio + enable MCP
4. Use AI chat to control Studio

Or run both simultaneously:
```bash
python -m server.combined  # runs API server (8000) + legacy bridge (17613)
```

## Examples

See `examples/`:

- `openai_example.py` - OpenAI SDK usage
- `curl_example.sh` - curl examples

## Docker

```bash
docker build -t zeroapi .
docker run -p 8000:8000 -p 17613:17613 zeroapi

# Or with compose
docker-compose up -d
```

Dashboard at http://localhost:8000/

## Testing

No browser required for unit tests:

```bash
pip install -r requirements.txt
python tests/test_server.py
# or
pytest tests/
```

## Configuration

Environment variables:

- `ZEROAPI_PORT` - HTTP port (default 8000)
- `ZEROAPI_HOST` - Host (default 0.0.0.0)
- `ZS_BRIDGE_PORT` - Legacy bridge port (default 17613)

## Documentation

- `docs/API.md` - Full OpenAI API spec, routing, WS protocol
- `docs/TRANSFORMATION.md` - How ZeroScript was transformed into ZeroAPI (RU)
- `zeroapi-extension/README.md` - Extension details

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No browsers connected | Open chat.deepseek.com with extension installed |
| API Server offline in popup | Run `python run_server.py` |
| 503 No browser | Open AI chat tab, check extension popup |
| Timeout | Provider slow, tab minimized? Keep tab visible |
| Model not found | Use `auto` or check `/v1/models` |

## Development

```bash
pip install -r requirements.txt
python run_server.py --reload  # auto-reload

# Test
python examples/openai_example.py
```

## Credits

- Original ZeroScript by [sebattfg](https://github.com/sebattfg) - GPL-3.0
- Multi-provider support, MCP idea from javnpa
- macOS support from archivealf
- ZeroAPI transformation: OpenAI API layer + browser bridge

## License

GPL-3.0 - Same as original ZeroScript

---

**Disclaimer:** This tool automates browser interaction with AI chat sites. Use responsibly and respect each provider's Terms of Service. No API keys are bypassed - it uses your existing logged-in sessions.
