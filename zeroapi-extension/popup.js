// ZeroAPI Popup v2.6 - with auto-switch settings
const SUPPORTED_HOSTS = [
  "chat.deepseek.com", "deepseek.com", "chatgpt.com", "chat.openai.com",
  "gemini.google.com", "www.kimi.ai", "kimi.ai",
  "chat.z.ai", "chat.qwen.ai", "arena.ai", "www.meta.ai", "meta.ai",
];
const DASHBOARD_URL = "http://localhost:8000/";
const DOCS_URL = "http://localhost:8000/docs";

document.getElementById("ver").textContent = `v${chrome.runtime.getManifest().version}`;

let currentStatus = null;
let availableTabs = [];
let currentSettings = { autoSwitch: true, autoFocus: true, notifySwitch: true };

function detectProviderFromUrl(url) {
  url = (url || "").toLowerCase();
  if (url.includes("deepseek")) return { id: "deepseek", name: "DeepSeek", models: ["deepseek-chat", "deepseek-reasoner"] };
  if (url.includes("chatgpt") || url.includes("openai")) return { id: "chatgpt", name: "ChatGPT", models: ["gpt-4o", "gpt-4o-mini", "gpt-4"] };
  if (url.includes("gemini")) return { id: "gemini", name: "Gemini", models: ["gemini-2.0-flash", "gemini-1.5-pro"] };
  if (url.includes("kimi")) return { id: "kimi", name: "Kimi", models: ["kimi-k2"] };
  if (url.includes("z.ai")) return { id: "glm", name: "GLM", models: ["glm-4"] };
  if (url.includes("qwen")) return { id: "qwen", name: "Qwen", models: ["qwen-turbo"] };
  if (url.includes("meta.ai")) return { id: "meta", name: "Meta AI", models: ["llama-3"] };
  if (url.includes("arena.ai")) return { id: "arena", name: "Arena", models: ["arena"] };
  return { id: "unknown", name: "Unknown", models: ["auto"] };
}

function renderStatus(s) {
  currentStatus = s;
  if (s.settings) currentSettings = { ...currentSettings, ...s.settings };
  if (s.availableProviders) {
    const infoEl = document.getElementById("switch-info");
    if (infoEl) {
      if (s.availableProviders.length) {
        infoEl.innerHTML = `Available: <code>${s.availableProviders.join("</code> <code>")}</code> — auto-switch will use matching tab. Tabs: ${s.tabsCount || 0}`;
      } else {
        infoEl.textContent = "No chat tabs open. Open tabs for each provider you want to use.";
      }
    }
  }

  const dot = document.getElementById("dot");
  const apiState = document.getElementById("api-state");
  const activeTabEl = document.getElementById("active-tab");

  if (s.apiConnected) {
    dot.className = "dot api on";
    const switchStatus = currentSettings.autoSwitch ? "🔄 auto-switch ON" : "⏸️ auto-switch OFF";
    apiState.innerHTML = `API Server: Connected <span class="badge ok">online</span> <span style="opacity:0.6">:${8000}</span> <span class="badge ok">${switchStatus}</span>`;
  } else {
    dot.className = "dot off";
    apiState.innerHTML = `❌ <b>API Server</b>: Offline <span class="badge warn">run server</span><br><small style="opacity:0.6">Run: <code>python run_server.py</code> or <code>start_api.bat</code></small>`;
  }

  if (activeTabEl) {
    const active = s.activeTab || s.zaActive;
    if (active) {
      const prov = detectProviderFromUrl(active.url || "");
      const autoSwitched = active.autoSwitched ? " <span class='badge ok'>↔️ auto-switched</span>" : "";
      const prev = active.previousProvider ? `<br><small style="opacity:0.6">from ${active.previousProvider} → ${active.provider}</small>` : "";
      activeTabEl.innerHTML = `Active chat: <b>${prov.name}</b> <span class="badge ok">${active.provider || prov.id}</span>${autoSwitched}${prev}<br><small style="opacity:0.6">${(active.url || "").slice(0,50)}</small>`;
    } else {
      activeTabEl.textContent = "Active chat: none — click 'Use this chat for API' on a chat tab";
    }
  }

  const compatEl = document.getElementById("zs-detect");
  if (compatEl) {
    if (chrome.management && chrome.management.getAll) {
      chrome.management.getAll(exts => {
        const hasZS = exts.some(e => e.name && e.name.toLowerCase().includes("zeroscript"));
        compatEl.textContent = hasZS ? "ZeroScript detected — compatible (bars stack)" : "ZeroScript not installed — ZeroAPI works standalone";
      });
    } else {
      compatEl.textContent = "ZeroAPI uses za- prefix, ZeroScript uses zs- — compatible";
    }
  }

  // Update toggles
  const sw = document.getElementById("toggle-auto-switch");
  const foc = document.getElementById("toggle-auto-focus");
  const not = document.getElementById("toggle-notify");
  if (sw) sw.checked = !!currentSettings.autoSwitch;
  if (foc) foc.checked = !!currentSettings.autoFocus;
  if (not) not.checked = currentSettings.notifySwitch !== false;

  renderTabs();
}

