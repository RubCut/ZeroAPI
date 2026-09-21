"""
ZeroAPI Server - OpenAI Compatible API Server based on ZeroScript
v2.2.2 - Active models + test API for AI News plugin / Smartspacer
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

from .config import HOST, PORT, MODEL_PROVIDER_MAP, ALL_MODELS, PROVIDER_DEFAULT_MODEL, CHAT_TIMEOUT, PROVIDER_DOMAINS
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(mcp_manager.load_config)
        def _start():
            try:
                mcp_manager.start_all()
            except Exception as e:
                logger.warning(f"MCP start failed (optional): {e}")
        threading.Thread(target=_start, daemon=True).start()
    except Exception as e:
        logger.warning(f"MCP init failed: {e}")
    logger.info(f"ZeroAPI Server v2.2.2 starting on {HOST}:{PORT}")
    yield
    for client in mcp_manager.clients.values():
        try:
            client.stop()
        except:
            pass

app = FastAPI(
    title="ZeroAPI - OpenAI Compatible Server",
    description="OpenAI-compatible API server powered by browser automation. Site names as model ids: deepseek, gemini, chatgpt, kimi, glm, qwen, meta, arena.",
    version="2.2.2",
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
    if not messages:
        return ""
    if len(messages) == 1 and messages[0].role == "user":
        content = messages[0].content
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            texts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    texts.append(part.get("text", ""))
            return "\n".join(texts)
    parts = []
    for msg in messages:
        role = msg.role
        content = msg.content or ""
        if isinstance(content, list):
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
    return "\n\n".join(parts)

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def get_active_providers() -> set:
    clients = ws_manager.get_all_clients()
    return set(c.provider for c in clients)

def get_active_models_data():
    """Return models filtered by active browsers, plus provider status"""
    clients = ws_manager.get_all_clients()
    active_providers = get_active_providers()
    # If no clients, all models are considered available (for listing), but none active
    if not clients:
        return ALL_MODELS, active_providers, []
    # Filter: only models whose provider is connected
    # Prioritize simple site-name models first
    simple_ids = {"deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena"}
    active_models = [m for m in ALL_MODELS if m["provider"] in active_providers or m["provider"] == "auto"]
    # Sort: simple names first, then active providers
    active_models.sort(key=lambda m: (0 if m["id"] in simple_ids else 1, m["id"]))
    return active_models, active_providers, clients

# --- WebSocket endpoint for browser extension ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = None
    client: Optional[BrowserClient] = None
    try:
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
                await websocket.send_text(json.dumps({
                    "type": "registered",
                    "client_id": client_id,
                    "server": "ZeroAPI v2.2.2",
                    "message": f"Registered as {client.provider} client"
                }))
                continue
            if client is None:
                client_id = data.get("client_id") or f"browser-{uuid.uuid4().hex[:8]}"
                client = await ws_manager.register_client(websocket, data)
                client_id = client.id
            if client:
                client.last_seen = time.time()
            if client:
                await ws_manager.handle_client_message(client, data)
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "id": data.get("id")}))
            elif msg_type == "studio_status":
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

# --- Dashboard ---
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    clients = ws_manager.get_all_clients()
    active_models, active_providers, _ = get_active_models_data()
    
    client_rows = ""
    for c in clients:
        status = "🟢 Busy" if c.busy else "🟢 Ready"
        client_rows += f"<tr><td>{c.id}</td><td><code>{c.provider}</code></td><td>{status}</td><td>{c.url[:60]}</td><td>{time.strftime('%H:%M:%S', time.localtime(c.last_seen))}</td></tr>"
    if not client_rows:
        client_rows = "<tr><td colspan='5' style='text-align:center; color:#888;'>No browsers connected. Install extension and open chat.deepseek.com or chatgpt.com<br>Then click 'Use this chat' in bar</td></tr>"

    simple_models = [m for m in ALL_MODELS if m["id"] in {"deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena"}]

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>ZeroAPI - OpenAI Compatible Server</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1100px; margin: 0 auto; padding: 20px; background: #0a0a0a; color: #e0e0e0; }}
        h1 {{ color: #fff; border-bottom: 1px solid #333; padding-bottom: 10px; }}
        .card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 10px; padding: 20px; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #333; }}
        th {{ color: #888; font-weight: 600; }}
        code {{ background: #222; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
        .badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.85em; background: #222; border: 1px solid #333; margin: 2px; }}
        .badge.green {{ background: #0a2; color: #fff; border-color: #0a2; }}
        .badge.blue {{ background: #0a84ff22; color: #0a84ff; border-color: #0a84ff44; }}
        .endpoint {{ display: flex; align-items: center; gap: 10px; margin: 10px 0; flex-wrap: wrap; }}
        .method {{ background: #0a84ff; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
        .method.get {{ background: #30d158; }}
        a {{ color: #0a84ff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .logo {{ font-size: 1.5em; margin-right: 10px; }}
        .active-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #30d158; display: inline-block; margin-right: 6px; box-shadow: 0 0 6px #30d158; }}
        .inactive-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #666; display: inline-block; margin-right: 6px; }}
    </style>
</head>
<body>
    <h1><span class="logo">⚡</span> ZeroAPI Server v2.2.2 — site names as models</h1>
    <p>OpenAI-compatible API. Use <code>model=\"deepseek\"</code> / <code>gemini</code> / <code>chatgpt</code> etc. — simple site names.</p>
    
    <div class="card">
        <h3>📡 Connected Browsers ({len(clients)}) — Active providers: {', '.join(active_providers) if active_providers else 'none'}</h3>
        <table>
            <tr><th>ID</th><th>Provider (model id)</th><th>Status</th><th>URL</th><th>Last Seen</th></tr>
            {client_rows}
        </table>
    </div>

    <div class="card">
        <h3>🤖 Active Models (site names) — for AI News plugin / Smartspacer</h3>
        <p>These are the models your plugin should show. Only connected browsers are listed as active.</p>
        <div style="display:flex; flex-wrap:wrap; gap:8px; margin:12px 0;">
            {"".join(f'<span class="badge {"green" if m["provider"] in active_providers else ""}"><span class="{"active-dot" if m["provider"] in active_providers else "inactive-dot"}"></span>{m["id"]} → {m["provider"]} {"✅ active" if m["provider"] in active_providers else "○ offline"}</span>' for m in simple_models)}
        </div>
        <p style="color:#888; font-size:0.9em;">Fetch via <code>GET /v1/models</code> (only active if browsers connected) or <code>GET /api/active-models</code> or <code>GET /zeroapi/&lt;model&gt;</code></p>
    </div>

    <div class="card">
        <h3>🔌 API Endpoints — Test & Fetch</h3>
        <div class="endpoint"><span class="method get">GET</span> <code>/v1/models</code> - List active models (filters to connected browsers)</div>
        <div class="endpoint"><span class="method get">GET</span> <code>/v1/models/active</code> / <code>/api/active-models</code> - Only active models with status</div>
        <div class="endpoint"><span class="method get">GET</span> <code>/zeroapi/&lt;model&gt;</code> - Test API for model, e.g. <a href="/zeroapi/deepseek">/zeroapi/deepseek</a>, <a href="/zeroapi/gemini">/zeroapi/gemini</a></div>
        <div class="endpoint"><span class="method get">GET</span> <code>/api/test</code> - Quick test all providers</div>
        <div class="endpoint"><span class="method">POST</span> <code>/api/test</code> - Test chat: {{"model":"deepseek","prompt":"Hello"}}</div>
        <div class="endpoint"><span class="method get">GET</span> <code>/test</code> - Interactive test page</div>
        <div class="endpoint"><span class="method">POST</span> <code>/v1/chat/completions</code> - OpenAI compatible chat</div>
        <div class="endpoint"><span class="method get">GET</span> <code>/health</code> / <code>/api/status</code> - Status</div>
    </div>

    <div class="card">
        <h3>💻 Usage for AI News Plugin</h3>
        <pre style="background:#111; padding:15px; border-radius:6px; overflow-x:auto;"><code>// 1. Fetch active models for plugin dropdown
fetch('http://localhost:{PORT}/api/active-models')
  .then(r=>r.json()).then(data=>console.log(data.active_models))

// 2. Test API (like zeroapi/deepseek)
fetch('http://localhost:{PORT}/zeroapi/deepseek')
  .then(r=>r.json()).then(console.log)

// 3. Use as OpenAI API
import openai
client = openai.OpenAI(base_url="http://localhost:{PORT}/v1", api_key="x")
resp = client.chat.completions.create(
  model="deepseek",  # or gemini, chatgpt, kimi...
  messages=[{{"role":"user","content":"Summarize news: EU AI Act"}}]
)
</code></pre>
    </div>

    <div class="card" style="text-align:center; color:#666; font-size:0.85em;">
        ZeroAPI v2.2.2 | site names as models: deepseek, gemini, chatgpt, kimi, glm, qwen, meta, arena<br>
        <a href="https://github.com/RubCut/ZeroAPI">GitHub</a> | <a href="/test">Test page</a> | <a href="/v1/models">/v1/models</a> | <a href="/api/active-models">/api/active-models</a>
    </div>
    <script>setTimeout(()=>location.reload(), 5000);</script>
</body>
</html>
    """
    return HTMLResponse(content=html)

