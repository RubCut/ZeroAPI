// ZeroAPI - API Mode Handler
// This content script handles chat requests from ZeroAPI server via browser automation
// Based on ZeroScript's ZSProvider interface - reuses all provider DOM logic
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

  // UI: API indicator
  function ensureIndicator() {
    let ind = document.getElementById("zs-api-indicator");
    if (!ind) {
      ind = document.createElement("div");
      ind.id = "zs-api-indicator";
      ind.innerHTML = `<span class="zs-spin"></span><span id="zs-api-ind-text">API request in progress...</span>`;
      document.documentElement.appendChild(ind);
    }
    return ind;
  }

  function showIndicator(text, show) {
    const ind = ensureIndicator();
    const txt = document.getElementById("zs-api-ind-text");
    if (txt && text) txt.textContent = text;
    if (show) ind.classList.add("active");
    else ind.classList.remove("active");
  }

  function updateDotStatus() {
    // Try to update the ZeroScript dot to show API status
    const dot = document.getElementById("zs-dot");
    if (!dot) return;
    
    if (isProcessing) {
      dot.classList.add("api", "busy");
      dot.classList.remove("on", "off", "warn");
      dot.title = `ZeroAPI: processing ${currentRequest ? currentRequest.id : ""} | ${ZSProvider ? ZSProvider.id : "unknown"}`;
    } else if (apiConnected) {
      dot.classList.add("api");
      dot.classList.remove("busy", "off", "warn");
      dot.title = `ZeroAPI: connected (${ZSProvider ? ZSProvider.id : "unknown"}) | Ready for API requests`;
    }
  }

  // Poll API connection status from background
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
        updateDotStatus();
      }
    } catch {}
  }

  // Convert OpenAI messages to prompt
  function messagesToPrompt(messages) {
    if (!messages || !messages.length) return "";
    if (messages.length === 1 && messages[0].role === "user") {
      const c = messages[0].content;
      if (typeof c === "string") return c;
      if (Array.isArray(c)) {
        return c.filter(p => p.type === "text").map(p => p.text).join("\n");
      }
    }
    return messages.map(m => {
      let content = m.content || "";
      if (Array.isArray(content)) {
        content = content.filter(p => p.type === "text").map(p => p.text).join("\n");
      }
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
      if (currentRequest && currentRequest.cancelled) {
        return { kind: "cancelled" };
      }

      const gen = P.isGenerating ? P.isGenerating() : false;
      const data = P.readAssistant ? P.readAssistant() : { reply: "", present: false };
      
      if (!data.present && !gen) {
        await sleep(250);
        continue;
      }

      if (gen) {
        started = true;
        const reply = data.reply || "";
        if (reply && reply.length !== lastText.length) {
          lastText = reply;
          stableSince = 0;
          // Streaming: send delta
          if (currentRequest && currentRequest.stream) {
            const newPart = reply.slice(lastSentLen);
            if (newPart) {
              sendChunk(reply, newPart, false);
              lastSentLen = reply.length;
            }
          }
          // Update indicator
          showIndicator(`API: generating... ${reply.length} chars`, true);
        }
        await sleep(300);
        continue;
      }

      // Generation ended
      const finalText = data.reply || lastText || "";
      if (started || finalText.length > 0) {
        if (!stableSince) stableSince = Date.now();
        if (Date.now() - stableSince > 1000) {
          // Send remaining if streaming and not yet sent
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
      chrome.runtime.sendMessage({
        type: "zeroapi-chat-chunk",
        id: currentRequest.id,
        content: fullContent,
        delta: delta,
        done: done
      });
    } catch (e) {
      console.log("[zeroapi] chunk send failed", e);
    }
  }

  function sendFinal(content) {
    if (!currentRequest) return;
    try {
      chrome.runtime.sendMessage({
        type: "zeroapi-chat-response",
        id: currentRequest.id,
        content: content,
        done: true
      });
    } catch (e) {
      console.log("[zeroapi] final send failed", e);
    }
  }

  function sendError(error) {
    if (!currentRequest) return;
    try {
      chrome.runtime.sendMessage({
        type: "zeroapi-chat-error",
        id: currentRequest.id,
        error: String(error),
        done: true
      });
    } catch (e) {
      console.log("[zeroapi] error send failed", e);
    }
  }

  async function handleChatRequest(request) {
    if (isProcessing) {
      sendError("Browser tab is busy processing another request");
      return;
    }

    isProcessing = true;
    currentRequest = {
      id: request.id,
      stream: !!request.stream,
      cancelled: false,
      prompt: request.prompt || messagesToPrompt(request.messages),
      model: request.model || "auto"
    };

    console.log(`[zeroapi] Handling chat request ${request.id} model=${currentRequest.model} stream=${currentRequest.stream}`);
    showIndicator(`API: ${currentRequest.model} - processing...`, true);
    updateDotStatus();

    try {
      const P = await waitForProvider();
      
      if (P.ensureComposerReady) {
        try { await P.ensureComposerReady("api"); } catch (e) { console.log("[zeroapi] composer ready failed", e); }
      }

      const base = P.assistantCount ? P.assistantCount() : 0;
      const prompt = currentRequest.prompt;
      if (!prompt || !prompt.trim()) throw new Error("Empty prompt");

      // Send via provider
      if (P.typeAndSend) {
        await P.typeAndSend(prompt, null);
      } else {
        throw new Error("Provider does not support sending");
      }

      const result = await waitForResponse(base, 180000);

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
    } finally {
      isProcessing = false;
      currentRequest = null;
      updateDotStatus();
    }
  }

  // Message listener
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "zeroapi-chat-request") {
      handleChatRequest(msg);
      sendResponse({ ok: true, received: true });
      return true;
    }
    if (msg.type === "zeroapi-cancel") {
      if (currentRequest && currentRequest.id === msg.id) currentRequest.cancelled = true;
      sendResponse({ ok: true });
      return true;
    }
    if (msg.type === "zeroapi-status") {
      sendResponse({ 
        ok: true, 
        busy: isProcessing,
        provider: (typeof ZSProvider !== 'undefined' ? ZSProvider.id : "unknown"),
        url: location.href,
        apiConnected: apiConnected
      });
      return true;
    }
    if (msg.type === "zs-status") {
      if (typeof msg.apiConnected === "boolean") {
        apiConnected = msg.apiConnected;
        updateDotStatus();
      }
    }
  });

  // Periodic status check
  setInterval(checkApiConnection, 3000);
  setTimeout(checkApiConnection, 1000);

  // Notify ready
  setTimeout(() => {
    try {
      chrome.runtime.sendMessage({
        type: "zeroapi-handler-ready",
        provider: (typeof ZSProvider !== 'undefined' ? ZSProvider.id : "unknown"),
        url: location.href,
        version: "2.0.0"
      });
      apiConnected = true; // optimistic
      updateDotStatus();
    } catch {}
  }, 1500);

  console.log("[zeroapi] API handler v2.0.0 loaded for", location.href);
})();