async function refreshTabs() {
  chrome.tabs.query({ url: SUPPORTED_HOSTS.map(h => `*://${h}/*`) }, (tabs) => {
    availableTabs = tabs || [];
    renderTabs();
  });
}

function renderTabs() {
  const list = document.getElementById("tabs-list");
  if (!list) return;

  if (!availableTabs.length) {
    list.innerHTML = `<div class="row small">No chat tabs open.<br>Open <code>chat.deepseek.com</code> or <code>chatgpt.com</code></div>`;
    return;
  }

  const activeTabId = currentStatus?.activeTab?.tabId;
  
  list.innerHTML = availableTabs.map(tab => {
    const prov = detectProviderFromUrl(tab.url);
    const isActive = tab.id === activeTabId;
    return `<div class="tab-item ${isActive ? 'active' : ''}" data-tab="${tab.id}">
      <span class="prov">${prov.name}</span>
      <span class="url">${tab.url ? new URL(tab.url).hostname : "unknown"}${isActive ? " ✓ active" : ""}</span>
    </div>`;
  }).join("");

  list.querySelectorAll(".tab-item").forEach(el => {
    el.addEventListener("click", () => {
      const tabId = parseInt(el.dataset.tab);
      const tab = availableTabs.find(t => t.id === tabId);
      if (!tab) return;
      const prov = detectProviderFromUrl(tab.url);
      chrome.runtime.sendMessage({ type: "za-set-active", tabId: tabId, provider: prov.id, url: tab.url }, () => {
        chrome.tabs.update(tabId, { active: true });
        setTimeout(() => { refreshStatus(); refreshTabs(); }, 500);
      });
    });
  });
}

function refreshStatus() {
  chrome.runtime.sendMessage({ type: "status" }, (s) => {
    if (chrome.runtime.lastError) return;
    if (s) renderStatus(s);
  });
}

function saveSettings() {
  const autoSwitch = document.getElementById("toggle-auto-switch")?.checked;
  const autoFocus = document.getElementById("toggle-auto-focus")?.checked;
  const notifySwitch = document.getElementById("toggle-notify")?.checked;
  const newSettings = { autoSwitch, autoFocus, notifySwitch };
  chrome.runtime.sendMessage({ type: "za-set-settings", settings: newSettings }, (resp) => {
    if (resp && resp.settings) currentSettings = resp.settings;
    refreshStatus();
  });
}

document.getElementById("toggle-auto-switch")?.addEventListener("change", saveSettings);
document.getElementById("toggle-auto-focus")?.addEventListener("change", saveSettings);
document.getElementById("toggle-notify")?.addEventListener("change", saveSettings);

document.getElementById("open-dashboard").addEventListener("click", () => {
  chrome.tabs.create({ url: DASHBOARD_URL });
});

document.getElementById("open-docs").addEventListener("click", () => {
  chrome.tabs.create({ url: DOCS_URL });
});

document.getElementById("reconnect").addEventListener("click", (e) => {
  e.target.textContent = "Reconnecting...";
  chrome.runtime.sendMessage({ type: "reconnect" }, () => {
    setTimeout(() => {
      e.target.textContent = "↻ Reconnect to server";
      refreshStatus();
    }, 800);
  });
});

document.getElementById("use-active").addEventListener("click", () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    if (!tab || !tab.url) {
      alert("Open a chat tab (deepseek, chatgpt, gemini, etc.) first");
      return;
    }
    const isSupported = SUPPORTED_HOSTS.some(h => tab.url.includes(h));
    if (!isSupported) {
      alert("Current tab is not a supported AI chat. Open chat.deepseek.com, chatgpt.com, gemini.google.com, etc.");
      return;
    }
    const prov = detectProviderFromUrl(tab.url);
    chrome.runtime.sendMessage({ type: "za-set-active", tabId: tab.id, provider: prov.id, url: tab.url }, (resp) => {
      if (chrome.runtime.lastError) {
        console.error(chrome.runtime.lastError);
        return;
      }
      const btn = document.getElementById("use-active");
      btn.textContent = `✓ ${prov.name} active for API`;
      btn.classList.add("active");
      setTimeout(() => {
        btn.textContent = "Use this chat for API";
        btn.classList.remove("active");
      }, 2500);
      refreshStatus();
      refreshTabs();
    });
  });
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && (msg.type === "za-status" || msg.type === "zs-status")) {
    renderStatus(msg);
  }
});

refreshStatus();
refreshTabs();
setInterval(refreshStatus, 2500);
setInterval(refreshTabs, 4000);
