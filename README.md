# ZeroAPI — OpenAI Compatible Browser Bridge

Turn ChatGPT, DeepSeek, Gemini, Kimi, GLM, Qwen, Meta AI, Arena into a local OpenAI-compatible API server. No API keys needed — your logged-in browser sessions are the engine.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-GPL--3.0-blue)

Based on ZeroScript by sebattfg, transformed into pure API server.

## Features

- OpenAI-compatible: Works with OpenAI SDK, LangChain, OpenWebUI, opencode, etc.
- Site names as models: `deepseek`, `chatgpt`, `gemini`, `kimi`, `glm`, `qwen`, `meta`, `arena`, `auto`
- File support: Any file type via `image_url` or `file` parts, auto-cleared after insertion
- Auto-switch tabs: When different model requested, extension switches to matching tab
- Tunnel detection + auto-start: Detects public URLs from ngrok, Cloudflare, localtunnel, bore; can auto-start tunnel from config
- Compact UI: Clean console with server URLs, models, controls
- Config file: `zeroapi_config.json` for ports, keys, models, tunnels

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

Aliases also work: `deepseek-chat`, `deepseek-reasoner`, `gpt-4o`, `gpt-4o-mini`, `gemini-2.0-flash`, etc.

## Quick Start

### 1. Run Server

Windows: double-click `start_api.bat`

macOS/Linux: `./start_api.sh` or `python zeroapi.py`

```
 ZeroAPI v1.0.0 | OpenAI Compatible API Server
 ------------------------------------------------------------
 Status: RUNNING | Port: 8000 | Browsers: 0
 ------------------------------------------------------------

 Server
   Local:   http://localhost:8000
   Network: http://192.168.1.50:8000
   Public:  (none)

 Auth
   API Key: zeroapi

 Models
   deepseek  chatgpt  gemini  kimi  glm  qwen  meta  arena
   0 browsers, 0 providers, auto-switch: on

 Endpoints
   /  /v1/models  /v1/chat/completions  /api/tunnels  /health
   Dashboard: http://localhost:8000/

 Logs: OFF | Tunnels: 0 | Providers: none
 ------------------------------------------------------------
 [L] Logs  [T] Tunnels  [S] Tunnel Start/Stop  [R] Reload  [C] Clear  [Q] Quit
 ------------------------------------------------------------
```

### 2. Install Extension

- Open `chrome://extensions` in Chrome/Edge/Brave
- Enable Developer mode
- Click Load unpacked
- Select `zeroapi-extension/` folder from this repo

### 3. Open AI Chat

Open https://chat.deepseek.com and log in.

Extension bar at bottom shows: `ZeroAPI [deepseek] Active`. If not active, click `Use this chat`.

For other providers, open their sites in separate tabs.

### 4. Test API

```bash
curl http://localhost:8000/v1/models
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="zeroapi")

resp = client.chat.completions.create(
    model="deepseek",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(resp.choices[0].message.content)
```

## Tutorial: opencode + DeepSeek via ZeroAPI

This is the recommended setup for local coding agent using your DeepSeek browser session.

### What is opencode?

opencode is an open-source AI coding agent that supports OpenAI-compatible providers. With ZeroAPI, you can use DeepSeek (or any browser chat) as its engine without API keys.

### Step 1: Install opencode

https://opencode.ai

```bash
# macOS / Linux
curl -fsSL https://opencode.ai/install | bash

# or npm
npm i -g opencode-ai
```

Verify:

```bash
opencode --version
```

### Step 2: Start ZeroAPI + DeepSeek

1. Run server: `python zeroapi.py` or `start_api.bat`
2. Load extension in browser
3. Open https://chat.deepseek.com, log in, make sure tab shows `ZeroAPI [deepseek] Active`
4. Check dashboard http://localhost:8000/ — should show 1 browser connected, provider `deepseek`

### Step 3: Configure opencode to use ZeroAPI

In your project root, create `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "zeroapi": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "ZeroAPI (local browser)",
      "options": {
        "baseURL": "http://localhost:8000/v1",
        "apiKey": "zeroapi"
      },
      "models": {
        "deepseek": {
          "name": "DeepSeek"
        }
      }
    }
  }
}
```

Or use the example file from this repo:

```bash
cp opencode.zeroapi.example.json opencode.json
```

