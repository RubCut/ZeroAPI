"""
ZeroAPI Server - OpenAI Compatible API Server based on ZeroScript
Transforms the Roblox Studio tool into a browser-based LLM gateway.

Architecture:
- FastAPI HTTP server exposing OpenAI-compatible endpoints
- WebSocket server for browser extension communication
- Extension injects prompts into ChatGPT, DeepSeek, Gemini, etc. and returns responses
- MCP manager kept for optional tool execution (Roblox Studio etc.)

Usage:
    python -m server.main
    or
    uvicorn server.main:app --host 0.0.0.0 --port 8000

Environment:
    ZEROAPI_PORT - HTTP port (default 8000)
    ZS_BRIDGE_PORT - legacy bridge port (default 17613, optional)
"""

import asyncio
import json
import time
import uuid
import os
import logging
import threading
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import HOST, PORT, MODEL_PROVIDER_MAP, ALL_MODELS, PROVIDER_DEFAULT_MODEL, CHAT_TIMEOUT
from .openai_models import (
    ModelCard, ModelList, ChatCompletionRequest, ChatCompletionResponse,
    ChatCompletionResponseChoice, ChatMessage, ChatCompletionStreamResponse,
    ChatCompletionStreamChoice, DeltaMessage, CompletionRequest, CompletionResponse,
    CompletionResponseChoice
)
from .ws_manager import ws_manager, BrowserClient
from .mcp_manager import mcp_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("zeroapi")

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: try to load MCP servers (optional, non-blocking)
    try:
        # Run in thread to avoid blocking
        await asyncio.to_thread(mcp_manager.load_config)
        # Start MCP servers in background thread (fire-and-forget)
        def _start():
            try:
                mcp_manager.start_all()
            except Exception as e:
                logger.warning(f"MCP start failed (optional): {e}")
        threading.Thread(target=_start, daemon=True).start()
    except Exception as e:
        logger.warning(f"MCP init failed: {e}")

    logger.info(f"ZeroAPI Server v2.0.0 starting on {HOST}:{PORT}")
    logger.info(f"OpenAI API: http://{HOST}:{PORT}/v1/chat/completions")
    logger.info(f"WebSocket for extension: ws://{HOST}:{PORT}/ws")
    logger.info(f"Dashboard: http://{HOST}:{PORT}/")
    yield
    # Shutdown
    for client in mcp_manager.clients.values():
        try:
            client.stop()
        except:
            pass

