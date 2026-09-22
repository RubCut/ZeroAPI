import asyncio
import json
import time
import uuid
from typing import Dict, Optional, Any, List
from fastapi import WebSocket
import logging

logger = logging.getLogger("zeroapi.ws")

class BrowserClient:
    def __init__(self, client_id: str, websocket: WebSocket, provider: str = "unknown", url: str = "", user_agent: str = ""):
        self.id = client_id
        self.ws = websocket
        self.provider = provider.lower() if provider else "unknown"
        self.url = url
        self.user_agent = user_agent
        self.connected_at = time.time()
        self.last_seen = time.time()
        self.busy = False
        self.current_request_id: Optional[str] = None
        self.version: str = ""
        self.tab_id: Optional[int] = None
        self.providers: List[str] = []  # available providers from extension (auto-switch)
        self.settings: Dict[str, Any] = {}
        self.active_tab: Optional[Dict[str, Any]] = None

    def to_dict(self):
        return {
            "id": self.id,
            "provider": self.provider,
            "providers": self.providers,
            "url": self.url,
            "busy": self.busy,
            "current_request": self.current_request_id,
            "connected_at": self.connected_at,
            "last_seen": self.last_seen,
            "version": self.version,
            "settings": self.settings,
            "active_tab": self.active_tab,
        }

