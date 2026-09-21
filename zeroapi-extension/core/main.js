// ZeroAPI - API Bar (replaces ZeroScript's main.js)
// Minimal UI for OpenAI-compatible API mode
// Compatible with ZeroScript extension running alongside (uses za- prefix, not zs-)
(() => {
  "use strict";
  const log = (...a) => console.log("[zeroapi]", ...a);
  const EXT_VERSION = chrome.runtime.getManifest().version;

  // State
  let apiConnected = false;
  let isBusy = false;
  let currentModel = "";
  let isActiveTab = false;
  let providerId = "unknown";
  let providerName = "Unknown";

  // Detect provider from ZSProvider if available, otherwise from URL
  function detectProvider() {
    try {
      if (typeof ZSProvider !== 'undefined' && ZSProvider.id) {
        providerId = ZSProvider.id;
        providerName = ZSProvider.displayName || ZSProvider.id;
        return;
      }
    } catch {}
    const host = location.hostname;
    if (host.includes("deepseek")) { providerId = "deepseek"; providerName = "DeepSeek"; }
    else if (host.includes("chatgpt") || host.includes("openai")) { providerId = "chatgpt"; providerName = "ChatGPT"; }
    else if (host.includes("gemini")) { providerId = "gemini"; providerName = "Gemini"; }
    else if (host.includes("kimi")) { providerId = "kimi"; providerName = "Kimi"; }
    else if (host.includes("z.ai")) { providerId = "glm"; providerName = "GLM"; }
    else if (host.includes("qwen")) { providerId = "qwen"; providerName = "Qwen"; }
    else if (host.includes("arena")) { providerId = "arena"; providerName = "Arena"; }
    else if (host.includes("meta")) { providerId = "meta"; providerName = "Meta AI"; }
  }

  // Storage key for active tab preference
  const ACTIVE_KEY = "zaActiveTab";

  async function checkActive() {
    try {
      const data = await new Promise(res => chrome.storage.local.get([ACTIVE_KEY, "zaActiveProvider"], res));
      const activeTab = data[ACTIVE_KEY];
      if (activeTab && activeTab.provider === providerId) {
        const age = Date.now() - (activeTab.timestamp || 0);
        if (age < 5 * 60 * 1000 && location.href.includes(activeTab.urlPart || "")) {
          isActiveTab = true;
        } else if (!activeTab.urlPart) {
          isActiveTab = true;
        }
      }
      if (!activeTab) isActiveTab = true;
    } catch {}
  }

  function setActive() {
    isActiveTab = true;
    try {
      chrome.storage.local.set({
        [ACTIVE_KEY]: {
          provider: providerId,
          url: location.href,
          urlPart: location.hostname,
          timestamp: Date.now()
        },
        zaActiveProvider: providerId
      });
      chrome.runtime.sendMessage({
        type: "za-set-active",
        provider: providerId,
        url: location.href
      });
    } catch {}
    renderBar();
    toast(`✓ ${providerName} set as active for API`);
  }

  // UI Construction
  let root, bar, dot, brandEl, stateEl, actionBtn, badgeEl, dashBtn;

  function build() {
    if (document.getElementById("za-root")) return;

    root = document.createElement("div");
    root.id = "za-root";
    root.innerHTML = `
      <div id="za-bar">
        <span id="za-dot" class="off" title="API status"></span>
        <span id="za-brand">ZeroAPI <span class="za-ver">v${EXT_VERSION}</span> <span class="za-prov">${providerName}</span></span>
        <span id="za-state">Initializing...</span>
        <span id="za-badge" class="za-api-badge off">API: offline</span>
        <button id="za-action" class="za-btn-primary">📌 Use this chat for API</button>
        <a id="za-dash" href="http://localhost:8000/" target="_blank" title="Open dashboard">📊 Dashboard</a>
        <button id="za-menu-btn" class="za-btn-ghost" title="More">⋯</button>
      </div>
      <div id="za-menu" hidden>
        <div class="za-menu-head"><span>ZeroAPI</span><span class="za-menu-ver">v${EXT_VERSION}</span></div>
        <div class="za-menu-sec">
          <div class="za-sec-label">Status</div>
          <div id="za-menu-status" class="za-menu-note">Checking...</div>
        </div>
        <div class="za-menu-sec">
          <div class="za-sec-label">How it works</div>
          <div class="za-menu-note">
            1. Run server: <code>python run_server.py</code><br>
            2. Click "Use this chat for API" on this tab<br>
            3. Use OpenAI SDK with <code>base_url=http://localhost:8000/v1</code>
          </div>
        </div>
        <div class="za-menu-sec">
          <div class="za-sec-label">Models for this tab</div>
          <div id="za-menu-models" class="za-menu-note"></div>
        </div>
        <div class="za-menu-sec">
          <div class="za-sec-label">Links</div>
          <button class="za-menu-opt" data-url="http://localhost:8000/">📊 Dashboard</button>
          <button class="za-menu-opt" data-url="http://localhost:8000/docs">📚 API Docs</button>
          <button class="za-menu-opt" data-url="http://localhost:8000/v1/models">🤖 Models JSON</button>
        </div>
      </div>
    `;
    document.documentElement.appendChild(root);
    bar = root.querySelector("#za-bar");
    dot = root.querySelector("#za-dot");
    brandEl = root.querySelector("#za-brand");
    stateEl = root.querySelector("#za-state");
    actionBtn = root.querySelector("#za-action");
    badgeEl = root.querySelector("#za-badge");
    dashBtn = root.querySelector("#za-dash");
    const menuEl = root.querySelector("#za-menu");
    const menuBtn = root.querySelector("#za-menu-btn");

    actionBtn.addEventListener("click", () => {
      if (isActiveTab) {
        toast("This chat is already active for API");
      } else {
        setActive();
      }
    });

    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      menuEl.hidden = !menuEl.hidden;
      if (!menuEl.hidden) updateMenu();
    });

    document.addEventListener("click", (e) => {
      if (menuEl.hidden) return;
      if (!menuEl.contains(e.target) && !menuBtn.contains(e.target)) menuEl.hidden = true;
    }, true);

    menuEl.querySelectorAll(".za-menu-opt").forEach(btn => {
      btn.addEventListener("click", () => {
        try { window.open(btn.dataset.url, "_blank"); } catch {}
        menuEl.hidden = true;
      });
    });

    renderBar();
    placeBar();
    log(`API bar ready provider=${providerId} v${EXT_VERSION}`);
  }

  function updateMenu() {
    const menuStatus = document.getElementById("za-menu-status");
    const menuModels = document.getElementById("za-menu-models");
    if (menuStatus) {
      menuStatus.innerHTML = `
        API Server: ${apiConnected ? '<span style="color:#34d399">● Connected</span>' : '<span style="color:#fbbf24">○ Offline</span>'}<br>
        Provider: ${providerName} (${providerId})<br>
        Active for API: ${isActiveTab ? '✅ Yes' : '○ No'}<br>
        Busy: ${isBusy ? '⏳ Processing request' : 'Idle'}
      `;
    }
    if (menuModels) {
      const modelMap = {
        deepseek: ["deepseek-chat", "deepseek-reasoner"],
        chatgpt: ["gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"],
        gemini: ["gemini-2.0-flash", "gemini-1.5-pro"],
        kimi: ["kimi-k2", "kimi"],
        glm: ["glm-4", "glm"],
        qwen: ["qwen-turbo", "qwen"],
        meta: ["llama-3", "meta"],
        arena: ["arena"]
      };
      const models = modelMap[providerId] || ["auto"];
      menuModels.innerHTML = models.map(m => `<code>${m}</code>`).join(" ") + `<br><small>Use <code>auto</code> for any tab</small>`;
    }
  }

  function renderBar() {
    if (!bar) return;

    if (isBusy) {
      dot.className = "api busy";
      dot.title = `ZeroAPI: processing ${currentModel || ""}`;
    } else if (apiConnected) {
      dot.className = isActiveTab ? "api on" : "api";
      dot.title = `ZeroAPI: connected (${providerName})${isActiveTab ? " - ACTIVE for API" : " - click 'Use this chat'"}`;
    } else {
      dot.className = "off";
      dot.title = "ZeroAPI: API server offline - run python run_server.py";
    }

    if (isBusy) {
      badgeEl.className = "za-api-badge busy";
      badgeEl.textContent = `⏳ ${currentModel || "busy"}`;
    } else if (apiConnected) {
      badgeEl.className = isActiveTab ? "za-api-badge ok" : "za-api-badge";
      badgeEl.textContent = isActiveTab ? "● Active for API" : "API: ready";
    } else {
      badgeEl.className = "za-api-badge off";
      badgeEl.textContent = "API: offline";
    }

    if (isBusy) {
      stateEl.textContent = `Processing ${currentModel}...`;
    } else if (apiConnected) {
      stateEl.textContent = isActiveTab ? `✓ Active for API (${providerName})` : `Ready - click to use ${providerName} for API`;
    } else {
      stateEl.textContent = "API server offline - run python run_server.py";
    }

    if (isActiveTab) {
      actionBtn.textContent = "✓ Active for API";
      actionBtn.classList.add("active");
      actionBtn.disabled = false;
    } else {
      actionBtn.textContent = "📌 Use this chat for API";
      actionBtn.classList.remove("active");
      actionBtn.disabled = false;
    }

    const provEl = brandEl.querySelector(".za-prov");
    if (provEl) provEl.textContent = providerName;
  }

  function placeBar() {
    requestAnimationFrame(placeBar);
    if (!bar) return;
    if (!bar.isConnected) {
      try { document.documentElement.appendChild(root); } catch {}
    }

    const zsBar = document.getElementById("zs-bar");
    let topOffset = 0;
    if (zsBar && zsBar.offsetHeight && zsBar.style.display !== "none") {
      const rect = zsBar.getBoundingClientRect();
      if (rect.top < 50) {
        topOffset = rect.height + 4;
      }
    }

    let mountParent = null;
    let mountBefore = null;
    try {
      if (typeof ZSProvider !== 'undefined' && ZSProvider.barMount) {
        const m = ZSProvider.barMount();
        if (m && m.parent && m.parent.isConnected) {
          mountParent = m.parent;
          mountBefore = m.before || null;
        }
      }
    } catch {}

    if (mountParent) {
      if (bar.parentElement !== mountParent || bar.nextElementSibling !== mountBefore) {
        try { mountParent.insertBefore(bar, mountBefore); } catch {}
      }
      bar.classList.add("za-bar-inline");
      bar.style.position = "";
      bar.style.top = "";
      bar.style.left = "";
      bar.style.width = "";
      bar.style.display = "flex";
      return;
    }

    bar.classList.remove("za-bar-inline");
    if (root && bar.parentElement !== root) root.appendChild(bar);
    bar.style.display = "flex";
    bar.style.position = "fixed";
    bar.style.top = topOffset + "px";
    bar.style.left = "0";
    bar.style.width = "100%";
    bar.style.zIndex = "2147483645";
    if (zsBar) {
      bar.style.zIndex = "2147483645";
      bar.style.top = topOffset + "px";
    }
  }

  function toast(msg) {
    let t = document.getElementById("za-toast");
    if (!t) {
      t = document.createElement("div");
      t.id = "za-toast";
      t.className = "za-toast";
      document.documentElement.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 3000);
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg) return;
    if (msg.type === "zs-status" || msg.type === "za-status") {
      if (typeof msg.apiConnected === "boolean") apiConnected = msg.apiConnected;
      if (msg.provider) {
        providerId = msg.provider;
        providerName = msg.provider;
      }
      renderBar();
    }
    if (msg.type === "zeroapi-status") {
      if (typeof msg.busy === "boolean") isBusy = msg.busy;
      if (msg.model) currentModel = msg.model;
      renderBar();
    }
    if (msg.type === "za-active-update") {
      isActiveTab = !!msg.active;
      renderBar();
    }
  });

  async function pollStatus() {
    try {
      chrome.runtime.sendMessage({ type: "status" }, (s) => {
        if (chrome.runtime.lastError) return;
        if (!s) return;
        if (typeof s.apiConnected === "boolean") apiConnected = s.apiConnected;
        renderBar();
      });
    } catch {}
  }

  window.addEventListener("za-busy", (e) => {
    isBusy = !!e.detail?.busy;
    currentModel = e.detail?.model || "";
    renderBar();
  });

  detectProvider();
  checkActive().then(() => {
    build();
    setInterval(pollStatus, 3000);
    setTimeout(pollStatus, 1000);
    setInterval(renderBar, 1000);
  });

  window.__zaBar = {
    setBusy: (busy, model) => {
      isBusy = busy;
      currentModel = model || "";
      renderBar();
      window.dispatchEvent(new CustomEvent("za-busy", { detail: { busy, model } }));
    },
    setConnected: (connected) => {
      apiConnected = connected;
      renderBar();
    },
    setActive: (active) => {
      isActiveTab = active;
      renderBar();
    }
  };

  log("ZeroAPI bar init", providerId);
})();