@app.get("/status", response_class=HTMLResponse)
async def legacy_status_page():
    return await dashboard()

@app.get("/health")
async def health():
    clients = ws_manager.get_all_clients()
    active_providers = list(get_active_providers())
    return {
        "status": "ok",
        "version": "2.2.2",
        "browsers_connected": len(clients),
        "active_providers": active_providers,
        "active_models": [m["id"] for m in ALL_MODELS if m["provider"] in active_providers or m["id"] in active_providers],
        "browsers": [c.to_dict() for c in clients],
        "mcp_servers": mcp_manager.health(),
        "uptime": time.time(),
    }

@app.get("/api/status")
async def api_status():
    data = await health()
    data["connected_clients"] = data.get("browsers_connected", 0)
    data["total_requests"] = 0
    return data

# --- Models endpoints with active filtering ---

@app.get("/v1/models")
async def list_models(active_only: bool = False, simple: bool = False):
    """
    For AI News plugin compatibility:
    - Default: return simple site-name models (deepseek, chatgpt, gemini...) always, so plugin dropdown shows all options
    - ?active_only=true: only models with connected browsers
    - ?simple=true: only simple 8 models + auto (for minimal UI)
    - ?simple=false (default false but we still prioritize simple): if no ?active_only, return simple models + auto (8) for plugin, full list for OpenAI SDK compatibility via ?simple=false&active_only=false returns all
    """
    clients = ws_manager.get_all_clients()
    active_providers = get_active_providers()
    
    SIMPLE_IDS = {"deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena","auto"}
    
    if active_only:
        if not clients:
            filtered = [m for m in ALL_MODELS if m["id"] in SIMPLE_IDS]
        else:
            filtered = [m for m in ALL_MODELS if (m["provider"] in active_providers or m["id"] in active_providers) and m["id"] in SIMPLE_IDS]
            if not filtered:
                filtered = [m for m in ALL_MODELS if m["id"] in SIMPLE_IDS and (m["provider"] in active_providers or m["id"] in active_providers)]
    else:
        if simple:
            filtered = [m for m in ALL_MODELS if m["id"] in SIMPLE_IDS]
        else:
            # Default for AI News plugin: return simple models always (so dropdown shows all), not filtered
            # This ensures fetch models works even if only 1 browser connected
            filtered = [m for m in ALL_MODELS if m["id"] in SIMPLE_IDS]
            # If client explicitly wants all, they can use ?simple=false&all=true? For now keep simple as default for plugin
            # To get full list, use /v1/models?simple=false&all=true via custom handling — we return simple for now for better UX

    # Sort simple first in defined order
    order = ["deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena","auto"]
    filtered.sort(key=lambda m: order.index(m["id"]) if m["id"] in order else 99)

    cards = []
    for m in filtered:
        cards.append(ModelCard(id=m["id"], owned_by=m["owned_by"]))
    return ModelList(data=cards)

