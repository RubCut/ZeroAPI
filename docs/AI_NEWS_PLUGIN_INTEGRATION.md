# ZeroAPI + AI News Smartspacer Plugin Integration

This doc explains how to make ZeroAPI work with [AI-news-Smartspacer-plugin](https://github.com/RubCut/AI-news-Smartspacer-plugin) — fetch models + test API.

## Problem
AI News plugin uses `AiProvider` enum + `OpenAiClient.listModels()` which does `GET {baseUrl}/models` expecting OpenAI format `{"data": [{"id": "model"}]}`.

ZeroAPI v2.3.0 now provides:
- `GET /v1/models` → simple site names: `deepseek`, `chatgpt`, `gemini`, `kimi`, `glm`, `qwen`, `meta`, `arena`, `auto`
- `GET /api/active-models` → only active (connected browsers)
- `GET /zeroapi/{model}` → test API like `/zeroapi/deepseek`
- `POST /api/test` → quick chat test

## Solution 1: Use Custom OpenAI provider (no code change)

1. Open AI News plugin → Settings → Provider → **Custom (OpenAI-compatible)**
2. Base URL: `http://192.168.1.XX:8000/v1`  (your laptop LAN IP, not 127.0.0.1 — Android can't reach 127.0.0.1 of laptop)
   - Find IP: `ipconfig` (Windows) or `ifconfig` (Mac/Linux)
   - Example: `http://192.168.1.50:8000/v1`
3. Enable **Allow unencrypted connections** switch (required for LAN IP — Android blocks cleartext to non-loopback by default, the plugin uses PlainHttp raw socket when this is on)
4. API Key: `dummy` or any text (ZeroAPI doesn't check)
5. Click **Fetch models** → should show `deepseek`, `chatgpt`, `gemini`, etc.
6. Select model e.g. `deepseek` → **Test key** → should say `Key OK, 8 models`
7. Save → plugin will generate news via ZeroAPI

**If fetch fails:**
- Ensure ZeroAPI server running: `python run_server.py` → binds 0.0.0.0:8000
- Ensure extension installed, tab open (deepseek.com / chatgpt.com / gemini.google.com), bar shows ` Active` with model pill
- Ensure phone and laptop on same WiFi
- Check firewall: allow port 8000
- Try `http://YOUR_IP:8000/api/test` in phone browser — should return JSON

## Solution 2: Add ZeroAPI as native provider (code change)

Add to `AiProvider.kt`:

```kotlin
ZEROAPI(
    id = "zeroapi",
    label = "ZeroAPI (browser)",
    flavor = ApiFlavor.OPENAI,
    defaultBaseUrl = "http://127.0.0.1:8000/v1",
    defaultModel = "deepseek",
    fallbackModels = listOf("deepseek", "chatgpt", "gemini", "kimi", "glm", "qwen", "meta", "arena", "auto"),
    apiKeyUrl = "https://github.com/RubCut/ZeroAPI",
    editableBaseUrl = true,
    requiresKey = false
),
```

Then in UI it appears as separate provider with its own fallback models, no need to use Custom.

Full patch is in `AiProvider_ZEROAPI.patch`.

## Server endpoints for plugin

| Endpoint | Use |
|----------|-----|
| `GET /v1/models` | Fetch models — returns 8 simple models always (for dropdown) |
| `GET /v1/models?active_only=true` | Only active (connected browsers) |
| `GET /api/active-models` | Detailed active models + browsers count — best for plugin logic |
| `GET /zeroapi/deepseek` | Test API for model — returns status active/offline, browsers, curl example |
| `GET /api/test` | Test all providers |
| `POST /api/test` `{"model":"deepseek","prompt":"Hello"}` | Quick chat test |
| `POST /v1/chat/completions` | OpenAI compatible — used by plugin to generate news |

## Why it didn't work before

1. `/v1/models` previously filtered to active only when browsers connected — if only DeepSeek tab open, plugin saw only `deepseek` models, not all 8. Now returns all 8 always.
2. `ChatCompletionRequest` didn't allow `response_format` field that plugin sends (`{"type":"json_object"}`) — now allowed via `extra="allow"`.
3. LAN IP needs `Allow unencrypted connections` switch — otherwise Android blocks cleartext to non-loopback hosts.

## Test with mock server

The plugin repo has `tools/mock-ai-server.py` — stdlib-only mock that mimics ZeroAPI for testing without real browser.

## Opencode integration

See `opencode.json` in ZeroAPI root — adds ZeroAPI as provider for opencode CLI with same site-name models.
