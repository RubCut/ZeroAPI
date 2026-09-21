# ZeroAPI Extension v2.1 - OpenAI Compatible Browser Bridge

Turn ChatGPT, DeepSeek, Gemini, Kimi, GLM, Qwen, Arena or Meta AI into an OpenAI-compatible API server. **No Roblox remnants, pure API mode.**

Based on ZeroScript providers, but completely rewritten UI for API usage.

## What changed in v2.1 (by user request)

- **Old Start button → "Use this chat for API"** — click to set this chat tab as active handler for API requests
- **ZeroScript compatibility** — uses `za-` prefix for DOM (`#za-bar`, `#za-dot`, `#za-api-indicator`) vs ZeroScript's `zs-` prefix. Both extensions can be installed side-by-side, bars stack vertically (ZeroScript on top, ZeroAPI below)
- **Removed all ZeroScript remnants** — deleted `core/config.js`, `core/parser.js`, test files, Roblox/MCP UI, Ko-fi/Robux buttons. Only API logic remains: `core/main.js` (API bar), `core/api_handler.js` (chat handling), `providers/*.js` (DOM automation)
- **New popup** — shows available chat tabs, lets you click to activate, no Roblox tools

## How it works

```
Your App (OpenAI SDK) -> ZeroAPI Server (localhost:8000) -> WS -> Extension (za-bar + api_handler) -> AI Chat DOM -> Response
```

Extension injects prompt via `ZSProvider.typeAndSend` and reads response via `readAssistant` / `isGenerating`.

## Setup

### 1. Server
```bash
pip install -r ../requirements.txt
python ../run_server.py
# Dashboard: http://localhost:8000/
```

### 2. Extension
- `chrome://extensions` → Developer mode → Load unpacked → select `zeroapi-extension` folder
- Open https://chat.deepseek.com (recommended) → bar appears at top: `ZeroAPI v2.1 DeepSeek | Ready | API: ready | [Use this chat for API]`
- Click **📌 Use this chat for API** → button becomes `✓ Active for API`, badge `● Active for API`

### 3. Use SDK
```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="zeroapi")
resp = client.chat.completions.create(model="deepseek-chat", messages=[{"role":"user","content":"Hello!"}])
print(resp.choices[0].message.content)
```

## Bar UI

- **Dot**: gray offline, blue ready, green active, yellow pulse busy
- **State**: "Active for API (DeepSeek)" / "Ready - click to use"
- **Badge**: API: offline / ready / Active for API / busy
- **Button**: "Use this chat for API" → sets this tab as preferred in `chrome.storage.local` (`zaActiveTab`) and notifies background. Background routes all requests for that provider to this tab first.
- **Dashboard link** → http://localhost:8000/
- **Menu (⋯)**: status, how it works, models for this tab, links to dashboard/docs/models

If ZeroScript is also installed, its `#zs-bar` stays at top:0 (z-index 2147483647), ZeroAPI's `#za-bar` at top:44px (z-index 2147483645) — stacked, no overlap.

## Popup

- Shows API Server connected/offline
- Shows active chat (provider + URL)
- Lists all open chat tabs with provider badges, click to activate
- Buttons: Use this chat (current tab), Dashboard, Docs, Reconnect
- Compatibility box: detects ZeroScript extension

## Models / Routing

Model name → provider → tab:

- `deepseek-chat`, `deepseek-reasoner` → DeepSeek
- `gpt-4o`, `gpt-4`, `gpt-3.5-turbo` → ChatGPT
- `gemini-2.0-flash`, `gemini-1.5-pro` → Gemini
- `kimi-k2`, `kimi` → Kimi
- `glm-4` → GLM (z.ai)
- `qwen-turbo` → Qwen
- `llama-3`, `meta` → Meta AI
- `arena` → Arena
- `auto` → any tab (or active tab)

Background prefers active tab (`zaActiveTab`) if set, otherwise first matching provider, otherwise any tab.

## Files (clean)

```
zeroapi-extension/
  manifest.json (v2.1.0, no parser/config)
  background.js (API-only, no legacy bridge)
  overlay.css (za- prefix, coexistence with zs-)
  popup.html/js (API-only, Use this chat)
  core/
    main.js (API bar, 400 lines, not 4000)
    api_handler.js (chat handling, za- UI)
  providers/
    deepseek.js, chatgpt.js, gemini.js, etc. (ZSProvider interface)
```

No `config.js`, `parser.js`, `test-*.js`, no Roblox/MCP/Ko-fi code.

## Compatibility with ZeroScript

Both can be installed:
- Different extension IDs → separate backgrounds
- Different DOM prefixes → `zs-` vs `za-` → no ID collision
- CSS stacking: `body:has(#zs-bar) #za-bar { top:44px }`
- Storage: ZeroAPI uses `zaActiveTab`, ZeroScript uses `zs*` keys → no overlap

You can have ZeroScript controlling Roblox Studio on one tab and ZeroAPI serving OpenAI requests on another, or even same provider different tabs.

## License

GPL-3.0 — Based on ZeroScript providers by sebattfg. ZeroAPI transformation: OpenAI API layer.
