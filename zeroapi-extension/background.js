// ZeroAPI Background - Dual mode: legacy bridge (17613) + new OpenAI API server (8000)
// Based on ZeroScript background.js, extended for ZeroAPI

const LEGACY_PORT = 17613;
const LEGACY_URL = `ws://127.0.0.1:${LEGACY_PORT}`;

const API_PORT = 8000;
const API_URL = `ws://127.0.0.1:${API_PORT}/ws`;

const PROVIDER_URLS = [
  "https://chat.deepseek.com/*",
  "https://chatgpt.com/*",
  "https://chat.openai.com/*",
  "https://gemini.google.com/*",
  "https://www.kimi.ai/*",
  "https://kimi.ai/*",
  "https://chat.z.ai/*",
  "https://chat.qwen.ai/*",
  "https://arena.ai/*",
  "https://www.meta.ai/*",
  "https://meta.ai/*"
];

const RECONNECT_MIN = 1000;
const RECONNECT_MAX = 8000;
const HEARTBEAT_MS = 12000;
const STALE_SOCKET_MS = 30000;
const REQUEST_TIMEOUT_DEFAULT = 130000;

// --- Legacy Bridge (Roblox) ---
let legacyWs = null;
let legacyConnected = false;
let legacyReconnectDelay = RECONNECT_MIN;
let legacyReconnectTimer = null;
let legacyHeartbeatTimer = null;
let legacyLastMessageAt = 0;
let legacyNextId = 1;
const legacyPending = new Map();
let toolsCache = [];
let mcpAlive = false;
let serversCache = [];
let studioConnected = null;
let studioApp = null;
let studioProc = null;

// --- ZeroAPI Server ---
let apiWs = null;
let apiConnected = false;
let apiReconnectDelay = RECONNECT_MIN;
let apiReconnectTimer = null;
let apiHeartbeatTimer = null;
let apiLastMessageAt = 0;
let apiClientId = `ext-${Math.random().toString(36).slice(2,10)}`;
let apiProvider = "unknown"; // will be updated per tab

function log(...a) {
  console.log("[zeroapi-bg]", ...a);
}

// ===== LEGACY BRIDGE =====
function connectLegacy() {
  if (legacyWs && (legacyWs.readyState === WebSocket.OPEN || legacyWs.readyState === WebSocket.CONNECTING)) return;
  clearTimeout(legacyReconnectTimer);
  try {
    legacyWs = new WebSocket(LEGACY_URL);
  } catch (e) {
    log("Legacy WS ctor failed", e);
    scheduleLegacyReconnect();
    return;
  }

  legacyWs.onopen = () => {
    legacyConnected = true;
    legacyReconnectDelay = RECONNECT_MIN;
    legacyLastMessageAt = Date.now();
    log("connected to legacy bridge", LEGACY_URL);
    startLegacyHeartbeat();
    broadcastStatus();
  };

  legacyWs.onmessage = (ev) => {
    legacyLastMessageAt = Date.now();
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    handleLegacyMessage(msg);
  };

  legacyWs.onclose = () => {
    legacyConnected = false;
    mcpAlive = false;
    studioConnected = null;
    studioApp = null;
    studioProc = null;
    serversCache = [];
    stopLegacyHeartbeat();
    failAllLegacyPending("legacy bridge closed");
    broadcastStatus();
    scheduleLegacyReconnect();
  };

  legacyWs.onerror = () => {
    try { legacyWs.close(); } catch {}
  };
}

function scheduleLegacyReconnect() {
  clearTimeout(legacyReconnectTimer);
  legacyReconnectTimer = setTimeout(connectLegacy, legacyReconnectDelay);
  legacyReconnectDelay = Math.min(legacyReconnectDelay * 1.7, RECONNECT_MAX);
}

function startLegacyHeartbeat() {
  stopLegacyHeartbeat();
  legacyHeartbeatTimer = setInterval(() => {
    if (legacyConnected) {
      if (legacyLastMessageAt && Date.now() - legacyLastMessageAt > STALE_SOCKET_MS) {
        log("legacy socket stale, reconnecting");
        try { legacyWs.close(); } catch {}
        return;
      }
      sendLegacy({ type: "ping" }).catch(()=>{});
    }
  }, HEARTBEAT_MS);
}

