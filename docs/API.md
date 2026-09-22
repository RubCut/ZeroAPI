# ZeroAPI - OpenAI Compatible API Documentation

Base URL: `http://localhost:8000`

## Authentication

API key is optional. You can pass any string as `api_key` or `Authorization: Bearer <key>`.

```python
client = OpenAI(base_url="http://localhost:8000/v1", api_key="anything")
```

## Endpoints

### List Models

```http
GET /v1/models
```

Response:
```json
{
  "object": "list",
  "data": [
    {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek"},
    {"id": "gpt-4o", "object": "model", "owned_by": "openai"}
  ]
}
```

### Chat Completions

```http
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "deepseek-chat",
  "messages": [
    {"role": "system", "content": "You are helpful"},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 500,
  "stream": false
}
```

Non-streaming response (OpenAI format):
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "deepseek-chat",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Hello! How can I help?"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
}
```

Streaming request:
```json
{
  "model": "auto",
  "messages": [{"role": "user", "content": "Count to 5"}],
  "stream": true
}
```

Streaming response (SSE):
```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"content":"1\n"},"index":0}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"content":"2\n"},"index":0}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{},"finish_reason":"stop","index":0}]}

data: [DONE]
```

### Completions (Legacy)

```http
POST /v1/completions
{
  "model": "gpt-4o",
  "prompt": "Once upon a time",
  "max_tokens": 100,
  "stream": false
}
```

### Health

```http
GET /health
```

```json
{
  "status": "ok",
  "version": "2.0.0",
  "browsers_connected": 1,
  "browsers": [{"id": "browser-abc", "provider": "deepseek", "busy": false}],
  "mcp_servers": []
}
```

### Dashboard

```http
GET /
```

HTML dashboard with browser status, endpoints, examples. Auto-refreshes every 3s.

## Model Routing

Model name determines which browser tab handles request:

- `deepseek-chat`, `deepseek-reasoner`, `deepseek` -> DeepSeek
- `gpt-4o`, `gpt-4`, `gpt-3.5-turbo`, `chatgpt`, `o1` -> ChatGPT
- `gemini-2.0-flash`, `gemini-1.5-pro`, `gemini` -> Gemini
- `kimi-k2`, `kimi` -> Kimi
- `glm-4`, `glm` -> GLM (Zhipu)
- `qwen-turbo`, `qwen` -> Qwen
- `llama-3`, `meta` -> Meta AI
- `arena` -> Arena
- `auto` -> any available

If no tab for requested provider exists, any available tab is used.

You can also force provider via `provider` field (ZeroAPI extension):

```json
{
  "model": "gpt-4o",
  "provider": "deepseek",
  "messages": [...]
}
```

## Error Handling

503 No browser connected:
```json
{
  "detail": {
    "error": {
      "message": "No browser connected for provider 'deepseek'...",
      "type": "service_unavailable",
      "code": "no_browser_connected"
    }
  }
}
```

504 Timeout:
```json
{"detail": {"error": {"message": "Browser timeout", "type": "timeout"}}}
```

## WebSocket Protocol (Extension <-> Server)

### Extension -> Server: Register

```json
{
  "type": "register",
  "client_id": "browser-abc123",
  "provider": "deepseek",
  "url": "https://chat.deepseek.com/...",
  "version": "2.0.0"
}
```

### Server -> Extension: Chat Request

```json
{
  "type": "chat_request",
  "id": "chatcmpl-xyz",
  "model": "deepseek-chat",
  "provider": "deepseek",
  "prompt": "Hello!",
  "messages": [{"role": "user", "content": "Hello!"}],
  "stream": true
}
```

### Extension -> Server: Chunk

```json
{
  "type": "chat_chunk",
  "id": "chatcmpl-xyz",
  "delta": "Hello",
  "content": "Hello",
  "done": false
}
```

### Extension -> Server: Final Response

```json
{
  "type": "chat_response",
  "id": "chatcmpl-xyz",
  "content": "Hello! How can I help?",
  "done": true
}
```

### Extension -> Server: Error

```json
{
  "type": "chat_error",
  "id": "chatcmpl-xyz",
  "error": "Timeout",
  "done": true
}
```

## Client Libraries

Any OpenAI-compatible library works:

- Python `openai`
- Node `openai`
- LangChain: `ChatOpenAI(base_url="http://localhost:8000/v1", api_key="x")`
- OpenWebUI: set OpenAI base URL to `http://localhost:8000/v1`
- Anything that supports custom base_url

## Tool Calling

ZeroAPI implements the OpenAI tools/functions protocol on top of browser chats.

Request (same as OpenAI):

```json
{
  "model": "deepseek",
  "messages": [{"role": "user", "content": "List the files"}],
  "tools": [{
    "type": "function",
    "function": {
      "name": "bash",
      "description": "Run a shell command",
      "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
    }
  }],
  "tool_choice": "auto"
}
```

Response:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "deepseek",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_9f2c...",
        "type": "function",
        "function": {"name": "bash", "arguments": "{\"command\": \"ls\"}"}
      }]
    },
    "finish_reason": "tool_calls"
  }],
  "usage": {"prompt_tokens": 120, "completion_tokens": 14, "total_tokens": 134}
}
```

Send the result back exactly like with OpenAI:

```json
{
  "model": "deepseek",
  "messages": [
    {"role": "user", "content": "List the files"},
    {"role": "assistant", "content": null, "tool_calls": [
      {"id": "call_9f2c...", "type": "function", "function": {"name": "bash", "arguments": "{\"command\": \"ls\"}"}}
    ]},
    {"role": "tool", "tool_call_id": "call_9f2c...", "name": "bash", "content": "server tests README.md"}
  ]
}
```

Notes:

- Streaming is supported: `delta.tool_calls` chunks (id/name first, then arguments)
  followed by a chunk with `finish_reason: "tool_calls"`.
- `tool_choice: "none"` disables tools for that request; `"required"` and
  `{"type": "function", "function": {"name": "..."}}` are honoured in the prompt.
- `stream_options: {"include_usage": true}` adds a final usage-only chunk.
- The model is instructed to put each tool call in its own assistant message with
  no greeting, reasoning, or prose before or after the JSON block. ZeroAPI strips
  any accidental preamble from `content`, so a tool-call response has
  `content: null` and clients never see raw tool JSON. In streaming mode the
  tool-enabled response is buffered until the tool call is recognized, so a
  preamble cannot leak before `finish_reason: "tool_calls"`.
- The first request in a conversation receives a short ZeroAPI context because
  browser chats do not expose a native system-message channel. It is not added
  again after an assistant/tool message is present.
- MCP: `GET /v1/tools` lists configured MCP tools in OpenAI format, and when a
  request carries no `tools` while `mcp_servers` are configured, the server injects
  them and executes the calls itself (`mcp_tools.auto_execute`).

### MCP endpoints

```http
GET /api/tools                 # raw MCP tools + server health
GET /v1/tools                  # OpenAI tool definitions
POST /api/tool/call            # {"name": "echo", "arguments": {"text": "hi"}}
```

## Limitations

- Browser tab must be visible (not minimized) for reliable operation (Chrome throttles background tabs)
- Only one request per tab at a time (queued)
- Temperature, top_p, etc. are not enforced by browser providers (they use their own defaults) - could be added to system prompt
- No real token counting (estimated)
- No embeddings, image generation (can be stubbed)
- Depends on provider's DOM - may break if site redesigns (ZeroScript provider files need update)

## Future

- Session persistence
- Vision support
- Auth & rate limiting