@app.get("/v1/models/all")
async def list_all_models():
    """Full list for OpenAI SDK compatibility"""
    cards = [ModelCard(id=m["id"], owned_by=m["owned_by"]) for m in ALL_MODELS]
    return ModelList(data=cards)

@app.get("/v1/models/active")
async def list_active_models_v1():
    active_models, active_providers, clients = get_active_models_data()
    cards = [ModelCard(id=m["id"], owned_by=m["owned_by"]) for m in active_models]
    return {
        "object": "list",
        "data": [c.model_dump() for c in cards],
        "active_providers": list(active_providers),
        "active_models": [m["id"] for m in active_models],
        "browsers": [c.to_dict() for c in clients],
    }

@app.get("/api/active-models")
async def api_active_models():
    active_models, active_providers, clients = get_active_models_data()
    simple = [m for m in active_models if m["id"] in {"deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena","auto"}]
    return {
        "active_providers": list(active_providers),
        "active_models": [m["id"] for m in simple] if clients else [m["id"] for m in ALL_MODELS if m["id"] in {"deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena","auto"}],
        "all_active_models": [m["id"] for m in active_models],
        "models_detailed": active_models,
        "browsers": [c.to_dict() for c in clients],
        "browsers_count": len(clients),
        "timestamp": time.time(),
    }

