// ZeroAPI Background - OpenAI Compatible API Server bridge
// Pure API mode, no Roblox/legacy remnants (except mention in comments)
// Compatible with ZeroScript extension running alongside (different extension ID, separate WS)

const API_PORT = 8000;
const API_URL = `ws://127.0.0.1:${API_PORT}/ws`;

const PROVIDER_URLS = [
  "https://chat.deepseek.com/*",
  "https://deepseek.com/*",
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

let apiWs = null;
let apiConnected = false;
let apiReconnectDelay = RECONNECT_MIN;
let apiReconnectTimer = null;
let apiHeartbeatTimer = null;
let apiLastMessageAt = 0;
let apiClientId = `za-${Math.random().toString(36).slice(2,10)}`;

let activeTabInfo = null;

function log(...a) { console.log("[zeroapi-bg]", ...a); }

chrome.storage.local.get(["zaActiveTab"], (r) => {
  if (r.zaActiveTab) activeTabInfo = r.zaActiveTab;
});

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
    log("connected to ZeroAPI server", API_URL, "clientId", apiClientId);
    startAPIHeartbeat();
    const hello = {
      type: "register",
      client_id: apiClientId,
      provider: "auto",
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

  if (type === "pong" || type === "registered" || type === "heartbeat") return;

  if (type === "chat_request") {
    log(`chat_request ${id} provider=${msg.provider} model=${msg.model} stream=${msg.stream}`);
    const targetProvider = (msg.provider || "auto").toLowerCase();
    
    chrome.tabs.query({ url: PROVIDER_URLS }, async (tabs) => {
      if (!tabs || !tabs.length) {
        sendAPIError(id, "No chat tabs open. Open chat.deepseek.com or chatgpt.com and click 'Use this chat for API'");
        return;
      }

      let targetTab = null;
      
      if (activeTabInfo) {
        const activeTab = tabs.find(t => t.id === activeTabInfo.tabId);
        if (activeTab) {
          if (targetProvider === "auto" || activeTab.url.toLowerCase().includes(targetProvider) || activeTabInfo.provider === targetProvider) {
            targetTab = activeTab;
          }
        } else {
          if (activeTabInfo.provider && targetProvider !== "auto") {
            const byProvider = tabs.find(t => {
              const u = (t.url || "").toLowerCase();
              return u.includes(activeTabInfo.provider) ||
                (activeTabInfo.provider === "deepseek" && u.includes("deepseek")) ||
                (activeTabInfo.provider === "chatgpt" && (u.includes("chatgpt") || u.includes("openai"))) ||
                (activeTabInfo.provider === "gemini" && u.includes("gemini")) ||
                (activeTabInfo.provider === "kimi" && u.includes("kimi")) ||
                (activeTabInfo.provider === "glm" && u.includes("z.ai")) ||
                (activeTabInfo.provider === "qwen" && u.includes("qwen")) ||
                (activeTabInfo.provider === "meta" && u.includes("meta.ai")) ||
                (activeTabInfo.provider === "arena" && u.includes("arena.ai"));
            });
            if (byProvider) targetTab = byProvider;
          }
        }
      }

      if (!targetTab && targetProvider !== "auto") {
        for (const tab of tabs) {
          const url = (tab.url || "").toLowerCase();
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
      
      if (!targetTab) targetTab = tabs[0];

      try {
        const status = await new Promise((resolve) => {
          chrome.tabs.sendMessage(targetTab.id, { type: "zeroapi-status" }, (resp) => {
            if (chrome.runtime.lastError) resolve({ busy: false });
            else resolve(resp || { busy: false });
          });
        });

        if (status && status.busy) {
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

        log(`Routing chat ${id} -> tab ${targetTab.id} ${targetTab.url}`);

        chrome.tabs.sendMessage(targetTab.id, {
          type: "zeroapi-chat-request",
          id: id,
          model: msg.model,
          provider: msg.provider,
          messages: msg.messages,
          prompt: msg.prompt,
          stream: !!msg.stream,
          temperature: msg.temperature,
          max_tokens: msg.max_tokens,
          files: msg.files || msg.images || [],
          images: msg.images || msg.files || []
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

function sendAPIError(id, error) {
  if (!apiConnected || !apiWs || apiWs.readyState !== WebSocket.OPEN) return;
  const msg = { type: "chat_error", id: id, error: String(error), done: true };
  try { apiWs.send(JSON.stringify(msg)); } catch (e) { log("sendAPIError failed", e); }
}

function statusObj() {
  return {
    type: "za-status",
    apiConnected: apiConnected,
    apiClientId: apiClientId,
    activeTab: activeTabInfo,
    connected: false,
    tools: 0,
    servers: [],
    zaActive: activeTabInfo
  };
}

function broadcastStatus() {
  const status = statusObj();
  const legacyStatus = { ...status, type: "zs-status", connected: false, apiConnected: apiConnected };
  try { chrome.runtime.sendMessage(status); } catch {}
  try { chrome.runtime.sendMessage(legacyStatus); } catch {}
  chrome.tabs.query({ url: PROVIDER_URLS }, (tabs) => {
    if (!tabs) return;
    for (const t of tabs) {
      try { chrome.tabs.sendMessage(t.id, status); } catch {}
      try { chrome.tabs.sendMessage(t.id, legacyStatus); } catch {}
    }
  });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg.type === "za-set-active") {
      const tabId = sender.tab ? sender.tab.id : msg.tabId;
      activeTabInfo = {
        tabId: tabId,
        provider: msg.provider || "auto",
        url: msg.url || sender.tab?.url || "",
        timestamp: Date.now()
      };
      try { chrome.storage.local.set({ zaActiveTab: activeTabInfo, zaActiveProvider: msg.provider }); } catch {}
      log("Active tab set", activeTabInfo);
      chrome.tabs.query({ url: PROVIDER_URLS }, (tabs) => {
        if (!tabs) return;
        for (const t of tabs) {
          const isActive = t.id === tabId;
          try { chrome.tabs.sendMessage(t.id, { type: "za-active-update", active: isActive, provider: msg.provider }); } catch {}
        }
      });
      broadcastStatus();
      sendResponse({ ok: true, activeTab: activeTabInfo });
      return;
    }

    if (msg.type === "zeroapi-handler-ready" || msg.type === "zs-provider-info") {
      sendResponse({ ok: true });
      broadcastStatus();
      return;
    }

    if (msg.type === "zeroapi-chat-chunk") {
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

    if (msg.type === "status" || msg.type === "za-status") {
      if (!apiConnected) connectAPI();
      sendResponse(statusObj());
      return;
    }

    if (msg.type === "reconnect" || msg.type === "za-reconnect") {
      apiReconnectDelay = RECONNECT_MIN;
      connectAPI();
      sendResponse({ ok: true });
      return;
    }

    if (msg.type === "za-get-active") {
      sendResponse({ ok: true, activeTab: activeTabInfo });
      return;
    }

    sendResponse({ ok: false, error: "unknown message" });
  })();
  return true;
});

chrome.runtime.onStartup.addListener(() => { connectAPI(); });
chrome.runtime.onInstalled.addListener(() => { connectAPI(); });

connectAPI();

log(`ZeroAPI background v${chrome.runtime.getManifest().version} started, clientId=${apiClientId} (API-only, compatible with ZeroScript)`);