function stopLegacyHeartbeat() {
  clearInterval(legacyHeartbeatTimer);
  legacyHeartbeatTimer = null;
}

async function sendLegacy(obj, timeout = REQUEST_TIMEOUT_DEFAULT) {
  if (!legacyConnected || !legacyWs || legacyWs.readyState !== WebSocket.OPEN) {
    // try wait
    await waitForLegacyConnection(3000);
  }
  return new Promise((resolve) => {
    if (!legacyConnected || !legacyWs || legacyWs.readyState !== WebSocket.OPEN) {
      resolve({ ok: false, kind: "disconnected", error: "legacy bridge not connected" });
      return;
    }
    const id = legacyNextId++;
    const payload = { ...obj, id };
    const timer = setTimeout(() => {
      if (legacyPending.has(id)) {
        legacyPending.delete(id);
        resolve({ ok: false, kind: "timeout", error: "legacy bridge timeout" });
      }
    }, timeout);
    legacyPending.set(id, { resolve, timer });
    try { legacyWs.send(JSON.stringify(payload)); }
    catch (e) {
      clearTimeout(timer);
      legacyPending.delete(id);
      resolve({ ok: false, kind: "disconnected", error: String(e) });
    }
  });
}

function waitForLegacyConnection(timeout = 5000) {
  return new Promise((resolve) => {
    if (legacyConnected && legacyWs && legacyWs.readyState === WebSocket.OPEN) return resolve(true);
    connectLegacy();
    const t0 = Date.now();
    const iv = setInterval(() => {
      if (legacyConnected && legacyWs && legacyWs.readyState === WebSocket.OPEN) {
        clearInterval(iv); resolve(true);
      } else if (Date.now() - t0 > timeout) {
        clearInterval(iv); resolve(false);
      }
    }, 100);
  });
}

function handleLegacyMessage(msg) {
  if ("studio" in msg) studioConnected = msg.studio;
  if ("studio_app" in msg) studioApp = msg.studio_app;
  if ("studio_proc" in msg) studioProc = msg.studio_proc;
  
  if (msg.type === "studio_status") {
    resolveLegacyPending(msg.id, { ok: true, studio: studioConnected });
    broadcastStatus(); return;
  }
  if (msg.type === "connected") {
    mcpAlive = !!msg.mcp_alive;
    if (Array.isArray(msg.tools)) toolsCache = msg.tools;
    if (Array.isArray(msg.servers)) serversCache = msg.servers;
    broadcastStatus(); return;
  }
  if (msg.type === "pong") { resolveLegacyPending(msg.id, { ok: true }); return; }
  if (msg.type === "tools") {
    if (Array.isArray(msg.tools)) toolsCache = msg.tools;
    if (Array.isArray(msg.servers)) serversCache = msg.servers;
    mcpAlive = !!msg.mcp_alive;
    resolveLegacyPending(msg.id, { ok: true, tools: toolsCache });
    broadcastStatus(); return;
  }
  if (msg.type === "tool_result") {
    resolveLegacyPending(msg.id, msg.ok ? { ok: true, text: msg.text, images: msg.images || [] } : { ok: false, kind: msg.kind, error: msg.error });
    return;
  }
  if (msg.type === "mcp_status") {
    mcpAlive = !!msg.alive;
    if (Array.isArray(msg.tools)) toolsCache = msg.tools;
    if (Array.isArray(msg.servers)) serversCache = msg.servers;
    resolveLegacyPending(msg.id, { ok: !!msg.ok, alive: msg.alive, error: msg.error });
    broadcastStatus(); return;
  }
  if (msg.type === "server_changed") {
    resolveLegacyPending(msg.id, { ok: !!msg.ok, error: msg.error, restarting: !!msg.restarting });
    return;
  }
  if (msg.type === "error") { resolveLegacyPending(msg.id, { ok: false, error: msg.error }); return; }
}

