// ZeroAPI Background v2.6 - Auto tab switching when different models required
// Features: auto-switch between tabs when model provider changes, auto-focus, provider detection

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

const PROVIDER_DOMAINS = {
  deepseek: "https://chat.deepseek.com",
  chatgpt: "https://chatgpt.com",
  gemini: "https://gemini.google.com",
  kimi: "https://kimi.com",
  glm: "https://chat.z.ai",
  qwen: "https://chat.qwen.ai",
  meta: "https://www.meta.ai",
  arena: "https://arena.ai"
};

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
let zaSettings = { autoSwitch: true, autoFocus: true, autoOpen: false, notifySwitch: true };

function log(...a) { console.log("[zeroapi-bg]", ...a); }

chrome.storage.local.get(["zaActiveTab", "zaSettings"], (r) => {
  if (r.zaActiveTab) activeTabInfo = r.zaActiveTab;
  if (r.zaSettings) zaSettings = { ...zaSettings, ...r.zaSettings };
  log("Loaded settings", zaSettings, "active", activeTabInfo);
});

function detectProviderFromUrl(url) {
  const u = (url || "").toLowerCase();
  if (u.includes("deepseek")) return "deepseek";
  if (u.includes("chatgpt") || u.includes("openai")) return "chatgpt";
  if (u.includes("gemini")) return "gemini";
  if (u.includes("kimi")) return "kimi";
  if (u.includes("z.ai")) return "glm";
  if (u.includes("qwen")) return "qwen";
  if (u.includes("meta.ai")) return "meta";
  if (u.includes("arena.ai")) return "arena";
  return "auto";
}

function getProviderDisplayName(provider) {
  const map = { deepseek: "DeepSeek", chatgpt: "ChatGPT", gemini: "Gemini", kimi: "Kimi", glm: "GLM", qwen: "Qwen", meta: "Meta AI", arena: "Arena", auto: "Auto" };
  return map[provider] || provider;
}

function getAvailableProviders(tabs) {
  const providers = new Set();
  for (const tab of tabs) {
    const p = detectProviderFromUrl(tab.url);
    if (p !== "auto") providers.add(p);
  }
  return Array.from(providers);
}