If you want all models available, use this expanded version:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "zeroapi": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "ZeroAPI",
      "options": {
        "baseURL": "http://localhost:8000/v1",
        "apiKey": "zeroapi"
      },
      "models": {
        "deepseek": { "name": "DeepSeek" },
        "chatgpt": { "name": "ChatGPT" },
        "gemini": { "name": "Gemini" },
        "auto": { "name": "Auto" }
      }
    }
  },
  "model": "zeroapi/deepseek"
}
```

Set default model:

```json
{
  "model": "zeroapi/deepseek"
}
```

### Step 4: Run opencode

```bash
opencode
# or
opencode run "Explain this codebase"
```

opencode will now:

1. Call `http://localhost:8000/v1/chat/completions` with `model: deepseek`
2. ZeroAPI server forwards prompt to your DeepSeek browser tab via WebSocket
3. Extension types prompt into chat.deepseek.com and reads response
4. Response streams back to opencode as OpenAI-compatible chunks

You should see streaming in opencode TUI, and in browser tab you will see messages appearing.

### Step 5: Tips for DeepSeek

- Keep DeepSeek tab visible (not minimized) — Chrome throttles background tabs
- DeepSeek has strong reasoning, good for code. Use `deepseek` model id.
- For files: opencode sends file context automatically, ZeroAPI injects them via `image_url` parts and auto-clears after.
- If you request `gemini` but only `deepseek` tab open, ZeroAPI will use `deepseek` anyway (or auto-switch if you have both tabs open and auto-switch enabled).

### Troubleshooting opencode

- `No browser connected`: Make sure extension shows Active and server shows Browsers: 1
- `Timeout`: DeepSeek may be thinking — wait 30s, check browser tab for errors
- `Model not found`: Check `opencode.json` provider id matches `zeroapi` and model is `deepseek`
- Tools not running / raw `jsonCopyDownload(...)` appears: ZeroAPI unwraps this DeepSeek markdown artefact and converts it into OpenAI `tool_calls`. Check `GET /health` -> `browsers_connected` and make sure the requested tool is included in the API request (see "Tool Calling").
- Browser tab not typing: Refresh chat.deepseek.com, click `Use this chat` again
- Want public URL for remote opencode: enable tunnel in `zeroapi_config.json` (see Tunnels section)

## Other Integrations

### OpenAI Python SDK

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="zeroapi")
client.chat.completions.create(model="deepseek", messages=[{"role":"user","content":"hi"}])
```

### OpenWebUI

Settings -> Connections -> OpenAI -> Base URL: `http://localhost:8000/v1`, API Key: `zeroapi`

### LangChain

```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(base_url="http://localhost:8000/v1", api_key="zeroapi", model="deepseek")
```

## Tool Calling (function calling)

Browser chats have no native function calling, so ZeroAPI emulates the OpenAI tool
protocol around them:

1. tool definitions from the request (`tools`) are injected into the prompt that is
   typed into the browser chat,
2. the model answers with a tool-call-only assistant message: a fenced JSON block
   (` ```json {"name": "bash", "arguments": {"command": "ls"}} ``` `), with no
   greeting, reasoning, or other text before or after it,
3. ZeroAPI parses that block server-side and returns real OpenAI `tool_calls`
   (`finish_reason: "tool_calls"`, `content: null`) instead of leaking the JSON or
   a preamble as message content,
4. the client executes the tool and sends the result back as a `role: "tool"`
   message; ZeroAPI folds it back into the next prompt as `[Tool result: <name>] ...`.

Works for both `stream: false` and `stream: true` (tool calls are streamed as
`delta.tool_calls` chunks). Tool-enabled streams are buffered until a tool call is
recognized, so accidental text cannot appear before the separate tool-call message.
Several calls in one tool-only message are supported (parallel calls), and
`tool_choice: "none" | "auto" | "required" | {"function": ...}` is honoured.
The first request in a conversation also receives a short ZeroAPI context prompt;
later requests do not receive it again once assistant/tool history is present. The
large OpenCode harness/system prompt is filtered out before it reaches the browser
chat, so it is not duplicated on every turn.

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="zeroapi")

tools = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    },
}]

