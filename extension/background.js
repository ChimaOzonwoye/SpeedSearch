// SpeedSearch - Contextual matching for university research discovery.
// Copyright (C) 2026 Aadharsh Sakkaravarthy, Ted Erdos, Ali Salama,
//                    Chima Ozonwoye.
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

// Service worker for the SpeedSearch extension.  It brokers messages
// between the content script (which scrapes the page) and the local
// Flask+Ollama backend, and caches per-tab results so the popup and
// action badge stay in sync.

const DEFAULT_BACKEND = "http://localhost:5000";

async function backendUrl() {
  const { backend } = await chrome.storage.local.get("backend");
  return backend || DEFAULT_BACKEND;
}

// Per-tab cache of the latest detection so the popup can render
// immediately and the badge can reflect the top match score.
const tabState = new Map();

function setBadge(tabId, matches) {
  if (!tabId) return;
  if (!matches || matches.length === 0) {
    chrome.action.setBadgeText({ text: "", tabId });
    return;
  }
  const top = Math.max(...matches.map((m) => m.score || 0));
  chrome.action.setBadgeText({ text: `${top}`, tabId });
  chrome.action.setBadgeBackgroundColor({
    color: top >= 75 ? "#16a34a" : top >= 50 ? "#2563eb" : "#64748b",
    tabId,
  });
}

async function detect({ text, url, tabId }) {
  const base = await backendUrl();
  let resp;
  try {
    resp = await fetch(`${base}/api/detect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, url }),
    });
  } catch (err) {
    return { error: `cannot reach backend at ${base}: ${err.message}` };
  }
  const data = await resp.json();
  if (!resp.ok) return { error: data.error || "detect failed" };

  tabState.set(tabId, { ...data, url, ts: Date.now() });
  setBadge(tabId, data.matches);
  return data;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "page-text") {
        const tabId = sender?.tab?.id;
        const result = await detect({
          text: msg.text,
          url: msg.url,
          tabId,
        });
        sendResponse(result);
        return;
      }
      if (msg.type === "get-tab-state") {
        const tabId = msg.tabId;
        sendResponse(tabState.get(tabId) || null);
        return;
      }
      if (msg.type === "rescan") {
        const [tab] = await chrome.tabs.query({
          active: true, currentWindow: true,
        });
        if (!tab) return sendResponse({ error: "no active tab" });
        try {
          await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ["content.js"],
          });
        } catch (_) { /* already injected */ }
        chrome.tabs.sendMessage(tab.id, { type: "scan-now" }, (result) => {
          sendResponse(result);
        });
        return;
      }
      sendResponse({ error: "unknown message" });
    } catch (e) {
      sendResponse({ error: String(e.message || e) });
    }
  })();
  return true; // async sendResponse
});

// Clear per-tab state when tabs close so we do not leak memory.
chrome.tabs.onRemoved.addListener((tabId) => tabState.delete(tabId));
