# ZeroAPI — OpenAI Compatible Browser Bridge

**Turn ChatGPT, DeepSeek, Gemini, Kimi, GLM, Qwen, Meta AI, Arena into an OpenAI-compatible API server.**

No API keys needed — uses your logged-in browser sessions. Your browser is the engine.

![Version](https://img.shields.io/badge/version-2.8.1-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-GPL--3.0-blue)

> Based on ZeroScript by sebattfg, transformed into pure API server.

## Features

- **OpenAI-compatible**: Works with OpenAI SDK, LangChain, OpenWebUI, opencode, AI News plugin, etc.
- **Site names as models**: `deepseek`, `chatgpt`, `gemini`, `kimi`, `glm`, `qwen`, `meta`, `arena`, `auto`
- **File support**: Any file type (images, PDFs, docs) via `image_url` or `file` parts, auto-cleared after insertion
- **Auto-switch tabs**: When different model requested, extension auto-switches to matching tab
- **Tunnel detection + auto-start**: Auto-detects public URLs from ngrok, Cloudflare, localtunnel, bore; can auto-start tunnel from config
- **Compact professional UI**: Clean console, network IP, public URLs, models, controls
- **Config file**: `zeroapi_config.json` for ports, keys, models, tunnels

## Supported Models

| Model ID | Provider | Site |
|----------|----------|------|
| `deepseek` | DeepSeek | chat.deepseek.com |
| `chatgpt` | ChatGPT | chatgpt.com |
| `gemini` | Gemini | gemini.google.com |
| `kimi` | Kimi K2 | kimi.ai |
| `glm` | GLM-4 | chat.z.ai |
| `qwen` | Qwen Turbo | chat.qwen.ai |
| `meta` | Meta AI | meta.ai |
| `arena` | Arena | arena.ai |
| `auto` | Any active tab | — |

Full aliases also work: `deepseek-chat`, `gpt-4o`, `gemini-2.0-flash`, etc.

## Quick Start

### 1. Run Server

**Windows:** Double-click `start_api.bat`

**macOS/Linux:** `./start_api.sh` or `python zeroapi.py`

Compact UI:

```
 ZeroAPI v2.8.1 | OpenAI Compatible API Server
 ------------------------------------------------------------
 Status: RUNNING | Port: 8000 | Browsers: 2
 ------------------------------------------------------------

 Server
   Local:   http://localhost:8000
   Network: http://192.168.1.50:8000
   Public:  https://abc-123.trycloudflare.com [cloudflare]
            https://abc-123.trycloudflare.com/v1/chat/completions

 Auth
   API Key: zeroapi

 Models
   deepseek [active]  gemini [active]  chatgpt  kimi  glm  qwen  meta  arena
   2 browsers, 2 providers, auto-switch: on

 Endpoints
   /  /v1/models  /v1/chat/completions  /api/tunnels  /health
   Dashboard: http://localhost:8000/

 Logs: OFF | Tunnels: 1 | Providers: deepseek, gemini
 ------------------------------------------------------------
 [L] Logs  [T] Tunnels  [S] Tunnel Start/Stop  [R] Reload  [C] Clear  [Q] Quit
 ------------------------------------------------------------
```

Config: edit `zeroapi_config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8000,
  "api_key": "zeroapi",
  "tunnel": {
    "enabled": true,
    "provider": "cloudflare",
    "auto_start": true
  }
}
```

### 2. Install Extension

- `chrome://extensions` -> Developer mode ON -> Load unpacked -> select `zeroapi-extension/` folder

### 3. Open AI Chat

Open https://chat.deepseek.com or https://chatgpt.com or https://gemini.google.com

Extension shows `ZeroAPI [deepseek] Active` — click `Use this chat` if not active.

### 4. Use API

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="zeroapi")

resp = client.chat.completions.create(model="deepseek", messages=[{"role": "user", "content": "Hello!"}])
print(resp.choices[0].message.content)

# Auto-switches to Gemini tab if open
resp = client.chat.completions.create(model="gemini", messages=[{"role": "user", "content": "Hi Gemini"}])
```

With files:

```python
import base64
with open("image.jpg","rb") as f:
    b64 = base64.b64encode(f.read()).decode()

resp = client.chat.completions.create(
    model="gemini",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]
    }]
)
```

### Tunnels — Public URL

Make your local API public:

```bash
# ngrok (auto-detected via http://127.0.0.1:4040/api/tunnels)
ngrok http 8000

# Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8000

# LocalTunnel
lt --port 8000

# Bore
bore local 8000 --to bore.pub

# Or autostart via config
{
  "tunnel": {
    "enabled": true,
    "provider": "cloudflare",
    "auto_start": true
  }
}

# Or env
ZEROAPI_TUNNEL_URL=https://xxx.trycloudflare.com python zeroapi.py
```

UI shows:

```
   Public:  https://abc.trycloudflare.com [cloudflare]
            https://abc.trycloudflare.com/v1/chat/completions
```

API:
- `GET /api/tunnels` — list tunnels
- `GET /health` — includes `tunnels`, `public_url`

## API Endpoints

- `GET /` — Dashboard
- `GET /v1/models` — 9 simple models
- `GET /v1/models/all` — full 21 models
- `GET /api/active-models` — active + browsers
- `GET /api/tunnels` — list tunnels + autostart config
- `POST /api/tunnels/start` — get start command
- `GET /health` — health with tunnels, providers
- `POST /v1/chat/completions` — OpenAI compatible

## Config

`zeroapi_config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8000,
  "api_key": "zeroapi",
  "log_enabled": false,
  "auto_clear_files": true,
  "auto_switch_tabs": true,
  "tunnel_auto_detect": true,
  "tunnel": {
    "enabled": false,
    "provider": "cloudflare",
    "auto_start": false,
    "port": null,
    "subdomain": "",
    "custom_command": "",
    "extra_args": ""
  }
}
```

Providers for tunnel: `cloudflare`, `ngrok`, `localtunnel`, `bore`, `custom`

## What's New

### v2.8.1 — Compact Professional UI
- Removed emojis, smaller header, product-ready layout
- Same autostart features as v2.8.0 but cleaner
- UI: `ZeroAPI v2.8.1 | OpenAI Compatible API Server` + compact sections

### v2.8.0 — Tunnel Auto-start + Detection
- Auto-start tunnel from config `tunnel.enabled=true provider=cloudflare auto_start=true`
- Detection: ngrok via 4040 API, cloudflare via logs/env, lt, bore
- UI T tunnels, S start/stop, `/api/tunnels` endpoint

### v2.6.0 — Auto-switch Tabs
- Extension auto-switches between tabs when different models required

### v2.5.0 — Clean Release + UI
- Removed ZeroScript remnants, only our batch + extension in releases

## License

GPL-3.0 — Based on ZeroScript by sebattfg
