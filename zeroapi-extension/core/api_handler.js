// ZeroAPI - API Mode Handler v2.4 - Full file support + auto-clear
// Supports any file type (images, PDFs, docs, etc.) via OpenAI compatible API
// Files are cleared from browser composer after each request
(() => {
  "use strict";
  
  function waitForProvider() {
    return new Promise((resolve) => {
      const check = () => {
        if (typeof ZSProvider !== 'undefined' && ZSProvider.typeAndSend) {
          resolve(ZSProvider);
        } else {
          setTimeout(check, 100);
        }
      };
      check();
    });
  }

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  
  let currentRequest = null;
  let isProcessing = false;
  let apiConnected = false;

  function ensureIndicator() {
    let ind = document.getElementById("za-api-indicator");
    if (!ind) ind = document.getElementById("zs-api-indicator");
    if (!ind) {
      ind = document.createElement("div");
      ind.id = "za-api-indicator";
      ind.innerHTML = `<span class="za-spin"></span><span id="za-api-ind-text">API request in progress...</span>`;
      document.documentElement.appendChild(ind);
    }
    return ind;
  }

  function showIndicator(text, show) {
    const ind = ensureIndicator();
    const txt = document.getElementById("za-api-ind-text") || document.getElementById("zs-api-ind-text");
    if (txt && text) txt.textContent = text;
    if (show) ind.classList.add("active");
    else ind.classList.remove("active");
  }

  function updateBarBusy(busy, model) {
    isProcessing = busy;
    const zaDot = document.getElementById("za-dot");
    const zsDot = document.getElementById("zs-dot");
    if (busy) {
      if (zaDot) { zaDot.classList.add("api", "busy"); zaDot.classList.remove("off"); }
      if (zsDot) { zsDot.classList.add("api", "busy"); zsDot.classList.remove("off"); }
    } else {
      if (zaDot) zaDot.classList.remove("busy");
      if (zsDot) zsDot.classList.remove("busy");
    }
    try {
      if (window.__zaBar && window.__zaBar.setBusy) window.__zaBar.setBusy(busy, model);
      window.dispatchEvent(new CustomEvent("za-busy", { detail: { busy, model } }));
    } catch {}
    try {
      chrome.runtime.sendMessage({
        type: "zeroapi-status",
        busy: busy,
        model: model || (currentRequest ? currentRequest.model : ""),
        provider: (typeof ZSProvider !== 'undefined' ? ZSProvider.id : "unknown")
      });
    } catch {}
  }

  async function checkApiConnection() {
    try {
      const resp = await new Promise((resolve) => {
        chrome.runtime.sendMessage({ type: "status" }, (s) => {
          if (chrome.runtime.lastError) resolve(null);
          else resolve(s);
        });
      });
      if (resp) {
        apiConnected = !!resp.apiConnected;
        try { if (window.__zaBar && window.__zaBar.setConnected) window.__zaBar.setConnected(apiConnected); } catch {}
      }
    } catch {}
  }

  function messagesToPrompt(messages) {
    if (!messages || !messages.length) return "";
    if (messages.length === 1 && messages[0].role === "user") {
      const c = messages[0].content;
      if (typeof c === "string") return c;
      if (Array.isArray(c)) return c.filter(p => p.type === "text").map(p => p.text).join("\n");
    }
    return messages.map(m => {
      let content = m.content || "";
      if (Array.isArray(content)) content = content.filter(p => p.type === "text").map(p => p.text).join("\n");
      if (m.role === "system") return `[System]: ${content}`;
      if (m.role === "user") return `User: ${content}`;
      if (m.role === "assistant") return `Assistant: ${content}`;
      return `${m.role}: ${content}`;
    }).join("\n\n");
  }

  async function waitForResponse(baseCount, timeoutMs = 180000) {
    const P = ZSProvider;
    const t0 = Date.now();
    let lastText = "";
    let stableSince = 0;
    let started = false;
    let lastSentLen = 0;

    while (Date.now() - t0 < timeoutMs) {
      if (currentRequest && currentRequest.cancelled) return { kind: "cancelled" };
      const gen = P.isGenerating ? P.isGenerating() : false;
      const data = P.readAssistant ? P.readAssistant() : { reply: "", present: false };
      if (!data.present && !gen) { await sleep(250); continue; }
      if (gen) {
        started = true;
        const reply = data.reply || "";
        if (reply && reply.length !== lastText.length) {
          lastText = reply;
          stableSince = 0;
          if (currentRequest && currentRequest.stream) {
            const newPart = reply.slice(lastSentLen);
            if (newPart) { sendChunk(reply, newPart, false); lastSentLen = reply.length; }
          }
          showIndicator(`API: ${currentRequest?.model || ""} generating... ${reply.length} chars`, true);
        }
        await sleep(300);
        continue;
      }
      const finalText = data.reply || lastText || "";
      if (started || finalText.length > 0) {
        if (!stableSince) stableSince = Date.now();
        if (Date.now() - stableSince > 1000) {
          if (currentRequest && currentRequest.stream && finalText.length > lastSentLen) {
            const remaining = finalText.slice(lastSentLen);
            if (remaining) sendChunk(finalText, remaining, false);
          }
          return { kind: "done", text: finalText };
        }
        await sleep(250);
        continue;
      }
      await sleep(250);
    }
    return { kind: "timeout", text: lastText };
  }

  function sendChunk(fullContent, delta, done) {
    if (!currentRequest) return;
    try {
      chrome.runtime.sendMessage({ type: "zeroapi-chat-chunk", id: currentRequest.id, content: fullContent, delta: delta, done: done });
    } catch (e) { console.log("[zeroapi] chunk send failed", e); }
  }

  function sendFinal(content) {
    if (!currentRequest) return;
    try {
      chrome.runtime.sendMessage({ type: "zeroapi-chat-response", id: currentRequest.id, content: content, done: true });
    } catch (e) { console.log("[zeroapi] final send failed", e); }
  }

  function sendError(error) {
    if (!currentRequest) return;
    try {
      chrome.runtime.sendMessage({ type: "zeroapi-chat-error", id: currentRequest.id, error: String(error), done: true });
    } catch (e) { console.log("[zeroapi] error send failed", e); }
  }

  function clearAllAttachments() {
    try {
      if (typeof ZSProvider !== 'undefined' && ZSProvider.clearAttachments) {
        ZSProvider.clearAttachments();
      }
    } catch (e) {
      console.log("[zeroapi] clearAttachments failed", e);
    }
    // Fallback: try to click remove buttons in composer
    try {
      const selectors = [
        "[aria-label*='Remove']",
        "[aria-label*='Delete']",
        "[aria-label*='upprimer']",
        "[class*='remove-attachment']",
        "[class*='delete-attachment']",
        "button[class*='close']"
      ];
      document.querySelectorAll(selectors.join(",")).forEach(btn => {
        const parent = btn.closest("[class*='preview'], [class*='attachment'], [class*='file']");
        if (parent) {
          try { btn.click(); } catch {}
        }
      });
    } catch {}
  }

  async function handleChatRequest(request) {
    if (isProcessing) {
      try {
        chrome.runtime.sendMessage({ type: "zeroapi-chat-error", id: request.id, error: "Browser tab is busy processing another request", done: true });
      } catch {}
      return;
    }

    const files = request.files || request.images || [];
    currentRequest = {
      id: request.id,
      stream: !!request.stream,
      cancelled: false,
      prompt: request.prompt || messagesToPrompt(request.messages),
      model: request.model || "auto",
      files: files
    };

    updateBarBusy(true, currentRequest.model);
    console.log(`[zeroapi] Handling ${request.id} model=${currentRequest.model} stream=${currentRequest.stream} files=${files.length}`);
    if (files.length) {
      console.log(`[zeroapi] Files:`, files.map(f => `${f.filename} (${f.mimeType}, ${f.data ? f.data.length : 0} chars)`));
      showIndicator(`API: ${currentRequest.model} - uploading ${files.length} file(s)...`, true);
    } else {
      showIndicator(`API: ${currentRequest.model} - processing...`, true);
    }

    try {
      const P = await waitForProvider();
      if (P.ensureComposerReady) { try { await P.ensureComposerReady("api"); } catch (e) { console.log("[zeroapi] composer ready failed", e); } }
      const base = P.assistantCount ? P.assistantCount() : 0;
      const prompt = currentRequest.prompt;
      if (!prompt || !prompt.trim()) {
        // Allow empty prompt if files present (e.g. "describe this image")
        if (!files.length) throw new Error("Empty prompt");
      }
      if (P.typeAndSend) {
        // Pass files (any type) to provider's typeAndSend
        await P.typeAndSend(prompt || " ", files.length ? files : null);
      } else throw new Error("Provider does not support sending");

      const result = await waitForResponse(base, 180000);

      // Clear attachments after successful send — as requested: files should be cleared after insertion
      // Wait a bit for upload to finish, then clear
      setTimeout(() => {
        clearAllAttachments();
        console.log("[zeroapi] Cleared attachments after request");
      }, 1000);

      if (result.kind === "cancelled") {
        sendError("Cancelled");
        showIndicator("API: cancelled", true);
        setTimeout(() => showIndicator("", false), 2000);
      } else if (result.kind === "timeout") {
        if (result.text) {
          sendFinal(result.text + "\n\n[Response timed out - partial result]");
          showIndicator("API: timeout (partial)", true);
          setTimeout(() => showIndicator("", false), 3000);
        } else {
          sendError("Timeout waiting for AI response");
          showIndicator("API: timeout", true);
          setTimeout(() => showIndicator("", false), 3000);
        }
      } else {
        sendFinal(result.text || "");
        showIndicator(`API: done (${(result.text||"").length} chars)`, true);
        setTimeout(() => showIndicator("", false), 2500);
      }
    } catch (e) {
      console.error("[zeroapi] Chat request failed", e);
      sendError(e.message || String(e));
      showIndicator(`API: error - ${e.message}`, true);
      setTimeout(() => showIndicator("", false), 4000);
      // Ensure clear even on error
      clearAllAttachments();
    } finally {
      updateBarBusy(false, "");
      currentRequest = null;
      // Final safety clear after 2 seconds
      setTimeout(clearAllAttachments, 2000);
    }
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "zeroapi-chat-request") {
      handleChatRequest(msg);
      sendResponse({ ok: true, received: true, files: (msg.files||[]).length });
      return true;
    }
    if (msg.type === "zeroapi-cancel") {
      if (currentRequest && currentRequest.id === msg.id) currentRequest.cancelled = true;
      sendResponse({ ok: true });
      return true;
    }
    if (msg.type === "zeroapi-status") {
      sendResponse({ ok: true, busy: isProcessing, provider: (typeof ZSProvider !== 'undefined' ? ZSProvider.id : "unknown"), url: location.href, apiConnected: apiConnected });
      return true;
    }
    if (msg.type === "za-status" || msg.type === "zs-status") {
      if (typeof msg.apiConnected === "boolean") {
        apiConnected = msg.apiConnected;
        try { if (window.__zaBar && window.__zaBar.setConnected) window.__zaBar.setConnected(apiConnected); } catch {}
      }
    }
  });

  setInterval(checkApiConnection, 3000);
  setTimeout(checkApiConnection, 1000);

  setTimeout(() => {
    try {
      chrome.runtime.sendMessage({ type: "zeroapi-handler-ready", provider: (typeof ZSProvider !== 'undefined' ? ZSProvider.id : "unknown"), url: location.href, version: "2.4.0" });
      apiConnected = true;
    } catch {}
  }, 1500);

  console.log("[zeroapi] API handler v2.4.0 loaded with full file support for", location.href);
})();
