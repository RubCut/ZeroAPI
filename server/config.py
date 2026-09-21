import os
from typing import Dict

# Server config
HOST = os.environ.get("ZEROAPI_HOST", "0.0.0.0")
PORT = int(os.environ.get("ZEROAPI_PORT", "8000"))
WS_PORT = int(os.environ.get("ZEROAPI_WS_PORT", "8000"))  # same as HTTP via FastAPI

# For backward compat with old bridge
BRIDGE_PORT = int(os.environ.get("ZS_BRIDGE_PORT", "17613"))

# Model -> Provider mapping
MODEL_PROVIDER_MAP: Dict[str, str] = {
    # DeepSeek
    "deepseek-chat": "deepseek",
    "deepseek-reasoner": "deepseek",
    "deepseek": "deepseek",
    "deepseek-v3": "deepseek",
    "deepseek-r1": "deepseek",
    # ChatGPT / OpenAI
    "gpt-4": "chatgpt",
    "gpt-4o": "chatgpt",
    "gpt-4o-mini": "chatgpt",
    "gpt-3.5-turbo": "chatgpt",
    "chatgpt": "chatgpt",
    "o1": "chatgpt",
    "o1-mini": "chatgpt",
    "o3-mini": "chatgpt",
    # Gemini
    "gemini": "gemini",
    "gemini-pro": "gemini",
    "gemini-1.5-pro": "gemini",
    "gemini-2.0-flash": "gemini",
    # Kimi
    "kimi": "kimi",
    "moonshot": "kimi",
    "kimi-k2": "kimi",
    # GLM
    "glm": "glm",
    "glm-4": "glm",
    "zhipu": "glm",
    # Qwen
    "qwen": "qwen",
    "qwen2": "qwen",
    "qwen-turbo": "qwen",
    # Arena
    "arena": "arena",
    # Meta
    "meta": "meta",
    "llama": "meta",
    "llama-3": "meta",
}

# Reverse map provider -> default model name
PROVIDER_DEFAULT_MODEL = {
    "deepseek": "deepseek-chat",
    "chatgpt": "gpt-4o",
    "gemini": "gemini-2.0-flash",
    "kimi": "kimi-k2",
    "glm": "glm-4",
    "qwen": "qwen-turbo",
    "arena": "arena",
    "meta": "llama-3",
}

# Provider -> chat domain for routing
PROVIDER_DOMAINS = {
    "deepseek": "https://chat.deepseek.com",
    "chatgpt": "https://chatgpt.com",
    "gemini": "https://gemini.google.com",
    "kimi": "https://www.kimi.com",
    "glm": "https://chat.z.ai",
    "qwen": "https://chat.qwen.ai",
    "arena": "https://arena.ai",
    "meta": "https://www.meta.ai",
}

# All available models for /v1/models endpoint
ALL_MODELS = [
    {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek", "provider": "deepseek"},
    {"id": "deepseek-reasoner", "object": "model", "owned_by": "deepseek", "provider": "deepseek"},
    {"id": "gpt-4o", "object": "model", "owned_by": "openai", "provider": "chatgpt"},
    {"id": "gpt-4o-mini", "object": "model", "owned_by": "openai", "provider": "chatgpt"},
    {"id": "gpt-4", "object": "model", "owned_by": "openai", "provider": "chatgpt"},
    {"id": "gpt-3.5-turbo", "object": "model", "owned_by": "openai", "provider": "chatgpt"},
    {"id": "gemini-2.0-flash", "object": "model", "owned_by": "google", "provider": "gemini"},
    {"id": "gemini-1.5-pro", "object": "model", "owned_by": "google", "provider": "gemini"},
    {"id": "kimi-k2", "object": "model", "owned_by": "moonshot", "provider": "kimi"},
    {"id": "glm-4", "object": "model", "owned_by": "zhipu", "provider": "glm"},
    {"id": "qwen-turbo", "object": "model", "owned_by": "qwen", "provider": "qwen"},
    {"id": "llama-3", "object": "model", "owned_by": "meta", "provider": "meta"},
    {"id": "arena", "object": "model", "owned_by": "arena", "provider": "arena"},
    # Generic aliases
    {"id": "auto", "object": "model", "owned_by": "zeroapi", "provider": "auto"},
]

# Timeouts
CHAT_TIMEOUT = 180  # seconds for full chat completion
STREAM_POLL_INTERVAL = 0.2