@app.get("/api/models/active")
async def api_models_active_alias():
    return await api_active_models()

# --- ZeroAPI test endpoints: /zeroapi/<model> like user requested ---
@app.get("/zeroapi")
async def zeroapi_root():
    active_models, active_providers, clients = get_active_models_data()
    return {
        "message": "ZeroAPI test endpoints — use /zeroapi/{model} like /zeroapi/deepseek",
        "available_models": [m["id"] for m in ALL_MODELS if m["id"] in {"deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena"}],
        "active_models": [m["id"] for m in active_models if m["id"] in {"deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena"}] if clients else [],
        "active_providers": list(active_providers),
        "browsers_connected": len(clients),
        "examples": {
            "deepseek": "/zeroapi/deepseek",
            "gemini": "/zeroapi/gemini",
            "chatgpt": "/zeroapi/chatgpt",
            "test_all": "/api/test",
            "models": "/v1/models",
            "active": "/api/active-models"
        }
    }

@app.get("/zeroapi/{model_id}")
async def zeroapi_model_test(model_id: str):
    model_id = model_id.lower()
    if not is_valid_model(model_id):
        raise HTTPException(status_code=404, detail={"error": f"Model '{model_id}' not found. Available: deepseek, gemini, chatgpt, kimi, glm, qwen, meta, arena"})
    
    provider = get_provider_for_model(model_id)
    clients = ws_manager.get_all_clients()
    active_providers = get_active_providers()
    
    # Find browsers for this provider
    provider_clients = [c for c in clients if c.provider == provider]
    is_active = provider in active_providers
    
    # Domain hint
    domain = PROVIDER_DOMAINS.get(provider, f"https://{provider}.com")
    
    return {
        "model": model_id,
        "provider": provider,
        "status": "active" if is_active else "offline",
        "is_active": is_active,
        "browsers_for_provider": len(provider_clients),
        "browsers": [c.to_dict() for c in provider_clients],
        "all_active_providers": list(active_providers),
        "total_browsers": len(clients),
        "test": {
            "curl": f'curl http://localhost:{PORT}/v1/chat/completions -H "Content-Type: application/json" -d \'{{"model":"{model_id}","messages":[{{"role":"user","content":"Hello!"}}]}}\'',
            "openai_sdk": f'openai.OpenAI(base_url="http://localhost:{PORT}/v1", api_key="x").chat.completions.create(model="{model_id}", messages=[{{"role":"user","content":"Hello"}}])',
            "fetch_test": f"POST /api/test with {{\"model\":\"{model_id}\",\"prompt\":\"Hello\"}}"
        },
        "domain": domain,
        "message": f"Model {model_id} is {'ready ✅' if is_active else 'offline ❌ - open '+domain+' with extension and click Use this chat'}",
    }

