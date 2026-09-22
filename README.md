# ZeroAPI ⚡ — OpenAI Compatible Browser Bridge

**Turn ChatGPT, DeepSeek, Gemini, Kimi, GLM, Qwen, Meta AI, Arena into an OpenAI-compatible API server.**

No API keys needed — uses your logged-in browser sessions. Your browser is the engine.

![Version](https://img.shields.io/badge/version-2.8.0-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-GPL--3.0-blue)

> Based on ZeroScript by sebattfg, transformed into pure API server. No Roblox remnants.

## Features

- **OpenAI-compatible**: Works with OpenAI SDK, LangChain, OpenWebUI, opencode, AI News plugin, etc.
- **Site names as models**: `deepseek`, `chatgpt`, `gemini`, `kimi`, `glm`, `qwen`, `meta`, `arena`, `auto`
- **File support**: Any file type (images, PDFs, docs) via `image_url` or `file` parts, auto-cleared after insertion
- **Auto-switch tabs**: When different model requested (e.g. `gemini` but active is `deepseek`), extension auto-switches to matching tab, focuses it, shows toast — configurable in popup
- **Tunnel detection + auto-start**: Auto-detects public URLs from ngrok, Cloudflare, localtunnel, bore — shows in UI and `/health`; can auto-start tunnel from config `tunnel.enabled=true provider=cloudflare auto_start=true`
- **UI mode**: Clears console, huge ZeroAPI status, shows LAN IP + API key + tunnel URLs, press L for logs, T for tunnels, S to start/stop tunnel
- **Config file**: `zeroapi_config.json` for ports, keys, models, auto-switch, tunnels, tunnel autostart

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

### 1. Run Server (UI Mode)

**Windows:** Double-click `start_api.bat`

**macOS/Linux:** `./start_api.sh` or `python zeroapi.py`

UI will show:

```
 ███████╗███████╗██████╗  ██████╗  █████╗ ██████╗ ██╗
 ...

  STATUS: RUNNING ✅  |  ZeroAPI v2.8.0

  📡 SERVER:
     Local:  http://localhost:8000
     LAN:    http://192.168.1.50:8000  <- use for phone
  🌐 TUNNELS (public URLs):
     ● https://abc-123.trycloudflare.com (cloudflare)
       API: https://abc-123.trycloudflare.com/v1/chat/completions
     ● https://xyz.ngrok.io (ngrok)
  🔑 API KEY: zeroapi
  🤖 MODELS: deepseek active, gemini offline...
  [L] Toggle logs | [Q] Quit | [T] Show tunnels
```

Config: edit `zeroapi_config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8000,
  "api_key": "zeroapi",
  "log_enabled": false,
  "tunnel_url": "https://xxx.trycloudflare.com",
  "auto_switch_tabs": true,
  "models": ["deepseek", "chatgpt", "gemini", ...]
}
```

### 2. Install Extension

- `chrome://extensions` → Developer mode ON → Load unpacked → select `zeroapi-extension/` folder
- Only this extension needed

### 3. Open AI Chat

Open https://chat.deepseek.com or https://chatgpt.com or https://gemini.google.com

Extension bar shows: `● ZeroAPI [deepseek] ✓ Active` — click `Use this chat` if not active.

With **auto-switch ON** (default), open multiple chats — extension will auto-switch when different model requested.

### 4. Use API

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="zeroapi")

# Simple site-name models — auto-switches tabs
resp = client.chat.completions.create(model="deepseek", messages=[{"role": "user", "content": "Hello!"}])
print(resp.choices[0].message.content)

# Will auto-switch to Gemini tab if open
resp = client.chat.completions.create(model="gemini", messages=[{"role": "user", "content": "Hi Gemini"}])

# With files (any type, auto-cleared)
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

### Tunnels — Public URL 🌐

Make your local API public:

```bash
# ngrok (auto-detected via http://127.0.0.1:4040/api/tunnels)
ngrok http 8000

# Cloudflare Tunnel (detected via logs/env/files)
cloudflared tunnel --url http://localhost:8000
# Quick tunnel URL like https://xxx.trycloudflare.com will be auto-detected

# LocalTunnel
lt --port 8000
npx localtunnel --port 8000

# Bore
bore local 8000 --to bore.pub

# Or manual in zeroapi_config.json
{
  "tunnel_url": "https://your-custom-domain.com",
  "external_urls": ["https://backup-url.com"]
}

# Or env vars
ZEROAPI_TUNNEL_URL=https://xxx.trycloudflare.com python zeroapi.py
TUNNEL_URL=https://xxx.ngrok.io python zeroapi.py
```

