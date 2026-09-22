# ZeroAPI ⚡ — OpenAI Compatible Browser Bridge

**Turn ChatGPT, DeepSeek, Gemini, Kimi, GLM, Qwen, Meta AI, Arena into an OpenAI-compatible API server.**

No API keys needed — uses your logged-in browser sessions. Your browser is the engine.

![Version](https://img.shields.io/badge/version-2.6.0-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-GPL--3.0-blue)

> Based on ZeroScript by sebattfg, transformed into pure API server. No Roblox remnants.

## Features

- **OpenAI-compatible**: Works with OpenAI SDK, LangChain, OpenWebUI, opencode, AI News plugin, etc.
- **Site names as models**: `deepseek`, `chatgpt`, `gemini`, `kimi`, `glm`, `qwen`, `meta`, `arena`, `auto`
- **File support**: Any file type (images, PDFs, docs) via `image_url` or `file` parts, auto-cleared after insertion
- **Auto-switch tabs**: When different model requested (e.g. `gemini` but active is `deepseek`), extension auto-switches to matching tab, focuses it, shows toast — configurable in popup
- **Active models API**: `GET /api/active-models`, `GET /zeroapi/{model}` for testing
- **UI mode**: Clears console, huge ZeroAPI status, shows LAN IP + API key, press L for logs
- **Config file**: `zeroapi_config.json` for ports, keys, models, auto-switch settings
- **Minimal bar**: Only status + model name, no duplicate buttons, embedded in chat composer, flashes on auto-switch

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
 ╚══███╔╝██╔════╝██╔══██╗██╔═══██╗██╔══██╗██╔══██╗██║
   ███╔╝ █████╗  ██████╔╝██║   ██║███████║██████╔╝██║
  ...

  STATUS: RUNNING ✅

  📡 SERVER:
     Local:  http://localhost:8000
     LAN:    http://192.168.1.50:8000  <- use for phone
  🔑 API KEY: zeroapi
  🤖 MODELS: deepseek active, gemini offline...
  [L] Toggle logs | [Q] Quit
```

Config: edit `zeroapi_config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8000,
  "api_key": "zeroapi",
  "log_enabled": false,
  "models": ["deepseek", "chatgpt", "gemini", ...]
}
```

### 2. Install Extension

- `chrome://extensions` → Developer mode ON → Load unpacked → select `zeroapi-extension/` folder
- Only this extension needed, no ZeroScript files

### 3. Open AI Chat

Open https://chat.deepseek.com or https://chatgpt.com or https://gemini.google.com

Extension bar shows: `● ZeroAPI [deepseek] ✓ Active` — click `Use this chat` if not active.

### 4. Use API

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="zeroapi")

# Simple site-name models
resp = client.chat.completions.create(
    model="deepseek",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(resp.choices[0].message.content)

# With files
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

### AI News Smartspacer Plugin

For [AI-news-Smartspacer-plugin](https://github.com/RubCut/AI-news-Smartspacer-plugin):

- Provider: Custom (OpenAI-compatible)
- Base URL: `http://192.168.1.XX:8000/v1` (your laptop LAN IP)
- Enable **Allow unencrypted connections**
- API Key: `dummy`
- Fetch models → `deepseek`, `chatgpt`, `gemini`...
- Test key → Key OK

Or add native provider via patch in `docs/AiProvider_ZEROAPI.patch`

See `docs/AI_NEWS_PLUGIN_INTEGRATION.md` for full guide.

### Opencode

Use `opencode.json` in repo root:

```json
{
  "provider": {
    "zeroapi": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "ZeroAPI",
      "options": {"baseURL": "http://localhost:8000/v1"},
      "models": {
        "deepseek": {"name": "DeepSeek"},
        "chatgpt": {"name": "ChatGPT"},
        "gemini": {"name": "Gemini"}
      }
    }
  }
}
```

Then `/models` → `zeroapi/deepseek` etc. Session memory preserved via messages array.

## API Endpoints

- `GET /` — Dashboard with active browsers
- `GET /v1/models` — 9 simple models (for plugin dropdown)
- `GET /v1/models?active_only=true` — only active
- `GET /v1/models/all` — full 21 models
- `GET /api/active-models` — active + browsers
- `GET /zeroapi/{model}` — test API e.g. `/zeroapi/deepseek`
- `GET /api/test` — test all providers
- `POST /api/test` `{"model":"deepseek","prompt":"hi"}` — quick chat test
- `GET /test` — interactive HTML test page
- `POST /v1/chat/completions` — OpenAI compatible
- `GET /health` — health

## Extension Bar & Auto-Switch

Minimal: `● ZeroAPI [deepseek] ✓ Active` + single `Use this chat` button when inactive. Embedded in composer.

**v2.6.0 Auto-switch**: 
- Open multiple chats: `chat.deepseek.com`, `chatgpt.com`, `gemini.google.com` — all with extension
- Request `model="gemini"` via API → extension auto-detects Gemini tab, switches active tab to it, focuses it, shows `↔️ Auto-switched: deepseek → gemini for gemini`
- Bar flashes green on switch, state shows `↔️ Switched from deepseek`
- Popup has toggles: 🔄 Auto-switch tabs (ON/OFF), 👁️ Auto-focus tab, 🔔 Notify on switch
- Server `/health` now returns `available_providers` (all open tabs) and `auto_switch: true`
- If no tab for provider open, returns 503 with hint: `Open https://gemini.google.com...`
- Works with `auto` model too — uses active tab or least busy

Config in `zeroapi_config.json` and extension storage `zaSettings`:
```json
{
  "auto_switch_tabs": true,
  "auto_focus_tab": true,
  "notify_on_switch": true
}
```

## File Support

Any file type via OpenAI format, auto-cleared after insertion on server and browser composer.

## Config

`zeroapi_config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8000,
  "api_key": "zeroapi",
  "log_enabled": false,
  "auto_clear_files": true
}
```

Edit and press R in UI to reload, or restart server.

## Bugs Fixed in v2.6.0

- v2.6.0 version bump, clean release only our files

## Bugs Fixed in v2.4.0

- Removed all ZeroScript remnants (bridge.py, config.json, launch_studio_mcp.py, start.bat, assets, zeroscript-extension, CHANGELOG)
- Only `zeroapi-extension` + batch files in releases
- UI mode with console clear, huge ASCII, IP + key, L to toggle logs
- File support for any type with auto-clear
- `response_format` json_object allowed (fixes AI News plugin 422)
- `/v1/models` always returns simple site names (fixes empty dropdown)
- LAN IP detection for phone usage
- Docker files cleaned (no config.json, no legacy bridge)

## License

GPL-3.0 — Based on ZeroScript by sebattfg