@app.get("/api/test/{model_id}")
async def api_test_model_alias(model_id: str):
    return await zeroapi_model_test(model_id)

# --- General test API ---
@app.get("/api/test")
async def api_test_all():
    clients = ws_manager.get_all_clients()
    active_providers = get_active_providers()
    by_provider = {}
    for c in clients:
        by_provider[c.provider] = by_provider.get(c.provider, 0) + 1
    
    simple_models = ["deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena"]
    test_results = []
    for m in simple_models:
        prov = get_provider_for_model(m)
        is_active = prov in active_providers
        test_results.append({
            "model": m,
            "provider": prov,
            "status": "active" if is_active else "offline",
            "browsers": by_provider.get(prov, 0),
            "test_url": f"/zeroapi/{m}",
            "ready": is_active
        })
    
    return {
        "status": "ok" if clients else "no_browsers",
        "message": f"{len(clients)} browsers connected, {len(active_providers)} providers active" if clients else "No browsers connected — open chat site with extension",
        "browsers_connected": len(clients),
        "active_providers": list(active_providers),
        "by_provider": by_provider,
        "models": test_results,
        "browsers": [c.to_dict() for c in clients],
        "endpoints": {
            "models": "/v1/models",
            "active_models": "/api/active-models",
            "test_model": "/zeroapi/{model} e.g. /zeroapi/deepseek",
            "chat": "POST /v1/chat/completions with model=deepseek/gemini/chatgpt"
        }
    }

