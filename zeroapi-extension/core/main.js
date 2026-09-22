// ZeroAPI - Minimal API Bar v2.6 with auto-switch support
// Shows only status + API model name, one action button when inactive, auto-switch toast
(() => {
  "use strict";
  const log = (...a) => console.log("[zeroapi]", ...a);
  const VER = chrome.runtime.getManifest().version;

  let apiConnected = false;
  let isBusy = false;
  let currentModel = "";
  let isActiveTab = false;
  let providerId = "unknown";
  let providerName = "Unknown";
  let lastSwitchInfo = null;

  const MODEL_MAP = {
    deepseek: { def: "deepseek" },
    chatgpt:  { def: "chatgpt" },
    gemini:   { def: "gemini" },
    kimi:     { def: "kimi" },
    glm:      { def: "glm" },
    qwen:     { def: "qwen" },
    meta:     { def: "meta" },
    arena:    { def: "arena" },
  };

  function detectProvider() {
    try {
      if (typeof ZSProvider !== 'undefined' && ZSProvider.id) {
        providerId = ZSProvider.id;
        providerName = ZSProvider.displayName || ZSProvider.id;
        return;
      }
    } catch {}
    const h = location.hostname;
    if (h.includes("deepseek")) { providerId = "deepseek"; providerName = "DeepSeek"; }
    else if (h.includes("chatgpt") || h.includes("openai")) { providerId = "chatgpt"; providerName = "ChatGPT"; }
    else if (h.includes("gemini")) { providerId = "gemini"; providerName = "Gemini"; }
    else if (h.includes("kimi")) { providerId = "kimi"; providerName = "Kimi"; }
    else if (h.includes("z.ai")) { providerId = "glm"; providerName = "GLM"; }
    else if (h.includes("qwen")) { providerId = "qwen"; providerName = "Qwen"; }
    else if (h.includes("arena")) { providerId = "arena"; providerName = "Arena"; }
    else if (h.includes("meta")) { providerId = "meta"; providerName = "Meta AI"; }
  }

  const ACTIVE_KEY = "zaActiveTab";
  async function checkActive() {
    try {
      const data = await new Promise(r => chrome.storage.local.get([ACTIVE_KEY], r));
      const at = data[ACTIVE_KEY];
      if (at) {
        if (at.provider === providerId) isActiveTab = true;
        else if (!at.provider) isActiveTab = true;
        else if (at.tabId) {
          // If active tab is different provider, we're inactive (unless auto-switch will activate us)
          isActiveTab = false;
        }
      } else {
        isActiveTab = true;
      }
    } catch {}
  }

  function setActive() {
    isActiveTab = true;
    try {
      chrome.storage.local.set({
        [ACTIVE_KEY]: { provider: providerId, url: location.href, urlPart: location.hostname, timestamp: Date.now(), manual: true },
        zaActiveProvider: providerId
      });
      chrome.runtime.sendMessage({ type: "za-set-active", provider: providerId, url: location.href });
    } catch {}
    renderBar();
    toast(`✓ ${providerName} active for API`);
  }

  let root, bar, dot, brandEl, modelEl, stateEl, actionBtn;
  let anchorPadEl = null;
  function clearAnchorPad() { if (anchorPadEl) { try { anchorPadEl.style.paddingTop = ""; } catch {} anchorPadEl = null; } }

  function build() {
    if (document.getElementById("za-root")) return;
    root = document.createElement("div");
    root.id = "za-root";
    const defModel = (MODEL_MAP[providerId]?.def) || "auto";
    root.innerHTML = `
      <div id="za-bar">
        <span id="za-dot" class="off"></span>
        <span id="za-brand">ZeroAPI <span id="za-model" title="Model name to use in API">${defModel}</span></span>
        <span id="za-state">Checking...</span>
        <button id="za-action">Use this chat</button>
      </div>
    `;
    document.documentElement.appendChild(root);
    bar = root.querySelector("#za-bar");
    dot = root.querySelector("#za-dot");
    brandEl = root.querySelector("#za-brand");
    modelEl = root.querySelector("#za-model");
    stateEl = root.querySelector("#za-state");
    actionBtn = root.querySelector("#za-action");

    actionBtn.addEventListener("click", () => {
      if (isActiveTab) toast("Already active for API");
      else setActive();
    });

    renderBar();
    placeBar();
    log(`bar ready provider=${providerId} model=${defModel} v${VER} with auto-switch`);
  }

  function renderBar() {
    if (!bar) return;
    const info = MODEL_MAP[providerId] || { def: providerId };
    const apiModel = info.def;

    if (modelEl) {
      modelEl.textContent = apiModel;
      modelEl.title = `API model: ${apiModel}\nUse model="${apiModel}" in OpenAI SDK\nAuto-switches between tabs when different model requested`;
    }

    if (isBusy) {
      dot.className = "busy";
      dot.title = `Processing ${currentModel || apiModel}${lastSwitchInfo ? ' (auto-switched from '+lastSwitchInfo.from+')' : ''}`;
    } else if (apiConnected) {
      dot.className = isActiveTab ? "on" : "idle";
      dot.title = isActiveTab ? `Active for API — model: ${apiModel} (auto-switch enabled)` : `API online — click to use ${apiModel} or will auto-switch when ${apiModel} requested`;
    } else {
      dot.className = "off";
      dot.title = "API offline — run python run_server.py";
    }

    if (isBusy) {
      stateEl.textContent = `⏳ ${currentModel || apiModel}...`;
      stateEl.title = `Processing ${currentModel}${lastSwitchInfo ? ' auto-switched from '+lastSwitchInfo.from : ''}`;
    } else if (apiConnected) {
      if (isActiveTab) {
        if (lastSwitchInfo && Date.now() - lastSwitchInfo.time < 5000) {
          stateEl.textContent = `↔️ Switched from ${lastSwitchInfo.from}`;
        } else {
          stateEl.textContent = `✓ Active`;
        }
      } else {
        stateEl.textContent = `Ready`;
      }
      stateEl.title = `Provider: ${providerName} | Model: ${apiModel} | Auto-switch: enabled`;
    } else {
      stateEl.textContent = `Offline`;
      stateEl.title = "API server offline";
    }

    if (isActiveTab) {
      actionBtn.style.display = "none";
    } else {
      actionBtn.style.display = "inline-flex";
      actionBtn.textContent = "Use this chat";
    }

    bar.classList.toggle("za-active", isActiveTab && apiConnected);
    bar.classList.toggle("za-busy", isBusy);
    bar.classList.toggle("za-offline", !apiConnected);
    if (lastSwitchInfo && Date.now() - lastSwitchInfo.time < 3000) {
      bar.classList.add("za-switched");
    } else {
      bar.classList.remove("za-switched");
    }
  }

  function placeBar() {
    requestAnimationFrame(placeBar);
    if (!bar) return;
    if (!bar.isConnected) { try { document.documentElement.appendChild(root); } catch {} }

    const zsBar = document.getElementById("zs-bar");
    let topOffset = 0;
    if (zsBar && zsBar.offsetHeight && zsBar.style.display !== "none") {
      const r = zsBar.getBoundingClientRect();
      if (r.top < 50) topOffset = r.height + 4;
    }

    let mountParent = null, mountBefore = null, mountInside = false;
    try {
      if (typeof ZSProvider !== 'undefined' && ZSProvider.barMount) {
        const m = ZSProvider.barMount();
        if (m && m.parent && m.parent.isConnected) {
          mountParent = m.parent; mountBefore = m.before || null; mountInside = !!m.inside;
        }
      }
    } catch {}

    if (mountParent) {
      clearAnchorPad();
      if (bar.parentElement !== mountParent || bar.nextElementSibling !== mountBefore) {
        try { mountParent.insertBefore(bar, mountBefore); } catch {}
      }
      bar.classList.add("za-bar-inline");
      bar.classList.toggle("za-bar-inside", mountInside);
      bar.classList.remove("za-bar-anchored");
      bar.style.position = ""; bar.style.top = ""; bar.style.left = ""; bar.style.width = ""; bar.style.display = "flex"; bar.style.zIndex = "";
      bar.classList.forEach(c => { if (c.startsWith("za-prov-")) bar.classList.remove(c); });
      bar.classList.add(`za-prov-${providerId}`);
      return;
    }

    let anchorEl = null;
    try { if (typeof ZSProvider !== 'undefined' && ZSProvider.barAnchor) anchorEl = ZSProvider.barAnchor(); } catch {}
    if (anchorEl && anchorEl.isConnected) {
      bar.classList.remove("za-bar-inline", "za-bar-inside");
      bar.classList.add("za-bar-anchored");
      if (root && bar.parentElement !== root) root.appendChild(bar);
      const r = anchorEl.getBoundingClientRect();
      if (!r.width) { bar.style.display = "none"; clearAnchorPad(); return; }
      bar.style.display = "flex";
      const bh = bar.offsetHeight || 32;
      if (anchorPadEl && anchorPadEl !== anchorEl) clearAnchorPad();
      anchorPadEl = anchorEl;
      anchorEl.style.paddingTop = (bh + 6) + "px";
      bar.style.position = "fixed";
      bar.style.left = Math.round(r.left) + "px";
      bar.style.top = Math.round(r.top + topOffset) + "px";
      bar.style.width = Math.round(r.width) + "px";
      bar.style.zIndex = "2147483645";
      bar.classList.forEach(c => { if (c.startsWith("za-prov-")) bar.classList.remove(c); });
      bar.classList.add(`za-prov-${providerId}`);
      return;
    }

    clearAnchorPad();
    bar.classList.remove("za-bar-inline", "za-bar-inside", "za-bar-anchored");
    if (root && bar.parentElement !== root) root.appendChild(bar);
    bar.style.display = "flex";
    bar.style.position = "fixed";
    bar.style.top = topOffset + "px";
    bar.style.left = "0";
    bar.style.width = "100%";
    bar.style.zIndex = "2147483645";
    bar.classList.forEach(c => { if (c.startsWith("za-prov-")) bar.classList.remove(c); });
    bar.classList.add(`za-prov-${providerId}`);
  }

  function toast(msg, long) {
    let t = document.getElementById("za-toast");
    if (!t) { t = document.createElement("div"); t.id = "za-toast"; document.documentElement.appendChild(t); }
    t.textContent = msg; t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), long ? 4000 : 2500);
  }

  function handleAutoSwitch(from, to, reason, model) {
    lastSwitchInfo = { from: from, to: to, reason: reason, model: model, time: Date.now() };
    isActiveTab = (to === providerId);
    renderBar();
    if (isActiveTab) {
      toast(`↔️ Auto-switched: ${from} → ${to} for ${model}`, true);
      // Flash animation
      if (bar) {
        bar.classList.add("za-switched");
        setTimeout(() => bar.classList.remove("za-switched"), 3000);
      }
    }
    log(`Auto-switch handled: ${from} -> ${to} for ${model}, active=${isActiveTab}`);
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg) return;
    if (msg.type === "zs-status" || msg.type === "za-status") {
      if (typeof msg.apiConnected === "boolean") apiConnected = msg.apiConnected;
      if (msg.provider) { /* keep our detected provider */ }
      renderBar();
    }
    if (msg.type === "zeroapi-status") {
      if (typeof msg.busy === "boolean") isBusy = msg.busy;
      if (msg.model) currentModel = msg.model;
      renderBar();
    }
    if (msg.type === "za-active-update") {
      const wasActive = isActiveTab;
      isActiveTab = !!msg.active;
      if (msg.autoSwitched && msg.active) {
        handleAutoSwitch(msg.previousProvider || "unknown", msg.provider || providerId, msg.reason || "auto-switch", currentModel || msg.provider || "");
      } else if (msg.autoSwitched && !wasActive && msg.active) {
        // Became active via auto-switch
        handleAutoSwitch(msg.previousProvider || "?", msg.provider || providerId, msg.reason, "");
      }
      renderBar();
    }
    if (msg.type === "za-auto-switch-notify") {
      handleAutoSwitch(msg.from || "?", msg.to || providerId, msg.reason || "", msg.model || "");
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

  function pageThemeHint() {
    const de = document.documentElement, b = document.body;
    const cls = (de.className + " " + (b ? b.className : "")).toLowerCase();
    if (/\bdark\b/.test(cls)) return "dark";
    if (/\blight\b/.test(cls)) return "light";
    const attr = (de.getAttribute("data-theme") || de.getAttribute("data-color-mode") || "").toLowerCase();
    if (/dark/.test(attr)) return "dark";
    if (/light/.test(attr)) return "light";
    const cs = (getComputedStyle(de).colorScheme || "").toLowerCase();
    if (/dark/.test(cs) && !/light/.test(cs)) return "dark";
    if (/light/.test(cs) && !/dark/.test(cs)) return "light";
    return null;
  }
  function effectiveBg() {
    let n = document.body;
    while (n && n !== document.documentElement) {
      const c = getComputedStyle(n).backgroundColor;
      if (c && !/(transparent)/.test(c) && !/,\s*0\s*\)$/.test(c)) return c;
      n = n.parentElement;
    }
    return getComputedStyle(document.documentElement).backgroundColor || "rgb(255,255,255)";
  }
  function applyTheme() {
    let light;
    const hint = pageThemeHint();
    if (hint) light = hint === "light";
    else {
      const m = (effectiveBg().match(/\d+(?:\.\d+)?/g) || []).map(Number);
      if (m.length < 3) return;
      light = 0.2126*m[0]+0.7152*m[1]+0.0722*m[2] > 140;
    }
    document.documentElement.classList.toggle("za-light", light);
    document.documentElement.classList.toggle("zs-light", light);
  }

  detectProvider();
  checkActive().then(() => {
    build();
    applyTheme();
    setInterval(applyTheme, 2000);
    setInterval(pollStatus, 3000);
    setTimeout(pollStatus, 800);
    setInterval(renderBar, 1000);
  });

  window.__zaBar = {
    setBusy: (b,m) => { isBusy=b; currentModel=m||""; renderBar(); },
    setConnected: (c) => { apiConnected=c; renderBar(); },
    setActive: (a) => { isActiveTab=a; renderBar(); },
    getProvider: () => providerId
  };
  log("ZeroAPI minimal bar v2.6 with auto-switch init", providerId);
})();
