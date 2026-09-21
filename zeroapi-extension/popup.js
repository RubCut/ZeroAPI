const KOFI_URL = "https://ko-fi.com/sebattfg";
const SUPPORTED_HOSTS = [
  "chat.deepseek.com", "deepseek.com", "chatgpt.com", "chat.openai.com",
  "gemini.google.com", "www.kimi.ai", "kimi.ai",
  "chat.z.ai", "chat.qwen.ai", "arena.ai", "www.meta.ai", "meta.ai",
];
const DEFAULT_AI_URL = "https://chat.deepseek.com/";
const DASHBOARD_URL = "http://localhost:8000/";

document.getElementById("ver").textContent = `v${chrome.runtime.getManifest().version}`;

function render(s) {
  const dot = document.getElementById("dot");
  const state = document.getElementById("state");
  const tools = document.getElementById("tools");
  const servers = document.getElementById("servers");
  const apiState = document.getElementById("api-state");
  const legacyState = document.getElementById("legacy-state");
  const browsers = document.getElementById("browsers");

  const list = s.servers || [];
  const up = list.filter((x) => x.alive).length;
  const mcpOk = s.connected && (s.mcpAlive || up > 0 || s.tools > 0);
  const studioOff = mcpOk && s.studio === false;
  const ok = mcpOk && !studioOff;

  // Main dot reflects API + legacy
  if (s.apiConnected) {
    dot.className = "dot api";
  } else if (s.connected && ok) {
    dot.className = "dot on";
  } else if (s.connected) {
    dot.className = "dot warn";
  } else {
    dot.className = "dot";
  }

  // API status
  if (apiState) {
    apiState.innerHTML = s.apiConnected 
      ? `✅ <b>API Server</b>: Connected (8000) <span class="badge ok">online</span>`
      : `❌ <b>API Server</b>: Offline <span class="badge warn">run server</span><br><small style="opacity:0.6">Run: python -m server.main</small>`;
  }

  if (legacyState) {
    legacyState.innerHTML = s.connected
      ? (ok ? `✅ <b>Legacy Bridge</b>: Roblox ready` : `⚠️ <b>Legacy Bridge</b>: ${studioOff ? "Studio not connected" : "Bridge OK, open Studio"}`)
      : `⚪ <b>Legacy Bridge</b>: Offline (optional)`;
  }

  if (browsers) {
    // Count browsers via tabs query? For now show API client ID
    browsers.textContent = `Client ID: ${s.apiClientId || "-"} | Tools: ${s.tools || 0}`;
  }

  state.textContent = s.apiConnected
    ? `ZeroAPI ready - ${s.connected ? " + Roblox tools" : "browser mode"}`
    : s.connected
      ? (ok ? "Legacy: Connected · Roblox Studio ready" : "Legacy: Bridge OK, no Studio")
      : "Offline - start API server";

  tools.textContent = s.connected ? `${s.tools || 0} legacy tools available` : "Legacy tools: none (API mode uses browser)";

  if (servers) {
    servers.textContent = s.connected
      ? list.map((x) => `${x.alive ? "●" : "○"} ${x.id} (${x.alive ? x.tools + " tools" : "down"})`).join("\n")
      : "";
  }
}

function refresh() {
  chrome.runtime.sendMessage({ type: "status" }, (s) => s && render(s));
}

document.getElementById("open-dashboard").addEventListener("click", () => {
  chrome.tabs.create({ url: DASHBOARD_URL });
});

document.getElementById("reconnect").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "reconnect" }, () => setTimeout(refresh, 600));
});

document.getElementById("restart").addEventListener("click", (e) => {
  e.target.textContent = "Restarting…";
  chrome.runtime.sendMessage({ type: "restart_mcp" }, () => {
    e.target.textContent = "⟳ Restart Roblox server";
    setTimeout(refresh, 600);
  });
});

document.getElementById("kofi").addEventListener("click", () => {
  chrome.tabs.create({ url: KOFI_URL });
});

document.getElementById("settings").addEventListener("click", () => {
  chrome.tabs.query({}, (tabs) => {
    const active = tabs.find((t) => t.active && t.url && SUPPORTED_HOSTS.some((h) => t.url.includes(h)));
    const anySupported = active || tabs.find((t) => t.url && SUPPORTED_HOSTS.some((h) => t.url.includes(h)));
    if (anySupported) {
      chrome.tabs.sendMessage(anySupported.id, { type: "zs-open-menu" });
      chrome.tabs.update(anySupported.id, { active: true });
    } else {
      chrome.tabs.create({ url: DEFAULT_AI_URL });
    }
  });
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "zs-status") render(msg);
});

refresh();
setInterval(refresh, 2000);