resp = client.chat.completions.create(
    model="deepseek",
    messages=[{"role": "user", "content": "Which files are in the project?"}],
    tools=tools,
)
print(resp.choices[0].finish_reason)      # tool_calls
print(resp.choices[0].message.tool_calls) # [bash {"command": "ls"}]
```

This is what makes agent clients work: opencode, LangChain agents, OpenWebUI tools
and anything else that sends `tools` and executes the returned calls.

### MCP tools (server-side execution)

ZeroAPI can also expose MCP servers as tools and execute them itself — no client
support needed. Add the servers to `zeroapi_config.json`:

```json
{
  "mcp_servers": {
    "roblox": { "command": "python", "args": ["roblox_mcp_server.py"] },
    "files":  { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/me"] }
  },
  "mcp_tools": {
    "enabled": true,
    "auto_execute": true,
    "max_rounds": 5
  }
}
```

* `GET /api/tools` — raw MCP tool list (name, description, schema, server, health)
* `GET /v1/tools` — the same tools in OpenAI format, for clients that want to execute them
* `POST /api/tool/call {"name": ..., "arguments": {...}}` — call one tool directly

When MCP servers are configured, a chat request that carries no client `tools` gets
the MCP tools injected automatically: the model asks for one, ZeroAPI runs it and
feeds the result back to the model (up to `max_rounds`), and the client only sees the
final answer. Client-provided `tools` always take precedence.

## Configuration

`zeroapi_config.json`:

```json
{
  "host": "0.0.0.0",
  "port": 8000,
  "api_key": "zeroapi",
  "log_enabled": false,
  "auto_switch_tabs": true,
  "auto_focus_tab": true,
  "notify_on_switch": true,
  "tunnel_auto_detect": true,
  "tunnel": {
    "enabled": false,
    "provider": "cloudflare",
    "auto_start": false,
    "port": null,
    "subdomain": "",
    "custom_command": "",
    "extra_args": ""
  },
  "models": ["deepseek", "chatgpt", "gemini", "kimi", "glm", "qwen", "meta", "arena", "auto"],
  "mcp_servers": {},
  "mcp_tools": {
    "enabled": true,
    "auto_execute": true,
    "max_rounds": 5
  }
}
```

`mcp_servers` / `mcp_tools` are optional — leave them out (or empty) and ZeroAPI runs
as a plain chat bridge. See "Tool Calling" above for the format.

CLI args:

```bash
python zeroapi.py --port 8000 --api-key mykey --tunnel-provider cloudflare --tunnel-autostart
python zeroapi.py --no-ui
```

Env vars:

```bash
ZEROAPI_PORT=8000 ZEROAPI_API_KEY=zeroapi ZEROAPI_TUNNEL_URL=https://xxx.trycloudflare.com python zeroapi.py
```

## Tunnels — Public URL

Make local API public:

```bash
# Cloudflare (recommended)
cloudflared tunnel --url http://localhost:8000

# ngrok
ngrok http 8000

# localtunnel
lt --port 8000

# bore
bore local 8000 --to bore.pub
```

Auto-detection: ZeroAPI auto-detects tunnel URLs from ngrok API (4040), cloudflared logs, env vars.

Auto-start from config:

```json
{
  "tunnel": {
    "enabled": true,
    "provider": "cloudflare",
    "auto_start": true
  }
}
```

Providers: `cloudflare`, `ngrok`, `localtunnel`, `bore`, `custom`

Then UI shows:

```
   Public:  https://abc.trycloudflare.com [cloudflare]
            https://abc.trycloudflare.com/v1/chat/completions
```

Use public URL in opencode.json:

```json
{
  "options": {
    "baseURL": "https://abc.trycloudflare.com/v1",
    "apiKey": "zeroapi"
  }
}
```

## API Endpoints

- `GET /` — Dashboard
- `GET /v1/models` — 9 simple models (site names)
- `GET /v1/models/all` — 21 models with aliases
- `GET /api/active-models` — active browsers
- `GET /api/tunnels` — tunnels + autostart config
- `POST /api/tunnels/start` — get start command for provider
- `GET /health` — health, tunnels, providers, auto_switch
- `GET /api/status` — status
- `POST /v1/chat/completions` — OpenAI compatible, streaming supported, tool calling supported
- `POST /v1/completions` — legacy completions
- `POST /v1/embeddings` — dummy embeddings (1536 dim)
- `GET /v1/tools` — MCP tools in OpenAI `tools` format
- `GET /api/tools` — MCP tools, servers and health
- `POST /api/tool/call` — execute an MCP tool directly

## How it Works

```
opencode / OpenAI Client
      |
      v
ZeroAPI Server (FastAPI :8000) -- WebSocket :8000/ws
      |
      v
Extension (content script + background)
      |
      v
AI Chat Site (chat.deepseek.com, etc.)
```

Server selects browser tab by provider (model -> provider map). Extension uses provider-specific DOM logic to type prompt and read response. Streaming via incremental text diff.

## Development

```bash
pip install -r requirements.txt
python tests/test_server.py
python zeroapi.py --reload
```

## License

GPL-3.0 — Based on ZeroScript by sebattfg
