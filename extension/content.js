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

// Content script.  Runs on every page.  If the page looks like a
// research or faculty listing, it pulls the visible text and hands it
// to the background worker, which calls the local backend.  The user
// can also trigger a scan manually from the popup via a "rescan"
// message.

(() => {
  if (window.__speedSearchLoaded) return;
  window.__speedSearchLoaded = true;

  const RESEARCH_HINTS = [
    "research",
    "lab",
    "laboratory",
    "principal investigator",
    "faculty",
    "undergraduate research",
    "reu ",
    "graduate student",
    "postdoc",
    "thesis",
    "open positions",
    "join the lab",
    "we are hiring",
    "looking for students",
    "independent study",
    "student researcher",
  ];

  function getPageText() {
    // Prefer the main article/content regions, fall back to body text.
    const candidates = [
      document.querySelector("main"),
      document.querySelector("article"),
      document.querySelector('[role="main"]'),
      document.querySelector("#content"),
      document.querySelector(".content"),
      document.body,
    ];
    const node = candidates.find(Boolean) || document.body;
    const raw = (node.innerText || "").replace(/\s+/g, " ").trim();
    return raw.slice(0, 40000);
  }

  function looksLikeResearch(text) {
    const lower = text.toLowerCase();
    const hits = RESEARCH_HINTS.filter((h) => lower.includes(h)).length;
    return hits >= 2 && lower.length > 500;
  }

  function postScan() {
    const text = getPageText();
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(
        { type: "page-text", text, url: location.href },
        (result) => resolve(result || { error: "no response" }),
      );
    });
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg?.type === "scan-now") {
      postScan().then(sendResponse);
      return true;
    }
  });

  // Auto-scan on page load if the heuristic says this looks like a
  // research page.  Users can always rescan manually from the popup.
  try {
    const text = getPageText();
    if (looksLikeResearch(text)) postScan();
  } catch (_) { /* ignore */ }
})();