function resolveLegacyPending(id, value) {
  const p = legacyPending.get(id);
  if (!p) return;
  clearTimeout(p.timer);
  legacyPending.delete(id);
  p.resolve(value);
}

function failAllLegacyPending(reason) {
  for (const [, p] of legacyPending) {
    clearTimeout(p.timer);
    p.resolve({ ok: false, kind: "disconnected", error: reason });
  }
  legacyPending.clear();
}

// ===== ZEROAPI SERVER =====
function connectAPI() {
  if (apiWs && (apiWs.readyState === WebSocket.OPEN || apiWs.readyState === WebSocket.CONNECTING)) return;
  clearTimeout(apiReconnectTimer);
  try {
    apiWs = new WebSocket(API_URL);
  } catch (e) {
    log("API WS ctor failed", e);
    scheduleAPIReconnect();
    return;
  }

  apiWs.onopen = () => {
    apiConnected = true;
    apiReconnectDelay = RECONNECT_MIN;
    apiLastMessageAt = Date.now();
    log("connected to ZeroAPI server", API_URL);
    startAPIHeartbeat();
    // Register
    const hello = {
      type: "register",
      client_id: apiClientId,
      provider: apiProvider,
      url: "extension-background",
      version: chrome.runtime.getManifest().version,
      capabilities: ["chat", "stream"]
    };
    try { apiWs.send(JSON.stringify(hello)); } catch {}
    broadcastStatus();
  };

  apiWs.onmessage = async (ev) => {
    apiLastMessageAt = Date.now();
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    await handleAPIMessage(msg);
  };

  apiWs.onclose = () => {
    apiConnected = false;
    stopAPIHeartbeat();
    broadcastStatus();
    scheduleAPIReconnect();
  };

  apiWs.onerror = () => {
    try { apiWs.close(); } catch {}
  };
}

function scheduleAPIReconnect() {
  clearTimeout(apiReconnectTimer);
  apiReconnectTimer = setTimeout(connectAPI, apiReconnectDelay);
  apiReconnectDelay = Math.min(apiReconnectDelay * 1.6, RECONNECT_MAX);
}

function startAPIHeartbeat() {
  stopAPIHeartbeat();
  apiHeartbeatTimer = setInterval(() => {
    if (apiConnected) {
      if (apiLastMessageAt && Date.now() - apiLastMessageAt > STALE_SOCKET_MS) {
        log("API socket stale, reconnecting");
        try { apiWs.close(); } catch {}
        return;
      }
      try { apiWs.send(JSON.stringify({ type: "ping", client_id: apiClientId })); } catch {}
    }
  }, HEARTBEAT_MS);
}

function stopAPIHeartbeat() {
  clearInterval(apiHeartbeatTimer);
  apiHeartbeatTimer = null;
}