@app.post("/api/test")
async def api_test_post(request: Request):
    try:
        data = await request.json()
    except:
        data = {}
    model = data.get("model", "deepseek")
    prompt = data.get("prompt", "Hello! Say hi in one sentence.")
    
    if not is_valid_model(model):
        raise HTTPException(status_code=400, detail={"error": f"Invalid model {model}"})
    
    provider = get_provider_for_model(model)
    client = await ws_manager.select_client(provider if provider != "auto" else None)
    if not client:
        return JSONResponse(status_code=503, content={
            "ok": False,
            "model": model,
            "provider": provider,
            "error": f"No browser for {provider}. Open {PROVIDER_DOMAINS.get(provider, provider)} and click Use this chat",
            "active_providers": list(get_active_providers())
        })
    
    request_id = f"test-{uuid.uuid4().hex[:8]}"
    payload = {
        "type": "chat_request",
        "id": request_id,
        "model": model,
        "provider": provider,
        "messages": [{"role": "user", "content": prompt}],
        "prompt": prompt,
        "stream": False,
    }
    try:
        result = await ws_manager.send_chat_request(client, request_id, payload, timeout=CHAT_TIMEOUT)
        if result.get("type") == "chat_error":
            return JSONResponse(status_code=500, content={"ok": False, "model": model, "error": result.get("error")})
        content = result.get("content", "") or result.get("text", "")
        return {
            "ok": True,
            "model": model,
            "provider": provider,
            "prompt": prompt,
            "response": content,
            "client": client.to_dict()
        }
    except asyncio.TimeoutError:
        return JSONResponse(status_code=504, content={"ok": False, "error": "Timeout — browser didn't respond"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@app.get("/test", response_class=HTMLResponse)
async def test_page():
    clients = ws_manager.get_all_clients()
    active = list(get_active_providers())
    options = "".join(f'<option value="{m}">{m} {"✅" if m in active else "○"}</option>' for m in ["deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena"])
    return HTMLResponse(content=f"""
<!DOCTYPE html>
<html>
<head><title>ZeroAPI Test</title><meta charset="utf-8">
<style>
body{{font-family:system-ui;max-width:800px;margin:0 auto;padding:20px;background:#0a0a0a;color:#e0e0e0}}
.card{{background:#1a1a1a;border:1px solid #333;border-radius:10px;padding:20px;margin:15px 0}}
input,select,textarea{{background:#222;border:1px solid #333;color:#fff;padding:8px 12px;border-radius:6px;width:100%;margin:5px 0}}
button{{background:#0a84ff;color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-weight:600}}
button:hover{{background:#0066cc}}
pre{{background:#111;padding:15px;border-radius:6px;overflow-x:auto;white-space:pre-wrap}}
.badge{{display:inline-block;padding:2px 8px;border-radius:10px;background:#222;border:1px solid #333;margin:2px;font-size:0.85em}}
.badge.active{{background:#0a2;color:#fff}}
</style>
</head>
<body>
<h1>⚡ ZeroAPI Test — /zeroapi/deepseek style</h1>
<div class="card">
<h3>Active: {', '.join(active) if active else 'none — open chat tabs'} | Browsers: {len(clients)}</h3>
<div>{''.join(f'<span class="badge {"active" if m in active else ""}">{m} {"✅" if m in active else "○"}</span>' for m in ["deepseek","chatgpt","gemini","kimi","glm","qwen","meta","arena"])}</div>
<p>Fetch active models: <code>GET /api/active-models</code> | <code>GET /v1/models</code></p>
<p>Test model: <code>GET /zeroapi/deepseek</code> | <code>GET /zeroapi/gemini</code></p>
</div>
<div class="card">
<h3>Quick Test Chat</h3>
<label>Model (site name):</label>
<select id="model">{options}</select>
<label>Prompt:</label>
<textarea id="prompt" rows="3">Hello! Who are you? Reply in one sentence.</textarea>
<button onclick="testChat()">Test API (POST /api/test)</button>
<pre id="result">Result will appear here...</pre>
</div>
<div class="card">
<h3>Fetch Active Models (for AI News plugin)</h3>
<button onclick="fetchModels()">Fetch /api/active-models</button>
<pre id="models"></pre>
</div>
<script>
async function testChat(){{
  const model=document.getElementById('model').value;
  const prompt=document.getElementById('prompt').value;
  const resEl=document.getElementById('result');
  resEl.textContent='Sending to '+model+'...';
  try{{
    const r=await fetch('/api/test',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{model,prompt}})}});
    const j=await r.json();
    resEl.textContent=JSON.stringify(j,null,2);
  }}catch(e){{resEl.textContent='Error: '+e}}
}}
async function fetchModels(){{
  const el=document.getElementById('models');
  el.textContent='Fetching...';
  try{{
    const r=await fetch('/api/active-models'); const j=await r.json();
    el.textContent=JSON.stringify(j,null,2);
  }}catch(e){{el.textContent='Error: '+e}}
}}
fetchModels();
</script>
</body>
</html>
""")

@app.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    for m in ALL_MODELS:
        if m["id"] == model_id:
            return ModelCard(id=m["id"], owned_by=m["owned_by"])
    # Generic if provider exists
    if is_valid_model(model_id):
        return ModelCard(id=model_id, owned_by="zeroapi")
    raise HTTPException(status_code=404, detail={"error": f"Model {model_id} not found"})

async def handle_chat_completion(request: ChatCompletionRequest) -> Dict[str, Any]:
    if not is_valid_model(request.model):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": f"Invalid model '{request.model}'. Available: {[m['id'] for m in ALL_MODELS if m['id'] in {'deepseek','chatgpt','gemini','kimi','glm','qwen','meta','arena','auto'}]}",
                    "type": "invalid_request_error",
                    "code": "model_not_found"
                }
            }
        )
    provider = request.provider or get_provider_for_model(request.model)
    client = await ws_manager.select_client(provider if provider != "auto" else None)
    if not client:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "message": f"No browser connected for provider '{provider}'. Open {PROVIDER_DOMAINS.get(provider, provider)} in browser with ZeroAPI extension installed and click 'Use this chat'. Active: {list(get_active_providers())}",
                    "type": "service_unavailable",
                    "code": "no_browser_connected",
                    "available_browsers": [c.to_dict() for c in ws_manager.get_all_clients()],
                    "active_providers": list(get_active_providers())
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
                    "message": f"Invalid model '{request.model}'. Use /v1/models to list available: deepseek, gemini, chatgpt, kimi, glm, qwen, meta, arena",
                    "type": "invalid_request_error",
                    "code": "model_not_found"
                }
            }
        )
    if request.stream:
        provider = request.provider or get_provider_for_model(request.model)
        client = await ws_manager.select_client(provider if provider != "auto" else None)
        if not client:
            raise HTTPException(status_code=503, detail={"error": {"message": f"No browser connected for provider '{provider}'", "type": "service_unavailable", "active": list(get_active_providers())}})
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
        if isinstance(result, dict):
            return JSONResponse(content=result)
        else:
            client, req_id, payload = result
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
    prompt = request.prompt if isinstance(request.prompt, str) else "\n".join(request.prompt)
    chat_req = ChatCompletionRequest(
        model=request.model,
        messages=[ChatMessage(role="user", content=prompt)],
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        stream=request.stream
    )
    if request.stream:
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