app = FastAPI(
    title="ZeroAPI - OpenAI Compatible Server",
    description="OpenAI-compatible API server powered by browser automation via ZeroScript. Routes requests through ChatGPT, DeepSeek, Gemini, Kimi, etc. running in your browser.",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helpers ---
def is_valid_model(model: str) -> bool:
    ml = model.lower()
    if ml == "auto":
        return True
    if ml in MODEL_PROVIDER_MAP:
        return True
    for m in ALL_MODELS:
        if m["id"].lower() == ml:
            return True
    for key in MODEL_PROVIDER_MAP.keys():
        if ml.startswith(key):
            return True
    return False

def get_provider_for_model(model: str) -> str:
    model_lower = model.lower()
    if model_lower in MODEL_PROVIDER_MAP:
        return MODEL_PROVIDER_MAP[model_lower]
    for key, prov in MODEL_PROVIDER_MAP.items():
        if model_lower.startswith(key):
            return prov
    return "auto"

def messages_to_prompt(messages: List[ChatMessage]) -> str:
    """Convert OpenAI messages array to a single prompt string for browser chat."""
    if not messages:
        return ""
    
    # If only one user message, return its content directly (cleanest)
    if len(messages) == 1 and messages[0].role == "user":
        content = messages[0].content
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Handle multimodal content array
            texts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    texts.append(part.get("text", ""))
            return "\n".join(texts)
    
    # Otherwise build conversation history
    parts = []
    for msg in messages:
        role = msg.role
        content = msg.content or ""
        if isinstance(content, list):
            # Multimodal - extract text
            texts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    texts.append(part.get("text", ""))
            content = "\n".join(texts)
        
        if role == "system":
            parts.append(f"[System Instructions]: {content}")
        elif role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
        elif role == "tool":
            parts.append(f"Tool result: {content}")
    
    # Join with double newline, last user message as final prompt
    return "\n\n".join(parts)

def estimate_tokens(text: str) -> int:
    # Rough estimation: 1 token ~ 4 chars
    return max(1, len(text) // 4)

# --- WebSocket endpoint for browser extension ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = None
    client: Optional[BrowserClient] = None
    
    try:
        # Expect first message to be registration
        # But also handle ping/pong loop
        while True:
            try:
                data_text = await websocket.receive_text()
                data = json.loads(data_text)
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"WS receive error: {e}")
                continue

            msg_type = data.get("type")

            if msg_type in ("register", "hello"):
                client_id = data.get("client_id") or f"browser-{uuid.uuid4().hex[:8]}"
                client = await ws_manager.register_client(websocket, data)
                client_id = client.id
                # Ack
                await websocket.send_text(json.dumps({
                    "type": "registered",
                    "client_id": client_id,
                    "server": "ZeroAPI v2.0.0",
                    "message": f"Registered as {client.provider} client"
                }))
                continue

            if client is None:
                # Auto-register if not yet registered
                client_id = data.get("client_id") or f"browser-{uuid.uuid4().hex[:8]}"
                client = await ws_manager.register_client(websocket, data)
                client_id = client.id

            # Update last seen
            if client:
                client.last_seen = time.time()

            # Handle message via manager
            if client:
                await ws_manager.handle_client_message(client, data)

            # Handle legacy bridge messages too (for backward compat)
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "id": data.get("id")}))
            elif msg_type == "studio_status":
                # Legacy: return studio status (mock as connected if browser connected)
                await websocket.send_text(json.dumps({
                    "type": "studio_status",
                    "id": data.get("id"),
                    "studio": True,
                    "studio_app": True,
                    "ok": True
                }))
            elif msg_type == "list_tools":
                tools = mcp_manager.list_tools()
                await websocket.send_text(json.dumps({
                    "type": "tools",
                    "id": data.get("id"),
                    "tools": tools,
                    "mcp_alive": len(mcp_manager.clients) > 0,
                    "servers": mcp_manager.health(),
                    "studio": True,
                    "studio_app": True,
                }))
            elif msg_type == "call_tool":
                # MCP tool call from old extension
                name = data.get("name")
                args = data.get("arguments") or {}
                timeout = float(data.get("timeout", 120000)) / 1000.0
                try:
                    result = await asyncio.to_thread(mcp_manager.call, name, args, timeout)
                    await websocket.send_text(json.dumps({
                        "type": "tool_result",
                        "id": data.get("id"),
                        "ok": True,
                        "text": result["text"],
                        "images": result["images"]
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "tool_result",
                        "id": data.get("id"),
                        "ok": False,
                        "error": str(e),
                        "kind": type(e).__name__
                    }))

    except WebSocketDisconnect:
        logger.info(f"Browser client {client_id} disconnected")
    except Exception as e:
        logger.error(f"WS error for {client_id}: {e}")
    finally:
        if client_id:
            await ws_manager.unregister_client(client_id)

