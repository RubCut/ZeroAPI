"""
ZeroAPI Server Tests - no browser required
Tests OpenAI-compatible endpoints, health, model listing, etc.
"""
import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from server.main import app
from server.config import MODEL_PROVIDER_MAP, PROVIDER_DOMAINS

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    print("✓ /health ok")

def test_models():
    r = client.get("/v1/models")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert len(data["data"]) >= 14
    # Check all exposed models have provider
    ids = [m["id"] for m in data["data"]]
    for m in data["data"]:
        assert "provider" in m or "owned_by" in m
    # Check core models present
    for core in ["deepseek-chat", "gpt-4o", "gemini-2.0-flash", "kimi-k2", "glm-4", "qwen-turbo", "llama-3", "auto"]:
        assert core in ids, f"Missing core model {core}"
    print(f"✓ /v1/models ok ({len(data['data'])} models)")

def test_chat_completions_no_client():
    # Should return 503 when no browser connected
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "hello"}]
    }
    r = client.post("/v1/chat/completions", json=payload)
    # Expect 503 no client, or 200 if somehow connected (should be 503 in test env)
    assert r.status_code in (503, 200), f"Expected 503 or 200, got {r.status_code}: {r.text}"
    if r.status_code == 503:
        data = r.json()
        # FastAPI wraps detail
        msg = str(data)
        assert "browser" in msg.lower() or "no" in msg.lower()
        print("✓ /v1/chat/completions correctly returns 503 when no browser")
    else:
        print("✓ /v1/chat/completions returned 200 (browser connected)")

def test_chat_completions_invalid_model():
    payload = {
        "model": "nonexistent-model-xyz",
        "messages": [{"role": "user", "content": "hello"}]
    }
    r = client.post("/v1/chat/completions", json=payload)
    assert r.status_code == 400
    print("✓ Invalid model returns 400")

def test_embeddings():
    r = client.post("/v1/embeddings", json={"model": "text-embedding-ada-002", "input": "hello world"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["data"]) == 1
    assert len(data["data"][0]["embedding"]) == 1536
    print("✓ /v1/embeddings ok")

def test_embeddings_batch():
    r = client.post("/v1/embeddings", json={"model": "text-embedding-ada-002", "input": ["hello", "world"]})
    assert r.status_code == 200
    data = r.json()
    assert len(data["data"]) == 2
    print("✓ /v1/embeddings batch ok")

def test_dashboard():
    r = client.get("/")
    assert r.status_code == 200
    assert "ZeroAPI" in r.text
    print("✓ / dashboard ok")

def test_legacy_status():
    r = client.get("/status")
    assert r.status_code == 200
    assert "ZeroAPI" in r.text
    print("✓ /status legacy ok")

def test_api_status():
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "connected_clients" in data
    print(f"✓ /api/status ok ({data['connected_clients']} clients)")

def test_api_stats():
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_requests" in data
    print("✓ /api/stats ok")

def test_ws_manager():
    from server.ws_manager import WSManager
    mgr = WSManager()
    # Initially empty
    assert mgr.get_connected_clients() == []
    # Model routing
    client = mgr.select_client_for_model("deepseek-chat")
    assert client is None
    print("✓ WSManager basic ok")

def test_provider_domains():
    # Ensure all providers have domains
    for provider, domain in PROVIDER_DOMAINS.items():
        assert domain.startswith("https://"), f"Invalid domain for {provider}"
    print(f"✓ PROVIDER_DOMAINS ok ({len(PROVIDER_DOMAINS)} providers)")

def test_model_provider_map():
    for model, provider in MODEL_PROVIDER_MAP.items():
        assert provider in PROVIDER_DOMAINS, f"Provider {provider} for model {model} not in PROVIDER_DOMAINS"
    print(f"✓ MODEL_PROVIDER_MAP ok ({len(MODEL_PROVIDER_MAP)} mappings)")

if __name__ == "__main__":
    test_health()
    test_models()
    test_chat_completions_no_client()
    test_chat_completions_invalid_model()
    test_embeddings()
    test_embeddings_batch()
    test_dashboard()
    test_legacy_status()
    test_api_status()
    test_api_stats()
    test_ws_manager()
    test_provider_domains()
    test_model_provider_map()
    print("\nAll tests passed! 🎉")