@app.post("/chat/completions")
async def chat_completions_legacy(request: ChatCompletionRequest):
    return await chat_completions(request)

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
    return {"browsers": [c.to_dict() for c in ws_manager.get_all_clients()], "active_providers": list(get_active_providers())}

@app.get("/api/stats")
async def api_stats():
    clients = ws_manager.get_all_clients()
    by_provider = {}
    for c in clients:
        by_provider[c.provider] = by_provider.get(c.provider, 0) + 1
    return {
        "total_requests": ws_manager.total_requests if hasattr(ws_manager, 'total_requests') else 0,
        "connected_clients": len(clients),
        "active_providers": list(by_provider.keys()),
        "by_provider": by_provider,
        "browsers": [c.to_dict() for c in clients],
        "uptime": time.time()
    }

@app.get("/api/tools")
async def list_tools():
    return {"tools": mcp_manager.list_tools(), "servers": mcp_manager.health()}

@app.post("/v1/embeddings")
async def embeddings(request: Request):
    data = await request.json()
    model = data.get("model", "text-embedding-ada-002")
    input_text = data.get("input", "")
    import hashlib, random
    texts = input_text if isinstance(input_text, list) else [input_text]
    embeddings_data = []
    for idx, txt in enumerate(texts):
        h = hashlib.md5(txt.encode()).hexdigest()
        random.seed(int(h[:8], 16))
        emb = [random.uniform(-1, 1) for _ in range(1536)]
        norm = sum(x*x for x in emb) ** 0.5
        emb = [x/norm for x in emb] if norm else emb
        embeddings_data.append({"object": "embedding","index": idx,"embedding": emb})
    return {
        "object": "list",
        "data": embeddings_data,
        "model": model,
        "usage": {"prompt_tokens": sum(estimate_tokens(t) for t in texts),"total_tokens": sum(estimate_tokens(t) for t in texts)}
    }

@app.post("/v1/images/generations")
async def image_generations(request: Request):
    return JSONResponse(
        status_code=501,
        content={"error": {"message": "Image generation not supported in browser mode. Use chat with image generation capability via chat completions.", "type": "not_supported","code": "image_generation_not_supported"}}
    )

@app.get("/v1/engines")
async def list_engines():
    return await list_models()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