Then UI shows:
```
🌐 TUNNELS:
   ● https://abc.trycloudflare.com (cloudflare)
     API: https://abc.trycloudflare.com/v1/chat/completions
```

API endpoints:
- `GET /api/tunnels` — list all detected tunnels
- `GET /health` — includes `tunnels`, `tunnel_urls`, `public_url`

Use tunnel URL in SDK:
```python
client = OpenAI(base_url="https://abc.trycloudflare.com/v1", api_key="x")
```

### AI News Smartspacer Plugin

- Base URL: `http://192.168.1.XX:8000/v1` or tunnel URL `https://xxx.trycloudflare.com/v1`
- Enable **Allow unencrypted connections** for LAN, or use https tunnel for encrypted
- Fetch models → `deepseek`, `chatgpt`, `gemini`...

See `docs/AI_NEWS_PLUGIN_INTEGRATION.md`

## API Endpoints

- `GET /` — Dashboard with browsers + tunnels + auto-switch
- `GET /v1/models` — 9 simple models
- `GET /v1/models/all` — full 21 models
- `GET /api/active-models` — active + browsers
- `GET /api/tunnels` — **NEW** list tunnels (ngrok, cloudflare, lt, bore) + public URLs + how-to
- `GET /zeroapi/{model}` — test API
- `GET /health` — health with `tunnels`, `tunnel_urls`, `public_url`, `available_providers`, `auto_switch`
- `POST /v1/chat/completions` — OpenAI compatible with auto-switch

## Extension Bar & Auto-Switch

- Open multiple chats, extension auto-switches when different model requested
- Bar flashes green, shows `↔️ Switched from deepseek`
- Popup toggles: 🔄 Auto-switch, 👁️ Auto-focus, 🔔 Notify
- Server `/health` returns `available_providers` (all open tabs)

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
  "auto_focus_tab": true,
  "notify_on_switch": true,
  "tunnel_auto_detect": true,
  "tunnel_url": "",
  "public_url": "",
  "external_urls": []
}
```

## What's New

### v2.8.0 — Tunnel Auto-start 🚀 + Detection 🌐
- **NEW: Auto-start tunnel from config** — set in `zeroapi_config.json` to automatically start tunnel when server starts:
```json
{
  "tunnel": {
    "enabled": true,
    "provider": "cloudflare",
    "auto_start": true,
    "port": null,
    "subdomain": "",
    "custom_command": "",
    "extra_args": ""
  }
}
```
  - Providers: `cloudflare` (`cloudflared tunnel --url http://localhost:8000`), `ngrok` (`ngrok http 8000`), `localtunnel` (`lt --port 8000`), `bore` (`bore local 8000 --to bore.pub`), `custom` (your own command)
  - CLI: `--tunnel-provider cloudflare --tunnel-autostart`
  - Env: `ZEROAPI_TUNNEL_PROVIDER=cloudflare`
  - UI: shows `🚀 Starting tunnel: provider=cloudflare port=8000`, `🌐 Tunnel detected: https://xxx.trycloudflare.com`, S key to manually start/stop, T for details, status `starting/running/failed`
  - Saves URL to `tunnel_url.txt` and `/tmp/cloudflared.log` and env `ZEROAPI_TUNNEL_URL` for auto-detection
  - Process managed: auto-restart check, stops on Q quit
  - Server `/api/tunnels` now shows `autostart` config + `POST /api/tunnels/start` to get command
- **Tunnel Detection** (v2.7.0): auto-detect ngrok via 4040 API, Cloudflare via logs/process/env/files, lt, bore
- UI shows 🌐 TUNNELS with public URLs + API endpoints, T key for details
- Dashboard new card with tunnel table, `/api/tunnels` endpoint, `/health` includes tunnels
- Config `tunnel_url`, `public_url`, `external_urls`, `tunnel_auto_detect`, CLI `--tunnel-url`

### v2.6.0 — Auto-switch Tabs
- Extension auto-switches between tabs when different models required
- Focus + toast, configurable, server shows available_providers

### v2.5.0 — Clean Release + UI
- Removed ZeroScript files, only our batch + extension in releases
- UI mode with huge logo, LAN IP, key, L toggle logs, config for ports/keys

## License

GPL-3.0 — Based on ZeroScript by sebattfg