class WSManager:
    def __init__(self):
        self.clients: Dict[str, BrowserClient] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}  # request_id -> Future
        self.stream_queues: Dict[str, asyncio.Queue] = {}  # request_id -> Queue for streaming chunks
        self.lock = asyncio.Lock()

    async def register_client(self, websocket: WebSocket, data: dict) -> BrowserClient:
        client_id = data.get("client_id") or f"browser-{uuid.uuid4().hex[:8]}"
        provider = data.get("provider", "unknown")
        url = data.get("url", "")
        version = data.get("version", "")
        tab_id = data.get("tab_id")
        providers = data.get("providers", [])
        settings = data.get("settings", {})
        active_tab = data.get("activeTab") or data.get("active_tab")

        async with self.lock:
            if client_id in self.clients:
                client = self.clients[client_id]
                client.ws = websocket
                client.provider = provider.lower()
                client.url = url
                client.last_seen = time.time()
                client.version = version
                client.tab_id = tab_id
                if providers:
                    client.providers = [p.lower() for p in providers]
                if settings:
                    client.settings = settings
                if active_tab:
                    client.active_tab = active_tab
            else:
                client = BrowserClient(client_id, websocket, provider, url)
                client.version = version
                client.tab_id = tab_id
                client.providers = [p.lower() for p in providers] if providers else []
                client.settings = settings
                client.active_tab = active_tab
                self.clients[client_id] = client
            logger.info(f"Registered browser client {client_id} provider={provider} providers={providers} url={url[:80]}")
            return client

    async def unregister_client(self, client_id: str):
        async with self.lock:
            if client_id in self.clients:
                del self.clients[client_id]
                logger.info(f"Unregistered browser client {client_id}")

    async def get_client(self, client_id: str) -> Optional[BrowserClient]:
        async with self.lock:
            return self.clients.get(client_id)

    def get_all_clients(self) -> List[BrowserClient]:
        return list(self.clients.values())

    def get_connected_clients(self) -> List[BrowserClient]:
        # Alias for compatibility
        return self.get_all_clients()

    def get_available_clients(self, provider: Optional[str] = None) -> List[BrowserClient]:
        clients = self.get_all_clients()
        # Filter by provider if specified and not auto
        if provider and provider != "auto":
            prov_lower = provider.lower()
            # First try exact provider match
            filtered = [c for c in clients if c.provider == prov_lower]
            # Then try clients that have this provider in their available providers list (auto-switch)
            if not filtered:
                filtered = [c for c in clients if prov_lower in [p.lower() for p in c.providers]]
            if filtered:
                clients = filtered
        # Prefer not busy
        available = [c for c in clients if not c.busy]
        return available if available else clients  # fallback to busy if none free

    async def select_client(self, provider: Optional[str] = None) -> Optional[BrowserClient]:
        available = self.get_available_clients(provider)
        if not available:
            return None
        # Simple round-robin: pick least recently used
        available.sort(key=lambda c: c.last_seen)
        return available[0]

    def select_client_for_model(self, model: str) -> Optional[BrowserClient]:
        # Sync helper for tests / simple routing - uses get_available_clients
        from .config import MODEL_PROVIDER_MAP
        provider = MODEL_PROVIDER_MAP.get(model.lower(), "auto")
        available = self.get_available_clients(provider if provider != "auto" else None)
        if not available:
            return None
        available.sort(key=lambda c: c.last_seen)
        return available[0]

    async def send_to_client(self, client: BrowserClient, message: dict):
        try:
            await client.ws.send_text(json.dumps(message))
            client.last_seen = time.time()
        except Exception as e:
            logger.error(f"Failed to send to client {client.id}: {e}")
            raise

    async def handle_client_message(self, client: BrowserClient, message: dict):
        msg_type = message.get("type")
        req_id = message.get("id") or message.get("request_id")

        if msg_type == "pong" or msg_type == "heartbeat" or msg_type == "ping":
            client.last_seen = time.time()
            # Update providers list if present in ping
            if message.get("providers"):
                client.providers = [p.lower() for p in message.get("providers", [])]
            if message.get("activeTab"):
                client.active_tab = message.get("activeTab")
            return

        if msg_type == "providers_update":
            client.providers = [p.lower() for p in message.get("providers", [])]
            client.active_tab = message.get("activeTab", client.active_tab)
            client.last_seen = time.time()
            logger.info(f"Client {client.id} updated providers: {client.providers} active={client.active_tab}")
            return

        if msg_type == "register" or msg_type == "hello":
            client.provider = message.get("provider", client.provider)
            client.url = message.get("url", client.url)
            client.version = message.get("version", client.version)
            if message.get("providers"):
                client.providers = [p.lower() for p in message.get("providers", [])]
            if message.get("settings"):
                client.settings = message.get("settings", {})
            if message.get("activeTab"):
                client.active_tab = message.get("activeTab")
            client.last_seen = time.time()
            return

        if msg_type in ("chat_chunk", "chat_response", "chat_error", "chat_done"):
            # Route to pending request
            if req_id and req_id in self.stream_queues:
                await self.stream_queues[req_id].put(message)
            if req_id and req_id in self.pending_requests:
                # For non-streaming, we may complete on chat_response
                if msg_type in ("chat_response", "chat_error"):
                    fut = self.pending_requests.get(req_id)
                    if fut and not fut.done():
                        fut.set_result(message)
            return

        # Generic tool_result or other messages for MCP compatibility
        if req_id and req_id in self.pending_requests:
            fut = self.pending_requests[req_id]
            if not fut.done():
                fut.set_result(message)

    async def send_chat_request(self, client: BrowserClient, request_id: str, payload: dict, timeout: int = 180) -> dict:
        """Send chat request to browser and wait for final response (non-streaming)"""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        queue = asyncio.Queue()

        async with self.lock:
            self.pending_requests[request_id] = future
            self.stream_queues[request_id] = queue

        client.busy = True
        client.current_request_id = request_id

        try:
            await self.send_to_client(client, payload)
            # Wait for final response
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        finally:
            async with self.lock:
                self.pending_requests.pop(request_id, None)
                self.stream_queues.pop(request_id, None)
            client.busy = False
            client.current_request_id = None

    async def send_chat_request_stream(self, client: BrowserClient, request_id: str, payload: dict):
        """Generator for streaming chat: yields chunks as they arrive from browser"""
        queue = asyncio.Queue()

        async with self.lock:
            self.stream_queues[request_id] = queue

        client.busy = True
        client.current_request_id = request_id

        try:
            await self.send_to_client(client, payload)

            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=180)
                except asyncio.TimeoutError:
                    yield {"type": "chat_error", "id": request_id, "error": "Timeout waiting for browser response"}
                    break

                msg_type = msg.get("type")
                if msg_type == "chat_chunk":
                    yield msg
                elif msg_type == "chat_response" or msg_type == "chat_done":
                    # Final chunk may contain content
                    if msg.get("content"):
                        yield {"type": "chat_chunk", "id": request_id, "delta": msg.get("content", ""), "done": False}
                    yield {"type": "chat_done", "id": request_id, "content": msg.get("content", ""), "done": True}
                    break
                elif msg_type == "chat_error":
                    yield msg
                    break

        finally:
            async with self.lock:
                self.stream_queues.pop(request_id, None)
            client.busy = False
            client.current_request_id = None

# Global manager instance
ws_manager = WSManager()