async function handleAPIMessage(msg) {
  const type = msg.type;
  const id = msg.id;

  if (type === "pong" || type === "registered" || type === "heartbeat") {
    return;
  }

  if (type === "chat_request") {
    // Route to appropriate browser tab
    log(`Received chat_request ${id} provider=${msg.provider} model=${msg.model}`);
    
    // Find tab with matching provider
    const targetProvider = (msg.provider || "auto").toLowerCase();
    
    chrome.tabs.query({ url: PROVIDER_URLS }, async (tabs) => {
      if (!tabs || !tabs.length) {
        sendAPIError(id, "No chat tabs open. Open chat.deepseek.com or chatgpt.com");
        return;
      }

      let targetTab = null;
      
      if (targetProvider !== "auto") {
        // Try to find tab matching provider
        for (const tab of tabs) {
          const url = tab.url || "";
          if (targetProvider === "deepseek" && url.includes("deepseek")) { targetTab = tab; break; }
          if (targetProvider === "chatgpt" && (url.includes("chatgpt") || url.includes("openai"))) { targetTab = tab; break; }
          if (targetProvider === "gemini" && url.includes("gemini")) { targetTab = tab; break; }
          if (targetProvider === "kimi" && url.includes("kimi")) { targetTab = tab; break; }
          if (targetProvider === "glm" && url.includes("z.ai")) { targetTab = tab; break; }
          if (targetProvider === "qwen" && url.includes("qwen")) { targetTab = tab; break; }
          if (targetProvider === "meta" && url.includes("meta.ai")) { targetTab = tab; break; }
          if (targetProvider === "arena" && url.includes("arena.ai")) { targetTab = tab; break; }
        }
      }
      
      // Fallback to first available tab
      if (!targetTab) targetTab = tabs[0];

      try {
        // Check if tab is busy
        const status = await new Promise((resolve) => {
          chrome.tabs.sendMessage(targetTab.id, { type: "zeroapi-status" }, (resp) => {
            if (chrome.runtime.lastError) resolve({ busy: false });
            else resolve(resp || { busy: false });
          });
        });

        if (status && status.busy) {
          // Try next tab
          const otherTabs = tabs.filter(t => t.id !== targetTab.id);
          for (const t of otherTabs) {
            const s = await new Promise((res) => {
              chrome.tabs.sendMessage(t.id, { type: "zeroapi-status" }, (r) => {
                if (chrome.runtime.lastError) res({ busy: false });
                else res(r || { busy: false });
              });
            });
            if (!s.busy) { targetTab = t; break; }
          }
        }

        log(`Routing chat ${id} to tab ${targetTab.id} ${targetTab.url}`);

        chrome.tabs.sendMessage(targetTab.id, {
          type: "zeroapi-chat-request",
          id: id,
          model: msg.model,
          provider: msg.provider,
          messages: msg.messages,
          prompt: msg.prompt,
          stream: !!msg.stream,
          temperature: msg.temperature,
          max_tokens: msg.max_tokens
        }, (resp) => {
          if (chrome.runtime.lastError) {
            log("Failed to send to tab", chrome.runtime.lastError.message);
            sendAPIError(id, "Failed to communicate with browser tab: " + chrome.runtime.lastError.message);
          }
        });

      } catch (e) {
        log("Error routing chat request", e);
        sendAPIError(id, String(e));
      }
    });
  }
}

function sendAPIResponse(id, content, done = true) {
  if (!apiConnected || !apiWs || apiWs.readyState !== WebSocket.OPEN) return;
  const msg = {
    type: done ? "chat_response" : "chat_chunk",
    id: id,
    content: content,
    delta: content,
    done: done
  };
  try { apiWs.send(JSON.stringify(msg)); } catch (e) { log("sendAPIResponse failed", e); }
}

function sendAPIChunk(id, delta, fullContent) {
  if (!apiConnected || !apiWs || apiWs.readyState !== WebSocket.OPEN) return;
  const msg = {
    type: "chat_chunk",
    id: id,
    delta: delta,
    content: fullContent || delta,
    done: false
  };
  try { apiWs.send(JSON.stringify(msg)); } catch (e) { log("sendAPIChunk failed", e); }
}

function sendAPIError(id, error) {
  if (!apiConnected || !apiWs || apiWs.readyState !== WebSocket.OPEN) return;
  const msg = {
    type: "chat_error",
    id: id,
    error: String(error),
    done: true
  };
  try { apiWs.send(JSON.stringify(msg)); } catch (e) { log("sendAPIError failed", e); }
}

// ===== STATUS & MESSAGING =====
function statusObj() {
  return {
    type: "zs-status",
    connected: legacyConnected,
    mcpAlive,
    studio: studioConnected,
    studioApp,
    studioProc,
    tools: toolsCache.length,
    servers: serversCache,
    // ZeroAPI specific
    apiConnected: apiConnected,
    apiClientId: apiClientId
  };
}

function broadcastStatus() {
  const status = statusObj();
  chrome.runtime.sendMessage(status).catch(()=>{});
  chrome.tabs.query({ url: PROVIDER_URLS }, (tabs) => {
    for (const t of tabs) chrome.tabs.sendMessage(t.id, status).catch(()=>{});
  });
}