function providerMatchesUrl(provider, url) {
  const u = (url || "").toLowerCase();
  const p = (provider || "").toLowerCase();
  if (p === "auto") return true;
  if (p === "deepseek") return u.includes("deepseek");
  if (p === "chatgpt") return u.includes("chatgpt") || u.includes("openai");
  if (p === "gemini") return u.includes("gemini");
  if (p === "kimi") return u.includes("kimi");
  if (p === "glm") return u.includes("z.ai");
  if (p === "qwen") return u.includes("qwen");
  if (p === "meta") return u.includes("meta.ai");
  if (p === "arena") return u.includes("arena.ai");
  return u.includes(p);
}

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

  apiWs.onopen = async () => {
    apiConnected = true;
    apiReconnectDelay = RECONNECT_MIN;
    apiLastMessageAt = Date.now();
    log("connected to ZeroAPI server", API_URL, "clientId", apiClientId);
    startAPIHeartbeat();
    
    // Get available providers from tabs for registration
    chrome.tabs.query({ url: PROVIDER_URLS }, (tabs) => {
      const providers = getAvailableProviders(tabs || []);
      const hello = {
        type: "register",
        client_id: apiClientId,
        provider: providers.length === 1 ? providers[0] : "auto",
        providers: providers,
        url: "extension-background",
        version: chrome.runtime.getManifest().version,
        capabilities: ["chat", "stream", "auto-switch"],
        settings: zaSettings,
        activeTab: activeTabInfo
      };
      try { apiWs.send(JSON.stringify(hello)); } catch {}
      log("Sent hello with providers", providers);
    });
    
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
      // Update available providers in heartbeat
      chrome.tabs.query({ url: PROVIDER_URLS }, (tabs) => {
        const providers = getAvailableProviders(tabs || []);
        try { 
          apiWs.send(JSON.stringify({ 
            type: "ping", 
            client_id: apiClientId,
            providers: providers,
            activeTab: activeTabInfo
          })); 
        } catch {}
      });
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
    log(`chat_request ${id} provider=${msg.provider} model=${msg.model} stream=${msg.stream} autoSwitch=${zaSettings.autoSwitch}`);
    const targetProvider = (msg.provider || "auto").toLowerCase();
    
    chrome.tabs.query({ url: PROVIDER_URLS }, async (tabs) => {
      if (!tabs || !tabs.length) {
        sendAPIError(id, `No chat tabs open. Open ${PROVIDER_DOMAINS[targetProvider] || "chat.deepseek.com"} and click 'Use this chat for API'`);
        return;
      }

      let targetTab = null;
      let switchReason = null;
      
      // Helper to find tab by provider
      const findTabByProvider = (provider, tabList) => {
        for (const tab of tabList) {
          if (providerMatchesUrl(provider, tab.url)) return tab;
        }
        return null;
      };

      // Check active tab
      let activeTab = null;
      if (activeTabInfo) {
        activeTab = tabs.find(t => t.id === activeTabInfo.tabId);
      }

      if (targetProvider === "auto") {
        // Auto mode: prefer active tab if not busy, else any non-busy
        if (activeTab) {
          targetTab = activeTab;
          switchReason = null; // no switch needed
        }
      } else {
        // Specific provider requested
        const providerTab = findTabByProvider(targetProvider, tabs);
        
        if (providerTab) {
          if (activeTab && activeTab.id === providerTab.id) {
            // Already active, no switch
            targetTab = providerTab;
          } else {
            // Different provider required - auto-switch!
            if (zaSettings.autoSwitch) {
              targetTab = providerTab;
              switchReason = `Auto-switch: ${getProviderDisplayName(activeTabInfo?.provider || "unknown")} → ${getProviderDisplayName(targetProvider)} for model ${msg.model}`;
              log(switchReason);
            } else {
              // autoSwitch disabled, but still route to correct provider if available
              targetTab = providerTab;
              switchReason = `Routing to ${getProviderDisplayName(targetProvider)} (autoSwitch disabled but provider tab exists)`;
            }
          }
        } else {
          // No tab for requested provider
          if (activeTab && zaSettings.autoSwitch === false) {
            // If autoSwitch disabled, use active tab anyway
            targetTab = activeTab;
            log(`No tab for ${targetProvider}, using active tab ${activeTab.id} (autoSwitch disabled)`);
          } else {
            // Try to inform user to open provider tab
            const domain = PROVIDER_DOMAINS[targetProvider] || `https://${targetProvider}.com`;
            sendAPIError(id, `No tab open for provider '${targetProvider}' (model ${msg.model}). Open ${domain} in browser with ZeroAPI extension and click 'Use this chat'. Available: ${getAvailableProviders(tabs).join(", ") || "none"}. Active: ${activeTabInfo?.provider || "none"}`);
            return;
          }
        }
      }
      
      // Fallback to first tab if still no target
      if (!targetTab) targetTab = tabs[0];

      // Check if target tab is busy, try to find alternative for same provider
      try {
        const status = await new Promise((resolve) => {
          chrome.tabs.sendMessage(targetTab.id, { type: "zeroapi-status" }, (resp) => {
            if (chrome.runtime.lastError) resolve({ busy: false });
            else resolve(resp || { busy: false });
          });
        });

        if (status && status.busy) {
          log(`Target tab ${targetTab.id} busy, searching alternative for ${targetProvider}`);
          const otherTabs = tabs.filter(t => t.id !== targetTab.id && (targetProvider === "auto" || providerMatchesUrl(targetProvider, t.url)));
          for (const t of otherTabs) {
            const s = await new Promise((res) => {
              chrome.tabs.sendMessage(t.id, { type: "zeroapi-status" }, (r) => {
                if (chrome.runtime.lastError) res({ busy: false });
                else res(r || { busy: false });
              });
            });
            if (!s.busy) { 
              targetTab = t; 
              switchReason = `Original tab busy, switched to alternative ${getProviderDisplayName(detectProviderFromUrl(t.url))} tab`;
              break; 
            }
          }
        }
      } catch (e) {
        log("Status check failed", e);
      }

      // Auto-switch active tab info if needed
      if (targetTab && ( !activeTabInfo || activeTabInfo.tabId !== targetTab.id ) && zaSettings.autoSwitch) {
        const newProvider = detectProviderFromUrl(targetTab.url);
        const oldProvider = activeTabInfo?.provider || "none";
        
        activeTabInfo = {
          tabId: targetTab.id,
          provider: newProvider,
          url: targetTab.url,
          timestamp: Date.now(),
          autoSwitched: true,
          previousProvider: oldProvider
        };
        
        try { 
          chrome.storage.local.set({ zaActiveTab: activeTabInfo, zaActiveProvider: newProvider }); 
        } catch {}
        
        // Broadcast to all tabs that active changed
        chrome.tabs.query({ url: PROVIDER_URLS }, (allTabs) => {
          if (!allTabs) return;
          for (const t of allTabs) {
            const isActive = t.id === targetTab.id;
            try { 
              chrome.tabs.sendMessage(t.id, { 
                type: "za-active-update", 
                active: isActive, 
                provider: newProvider,
                autoSwitched: true,
                reason: switchReason
              }); 
            } catch {}
          }
        });
        
        broadcastStatus();
        
        // Auto-focus the new tab if enabled
        if (zaSettings.autoFocus) {
          try {
            chrome.tabs.update(targetTab.id, { active: true }, () => {
              if (chrome.runtime.lastError) {
                log("Failed to focus tab", chrome.runtime.lastError.message);
              } else {
                log(`Focused tab ${targetTab.id} for provider ${newProvider}`);
                // Also focus window
                chrome.windows.update(targetTab.windowId, { focused: true }, () => {});
              }
            });
          } catch (e) {
            log("Auto-focus failed", e);
          }
        }
        
        if (zaSettings.notifySwitch && switchReason) {
          // Notify via badge or toast in target tab (will be handled by content script)
          try {
            chrome.tabs.sendMessage(targetTab.id, {
              type: "za-auto-switch-notify",
              from: oldProvider,
              to: newProvider,
              reason: switchReason,
              model: msg.model
            });
          } catch {}
        }
        
        log(`Auto-switched active tab: ${oldProvider} -> ${newProvider} (tab ${targetTab.id}) reason: ${switchReason}`);
      }

      log(`Routing chat ${id} -> tab ${targetTab.id} ${targetTab.url} provider=${detectProviderFromUrl(targetTab.url)}${switchReason ? ' ['+switchReason+']' : ''}`);

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
        images: msg.images || msg.files || [],
        autoSwitched: !!switchReason,
        switchReason: switchReason
      }, (resp) => {
        if (chrome.runtime.lastError) {
          log("Failed to send to tab", chrome.runtime.lastError.message);
          sendAPIError(id, "Failed to communicate with browser tab: " + chrome.runtime.lastError.message);
        }
      });

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
    settings: zaSettings,
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
      const provider = msg.provider || detectProviderFromUrl(msg.url || sender.tab?.url || "");
      activeTabInfo = {
        tabId: tabId,
        provider: provider,
        url: msg.url || sender.tab?.url || "",
        timestamp: Date.now(),
        manual: true
      };
      try { chrome.storage.local.set({ zaActiveTab: activeTabInfo, zaActiveProvider: provider }); } catch {}
      log("Active tab set manually", activeTabInfo);
      chrome.tabs.query({ url: PROVIDER_URLS }, (tabs) => {
        if (!tabs) return;
        for (const t of tabs) {
          const isActive = t.id === tabId;
          try { chrome.tabs.sendMessage(t.id, { type: "za-active-update", active: isActive, provider: provider }); } catch {}
        }
      });
      broadcastStatus();
      sendResponse({ ok: true, activeTab: activeTabInfo });
      return;
    }

    if (msg.type === "za-set-settings") {
      zaSettings = { ...zaSettings, ...msg.settings };
      try { chrome.storage.local.set({ zaSettings: zaSettings }); } catch {}
      log("Settings updated", zaSettings);
      broadcastStatus();
      sendResponse({ ok: true, settings: zaSettings });
      return;
    }

    if (msg.type === "za-get-settings") {
      sendResponse({ ok: true, settings: zaSettings, activeTab: activeTabInfo });
      return;
    }

    if (msg.type === "zeroapi-handler-ready" || msg.type === "zs-provider-info") {
      // Update available providers when a handler becomes ready
      chrome.tabs.query({ url: PROVIDER_URLS }, (tabs) => {
        const providers = getAvailableProviders(tabs || []);
        if (apiConnected && apiWs && apiWs.readyState === WebSocket.OPEN) {
          try {
            apiWs.send(JSON.stringify({
              type: "providers_update",
              client_id: apiClientId,
              providers: providers,
              activeTab: activeTabInfo
            }));
          } catch {}
        }
      });
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
      // Include available providers in status
      chrome.tabs.query({ url: PROVIDER_URLS }, (tabs) => {
        const providers = getAvailableProviders(tabs || []);
        const status = { ...statusObj(), availableProviders: providers, tabsCount: (tabs || []).length };
        sendResponse(status);
      });
      return true; // async response
    }

    if (msg.type === "reconnect" || msg.type === "za-reconnect") {
      apiReconnectDelay = RECONNECT_MIN;
      connectAPI();
      sendResponse({ ok: true });
      return;
    }

    if (msg.type === "za-get-active") {
      chrome.tabs.query({ url: PROVIDER_URLS }, (tabs) => {
        const providers = getAvailableProviders(tabs || []);
        sendResponse({ ok: true, activeTab: activeTabInfo, availableProviders: providers, settings: zaSettings });
      });
      return true;
    }

    sendResponse({ ok: false, error: "unknown message" });
  })();
  return true;
});

chrome.runtime.onStartup.addListener(() => { connectAPI(); });
chrome.runtime.onInstalled.addListener(() => { connectAPI(); });

connectAPI();

log(`ZeroAPI background v${chrome.runtime.getManifest().version} started with auto-switch (autoSwitch=${zaSettings.autoSwitch} autoFocus=${zaSettings.autoFocus}), clientId=${apiClientId}`);