# --- HTTP API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    clients = ws_manager.get_all_clients()
    models = ALL_MODELS
    
    client_rows = ""
    for c in clients:
        status = "🟢 Busy" if c.busy else "🟢 Ready"
        client_rows += f"<tr><td>{c.id}</td><td>{c.provider}</td><td>{status}</td><td>{c.url[:60]}</td><td>{time.strftime('%H:%M:%S', time.localtime(c.last_seen))}</td></tr>"
    
    if not client_rows:
        client_rows = "<tr><td colspan='5' style='text-align:center; color:#888;'>No browsers connected. Install extension and open chat.deepseek.com or chatgpt.com</td></tr>"

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>ZeroAPI - OpenAI Compatible Server</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; background: #0a0a0a; color: #e0e0e0; }}
        h1 {{ color: #fff; border-bottom: 1px solid #333; padding-bottom: 10px; }}
        .card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #333; }}
        th {{ color: #888; font-weight: 600; }}
        code {{ background: #222; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; background: #222; border: 1px solid #333; }}
        .badge.green {{ background: #0a2; color: #fff; border-color: #0a2; }}
        .endpoint {{ display: flex; align-items: center; gap: 10px; margin: 10px 0; }}
        .method {{ background: #0a84ff; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
        .method.get {{ background: #30d158; }}
        a {{ color: #0a84ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .logo {{ font-size: 1.5em; margin-right: 10px; }}
    </style>
</head>
<body>
    <h1><span class="logo">⚡</span> ZeroAPI Server v2.0.0</h1>
    <p>OpenAI-compatible API powered by browser automation. Based on ZeroScript.</p>
    
    <div class="card">
        <h3>📡 Connected Browsers ({len(clients)})</h3>
        <table>
            <tr><th>ID</th><th>Provider</th><th>Status</th><th>URL</th><th>Last Seen</th></tr>
            {client_rows}
        </table>
        <p style="margin-top:15px; color:#888; font-size:0.9em;">
            To connect a browser: install the ZeroAPI extension, open <a href="https://chat.deepseek.com" target="_blank">chat.deepseek.com</a> or <a href="https://chatgpt.com" target="_blank">chatgpt.com</a>, and the extension will auto-connect.
        </p>
    </div>

    <div class="card">
        <h3>🔌 API Endpoints</h3>
        <div class="endpoint"><span class="method get">GET</span> <code>/v1/models</code> - List available models</div>
        <div class="endpoint"><span class="method">POST</span> <code>/v1/chat/completions</code> - Chat completions (OpenAI compatible)</div>
        <div class="endpoint"><span class="method">POST</span> <code>/v1/completions</code> - Text completions</div>
        <div class="endpoint"><span class="method get">GET</span> <code>/health</code> - Health check</div>
        <div class="endpoint"><span class="method get">GET</span> <code>/api/status</code> - Detailed status JSON</div>
        <div class="endpoint"><span class="method">WS</span> <code>/ws</code> - WebSocket for browser extension</div>
    </div>

    <div class="card">
        <h3>💻 Usage Example</h3>
        <pre style="background:#111; padding:15px; border-radius:6px; overflow-x:auto;"><code>import openai

client = openai.OpenAI(
    base_url="http://localhost:{PORT}/v1",
    api_key="zeroapi"  # any string, auth is optional
)

response = client.chat.completions.create(
    model="deepseek-chat",  # or gpt-4o, gemini, kimi, etc.
    messages=[
        {{"role": "user", "content": "Hello! How are you?"}}
    ]
)

print(response.choices[0].message.content)
</code></pre>
    </div>

    <div class="card">
        <h3>🤖 Available Models</h3>
        <p>Models are routed to browser tabs based on provider. Use <code>auto</code> for any available browser.</p>
        <table>
            <tr><th>Model ID</th><th>Provider</th><th>Description</th></tr>
            {"".join(f"<tr><td><code>{m['id']}</code></td><td>{m['provider']}</td><td>{m['owned_by']}</td></tr>" for m in models)}
        </table>
    </div>

    <div class="card" style="text-align:center; color:#666; font-size:0.85em;">
        ZeroAPI v2.0.0 | Based on ZeroScript by sebattfg | GPL-3.0<br>
        <a href="https://github.com/RubCut/ZeroAPI">GitHub</a>
    </div>

    <script>
        // Auto-refresh every 3 seconds
        setTimeout(() => location.reload(), 3000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html)

@app.get("/status", response_class=HTMLResponse)
async def legacy_status_page():
    # Redirect to dashboard logic
    return await dashboard()

@app.get("/health")
async def health():
    clients = ws_manager.get_all_clients()
    return {
        "status": "ok",
        "version": "2.0.0",
        "browsers_connected": len(clients),
        "browsers": [c.to_dict() for c in clients],
        "mcp_servers": mcp_manager.health(),
        "uptime": time.time(),
    }

@app.get("/api/status")
async def api_status():
    data = await health()
    # Add alias for compatibility
    data["connected_clients"] = data.get("browsers_connected", 0)
    data["total_requests"] = 0
    return data

@app.get("/v1/models")
async def list_models():
    cards = []
    for m in ALL_MODELS:
        cards.append(ModelCard(id=m["id"], owned_by=m["owned_by"]))
    return ModelList(data=cards)

@app.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    for m in ALL_MODELS:
        if m["id"] == model_id:
            return ModelCard(id=m["id"], owned_by=m["owned_by"])
    # Return generic if not found but provider exists
    return ModelCard(id=model_id, owned_by="zeroapi")

async def handle_chat_completion(request: ChatCompletionRequest) -> Dict[str, Any]:
    if not is_valid_model(request.model):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": f"Invalid model '{request.model}'. Available: {[m['id'] for m in ALL_MODELS]}",
                    "type": "invalid_request_error",
                    "code": "model_not_found"
                }
            }
        )
    provider = request.provider or get_provider_for_model(request.model)
    
    # Select browser client
    client = await ws_manager.select_client(provider if provider != "auto" else None)
    if not client:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "message": f"No browser connected for provider '{provider}'. Open {provider}.com in browser with ZeroAPI extension installed.",
                    "type": "service_unavailable",
                    "code": "no_browser_connected",
                    "available_browsers": [c.to_dict() for c in ws_manager.get_all_clients()]
                }
            }
        )

    prompt = messages_to_prompt(request.messages)
    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    payload = {
        "type": "chat_request",
        "id": request_id,
        "model": request.model,
        "provider": provider,
        "messages": [m.model_dump() for m in request.messages],
        "prompt": prompt,
        "stream": request.stream,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "session_id": request.session_id,
    }

    logger.info(f"Routing chat request {request_id} model={request.model} provider={provider} -> client {client.id} ({client.provider})")

    if request.stream:
        return client, request_id, payload
    else:
        try:
            result = await ws_manager.send_chat_request(client, request_id, payload, timeout=CHAT_TIMEOUT)
            
            if result.get("type") == "chat_error":
                raise HTTPException(status_code=500, detail={"error": {"message": result.get("error", "Browser error"), "type": "browser_error"}})
            
            content = result.get("content", "") or result.get("text", "") or ""
            
            # Build OpenAI response
            choice = ChatCompletionResponseChoice(
                index=0,
                message=ChatMessage(role="assistant", content=content),
                finish_reason="stop"
            )
            
            prompt_tokens = estimate_tokens(prompt)
            completion_tokens = estimate_tokens(content)
            
            response = ChatCompletionResponse(
                model=request.model,
                choices=[choice],
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens
                }
            )
            return response.model_dump()
            
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail={"error": {"message": "Browser timeout - no response from AI provider", "type": "timeout"}})
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise HTTPException(status_code=500, detail={"error": {"message": str(e), "type": "internal_error"}})

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    if not is_valid_model(request.model):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": f"Invalid model '{request.model}'. Use /v1/models to list available.",
                    "type": "invalid_request_error",
                    "code": "model_not_found"
                }
            }
        )
    # Handle streaming vs non-streaming
    if request.stream:
        provider = request.provider or get_provider_for_model(request.model)
        client = await ws_manager.select_client(provider if provider != "auto" else None)
        if not client:
            raise HTTPException(status_code=503, detail={"error": {"message": f"No browser connected for provider '{provider}'", "type": "service_unavailable"}})

        prompt = messages_to_prompt(request.messages)
        request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        
        payload = {
            "type": "chat_request",
            "id": request_id,
            "model": request.model,
            "provider": provider,
            "messages": [m.model_dump() for m in request.messages],
            "prompt": prompt,
            "stream": True,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        async def event_generator():
            chat_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
            created = int(time.time())
            full_content = ""
            
            try:
                async for chunk_msg in ws_manager.send_chat_request_stream(client, request_id, payload):
                    msg_type = chunk_msg.get("type")
                    
                    if msg_type == "chat_chunk":
                        delta_text = chunk_msg.get("delta", "") or chunk_msg.get("content", "")
                        if not delta_text:
                            continue
                        # Only send new delta, not full content
                        # For simplicity, we track full_content and send incremental
                        # But browser may send full content each time - we need to diff
                        # Let's assume browser sends incremental delta
                        # If browser sends full content, we need to calculate diff
                        # Here we implement simple diff logic on server side
                        if len(delta_text) > len(full_content) and delta_text.startswith(full_content):
                            new_delta = delta_text[len(full_content):]
                        else:
                            new_delta = delta_text
                        
                        if new_delta:
                            full_content = delta_text if len(delta_text) > len(full_content) else full_content + new_delta
                            
                            chunk = ChatCompletionStreamResponse(
                                id=chat_id,
                                created=created,
                                model=request.model,
                                choices=[ChatCompletionStreamChoice(
                                    index=0,
                                    delta=DeltaMessage(content=new_delta),
                                    finish_reason=None
                                )]
                            )
                            yield f"data: {json.dumps(chunk.model_dump())}\n\n"
                    
                    elif msg_type == "chat_done":
                        final_content = chunk_msg.get("content", full_content)
                        # Send any remaining content
                        if final_content and len(final_content) > len(full_content):
                            remaining = final_content[len(full_content):]
                            if remaining:
                                chunk = ChatCompletionStreamResponse(
                                    id=chat_id,
                                    created=created,
                                    model=request.model,
                                    choices=[ChatCompletionStreamChoice(
                                        index=0,
                                        delta=DeltaMessage(content=remaining),
                                        finish_reason=None
                                    )]
                                )
                                yield f"data: {json.dumps(chunk.model_dump())}\n\n"
                        
                        # Final chunk with finish_reason
                        final_chunk = ChatCompletionStreamResponse(
                            id=chat_id,
                            created=created,
                            model=request.model,
                            choices=[ChatCompletionStreamChoice(
                                index=0,
                                delta=DeltaMessage(),
                                finish_reason="stop"
                            )]
                        )
                        yield f"data: {json.dumps(final_chunk.model_dump())}\n\n"
                        yield "data: [DONE]\n\n"
                        break
                    
                    elif msg_type == "chat_error":
                        error_msg = chunk_msg.get("error", "Unknown browser error")
                        # Send error as content then finish
                        err_chunk = ChatCompletionStreamResponse(
                            id=chat_id,
                            created=created,
                            model=request.model,
                            choices=[ChatCompletionStreamChoice(
                                index=0,
                                delta=DeltaMessage(content=f"Error: {error_msg}"),
                                finish_reason="stop"
                            )]
                        )
                        yield f"data: {json.dumps(err_chunk.model_dump())}\n\n"
                        yield "data: [DONE]\n\n"
                        break
                        
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                err_chunk = ChatCompletionStreamResponse(
                    id=chat_id,
                    created=created,
                    model=request.model,
                    choices=[ChatCompletionStreamChoice(
                        index=0,
                        delta=DeltaMessage(content=f"Error: {str(e)}"),
                        finish_reason="stop"
                    )]
                )
                yield f"data: {json.dumps(err_chunk.model_dump())}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    else:
        result = await handle_chat_completion(request)
        # If result is a tuple, it's streaming case handled above, but we already handled
        if isinstance(result, dict):
            return JSONResponse(content=result)
        else:
            # Should not happen for non-streaming
            client, req_id, payload = result
            # Fallback to non-streaming via stream manager
            try:
                res = await ws_manager.send_chat_request(client, req_id, payload, timeout=CHAT_TIMEOUT)
                content = res.get("content", "") or res.get("text", "") or ""
                choice = ChatCompletionResponseChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason="stop"
                )
                prompt_text = payload["prompt"]
                response = ChatCompletionResponse(
                    model=request.model,
                    choices=[choice],
                    usage={
                        "prompt_tokens": estimate_tokens(prompt_text),
                        "completion_tokens": estimate_tokens(content),
                        "total_tokens": estimate_tokens(prompt_text) + estimate_tokens(content)
                    }
                )
                return JSONResponse(content=response.model_dump())
            except Exception as e:
                raise HTTPException(status_code=500, detail={"error": {"message": str(e)}})

@app.post("/v1/completions")
async def completions(request: CompletionRequest):
    # Convert to chat format
    prompt = request.prompt if isinstance(request.prompt, str) else "\n".join(request.prompt)
    chat_req = ChatCompletionRequest(
        model=request.model,
        messages=[ChatMessage(role="user", content=prompt)],
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        stream=request.stream
    )
    # Reuse chat completions logic but return completion format
    if request.stream:
        # For streaming completions, we can reuse chat streaming but adapt format
        # Simplified: call chat and stream as text
        provider = get_provider_for_model(request.model)
        client = await ws_manager.select_client(provider if provider != "auto" else None)
        if not client:
            raise HTTPException(status_code=503, detail={"error": {"message": "No browser connected"}})
        
        request_id = f"cmpl-{uuid.uuid4().hex[:12]}"
        payload = {
            "type": "chat_request",
            "id": request_id,
            "model": request.model,
            "prompt": prompt,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }

        async def gen():
            async for chunk_msg in ws_manager.send_chat_request_stream(client, request_id, payload):
                if chunk_msg.get("type") == "chat_chunk":
                    delta = chunk_msg.get("delta", "")
                    resp = {
                        "id": request_id,
                        "object": "text_completion",
                        "created": int(time.time()),
                        "model": request.model,
                        "choices": [{"text": delta, "index": 0, "finish_reason": None}]
                    }
                    yield f"data: {json.dumps(resp)}\n\n"
                elif chunk_msg.get("type") == "chat_done":
                    resp = {
                        "id": request_id,
                        "object": "text_completion",
                        "created": int(time.time()),
                        "model": request.model,
                        "choices": [{"text": "", "index": 0, "finish_reason": "stop"}]
                    }
                    yield f"data: {json.dumps(resp)}\n\n"
                    yield "data: [DONE]\n\n"
                    break
        return StreamingResponse(gen(), media_type="text/event-stream")
    else:
        # Non-streaming
        chat_req = ChatCompletionRequest(
            model=request.model,
            messages=[ChatMessage(role="user", content=prompt)],
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stream=False
        )
        result = await handle_chat_completion(chat_req)
        if isinstance(result, dict):
            content = result["choices"][0]["message"]["content"]
            comp_resp = CompletionResponse(
                model=request.model,
                choices=[CompletionResponseChoice(text=content, index=0, finish_reason="stop")],
                usage=result.get("usage", {})
            )
            return JSONResponse(content=comp_resp.model_dump())
        else:
            raise HTTPException(status_code=500, detail={"error": "Unexpected streaming response for non-streaming request"})

# Legacy OpenAI endpoints without /v1 prefix
@app.post("/chat/completions")
async def chat_completions_legacy(request: ChatCompletionRequest):
    return await chat_completions(request)

# Tool execution endpoint (for ZeroScript compatibility)
@app.post("/api/tool/call")
async def tool_call(request: Request):
    data = await request.json()
    name = data.get("name")
    arguments = data.get("arguments", {})
    timeout = data.get("timeout", 120)
    try:
        result = await asyncio.to_thread(mcp_manager.call, name, arguments, timeout)
        return JSONResponse(content={"ok": True, **result})
    except Exception as e:
        return JSONResponse(content={"ok": False, "error": str(e)}, status_code=500)

@app.get("/api/browsers")
async def list_browsers():
    return {"browsers": [c.to_dict() for c in ws_manager.get_all_clients()]}

@app.get("/api/stats")
async def api_stats():
    clients = ws_manager.get_all_clients()
    by_provider = {}
    for c in clients:
        by_provider[c.provider] = by_provider.get(c.provider, 0) + 1
    return {
        "total_requests": ws_manager.total_requests if hasattr(ws_manager, 'total_requests') else 0,
        "connected_clients": len(clients),
        "by_provider": by_provider,
        "browsers": [c.to_dict() for c in clients],
        "uptime": __import__("time").time()
    }

# For compatibility with old bridge port
@app.get("/api/tools")
async def list_tools():
    return {"tools": mcp_manager.list_tools(), "servers": mcp_manager.health()}

# Additional OpenAI-compatible stubs

@app.post("/v1/embeddings")
async def embeddings(request: Request):
    data = await request.json()
    model = data.get("model", "text-embedding-ada-002")
    input_text = data.get("input", "")
    # Mock embedding - in real implementation would route to browser or use local model
    # For now return a dummy embedding
    import hashlib
    import random
    # Deterministic pseudo-embedding based on input hash
    texts = input_text if isinstance(input_text, list) else [input_text]
    embeddings_data = []
    for idx, txt in enumerate(texts):
        # Create deterministic 1536-dim embedding
        h = hashlib.md5(txt.encode()).hexdigest()
        random.seed(int(h[:8], 16))
        emb = [random.uniform(-1, 1) for _ in range(1536)]
        # Normalize
        norm = sum(x*x for x in emb) ** 0.5
        emb = [x/norm for x in emb] if norm else emb
        embeddings_data.append({
            "object": "embedding",
            "index": idx,
            "embedding": emb
        })
    
    return {
        "object": "list",
        "data": embeddings_data,
        "model": model,
        "usage": {
            "prompt_tokens": sum(estimate_tokens(t) for t in texts),
            "total_tokens": sum(estimate_tokens(t) for t in texts)
        }
    }

@app.post("/v1/images/generations")
async def image_generations(request: Request):
    # Stub - browser AI chats don't generate images via API
    return JSONResponse(
        status_code=501,
        content={
            "error": {
                "message": "Image generation not supported in browser mode. Use chat with image generation capability (e.g. ChatGPT with DALL-E) via chat completions.",
                "type": "not_supported",
                "code": "image_generation_not_supported"
            }
        }
    )

@app.get("/v1/engines")
async def list_engines():
    # Legacy endpoint
    return await list_models()

@app.post("/v1/chat/completions/tool-test")
async def tool_test(request: Request):
    """Test endpoint to check tool parsing via ZeroScript parser"""
    data = await request.json()
    text = data.get("text", "")
    # Simple heuristic for ZeroScript command detection (from parser.js logic)
    import re
    has_command = bool(re.search(r'"command"\s*:\s*"', text) or "###LUA###" in text or "###MCP_TOOL###" in text)
    return {
        "has_tool_call": has_command,
        "text": text[:500],
        "note": "Uses ZeroScript parser logic from core/parser.js"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