// Messages from content scripts and popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    // Update provider from content script
    if (msg.type === "zeroapi-handler-ready" || msg.type === "zs-provider-info") {
      if (msg.provider) apiProvider = msg.provider;
      // Re-register with API server if connected
      if (apiConnected && apiWs && apiWs.readyState === WebSocket.OPEN) {
        try {
          apiWs.send(JSON.stringify({
            type: "register",
            client_id: apiClientId,
            provider: msg.provider || apiProvider,
            url: msg.url || sender.tab?.url || "",
            version: chrome.runtime.getManifest().version
          }));
        } catch {}
      }
      sendResponse({ ok: true });
      return;
    }

    // API chat chunks from content -> forward to ZeroAPI server
    if (msg.type === "zeroapi-chat-chunk") {
      // msg contains id, content, delta
      if (apiConnected && apiWs && apiWs.readyState === WebSocket.OPEN) {
        try {
          apiWs.send(JSON.stringify({
            type: "chat_chunk",
            id: msg.id,
            delta: msg.content || msg.delta || "",
            content: msg.content || msg.delta || "",
            done: false
          }));
        } catch (e) { log("forward chunk failed", e); }
      }
      sendResponse({ ok: true });
      return;
    }

    if (msg.type === "zeroapi-chat-response") {
      if (apiConnected && apiWs && apiWs.readyState === WebSocket.OPEN) {
        try {
          apiWs.send(JSON.stringify({
            type: "chat_response",
            id: msg.id,
            content: msg.content || "",
            done: true
          }));
        } catch (e) { log("forward response failed", e); }
      }
      sendResponse({ ok: true });
      return;
    }

    if (msg.type === "zeroapi-chat-error") {
      if (apiConnected && apiWs && apiWs.readyState === WebSocket.OPEN) {
        try {
          apiWs.send(JSON.stringify({
            type: "chat_error",
            id: msg.id,
            error: msg.error || "Unknown error",
            done: true
          }));
        } catch (e) { log("forward error failed", e); }
      }
      sendResponse({ ok: true });
      return;
    }

    // Legacy ZeroScript messages
    switch (msg.type) {
      case "status":
        if (!legacyConnected) connectLegacy();
        if (!apiConnected) connectAPI();
        sendResponse(statusObj());
        break;
      case "list_tools": {
        const r = await sendLegacy({ type: "list_tools" }, 10000);
        if (r.ok) sendResponse({ ok: true, tools: r.tools });
        else sendResponse({ ok: toolsCache.length > 0, tools: toolsCache, error: r.error });
        break;
      }
      case "call_tool": {
        const timeout = (msg.timeout || 120000) + 10000;
        const r = await sendLegacy({ type: "call_tool", name: msg.name, arguments: msg.arguments, timeout: msg.timeout }, timeout);
        sendResponse(r);
        break;
      }
      case "restart_mcp": {
        const r = await sendLegacy({ type: "restart_mcp" }, 30000);
        sendResponse(r);
        break;
      }
      case "add_server": {
        const r = await sendLegacy({ type: "add_server", server_id: msg.server_id, command: msg.command, args: msg.args, env: msg.env }, 15000);
        sendResponse(r);
        break;
      }
      case "remove_server": {
        const r = await sendLegacy({ type: "remove_server", server_id: msg.server_id }, 15000);
        sendResponse(r);
        break;
      }
      case "reconnect":
        legacyReconnectDelay = RECONNECT_MIN;
        apiReconnectDelay = RECONNECT_MIN;
        connectLegacy();
        connectAPI();
        sendResponse({ ok: true });
        break;
      default:
        sendResponse({ ok: false, error: "unknown message" });
    }
  })();
  return true;
});

chrome.runtime.onStartup.addListener(() => { connectLegacy(); connectAPI(); });
chrome.runtime.onInstalled.addListener(() => { connectLegacy(); connectAPI(); });

connectLegacy();
connectAPI();

log(`ZeroAPI background v${chrome.runtime.getManifest().version} started, clientId=${apiClientId}`);
