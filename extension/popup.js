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

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function difficultyClass(d) {
  const k = (d || "").toLowerCase();
  if (k.includes("high")) return "high";
  if (k.includes("struct")) return "structured";
  return "moderate";
}

function renderMatches(matches, hasProfile) {
  const list = $("match-list");
  if (!matches || matches.length === 0) {
    $("results").classList.add("hidden");
    $("empty").classList.remove("hidden");
    return;
  }
  $("empty").classList.add("hidden");
  $("results").classList.remove("hidden");

  list.innerHTML = matches.map((m, i) => `
    <div class="match ${i === 0 ? "top" : ""}">
      <div class="match-head">
        <div>
          <span class="difficulty ${difficultyClass(m.difficulty)}">${escapeHtml(m.difficulty || "Moderate")}</span>
          <h4>${escapeHtml(m.title)}</h4>
        </div>
        <div class="score">${hasProfile ? (m.score ?? "--") + "%" : "--"}</div>
      </div>
      ${hasProfile ? `<p>${escapeHtml(m.reason || "")}</p>` : ""}
      ${m.required_skills && m.required_skills.length ? `
        <div class="skills">
          ${m.required_skills.slice(0, 6).map((s) =>
            `<span class="skill">${escapeHtml(s)}</span>`).join("")}
        </div>` : ""}
    </div>
  `).join("");

  if (!hasProfile) {
    const note = document.createElement("p");
    note.style.cssText = "padding:8px 14px; color:#b45309; font-size:12px;";
    note.innerHTML =
      `Set up your profile to see match scores. ` +
      `<a href="#" id="open-options-2">Open settings</a>`;
    list.appendChild(note);
    note.querySelector("#open-options-2")
      .addEventListener("click", openOptions);
  }
}

function setStatus(text, level = "") {
  const el = $("status");
  el.textContent = text;
  el.className = "status" + (level ? " " + level : "");
}

function showLoading(text) {
  $("empty").classList.add("hidden");
  $("results").classList.remove("hidden");
  $("match-list").innerHTML =
    `<div class="loading"><span class="spinner"></span>${escapeHtml(text)}</div>`;
}

function openOptions(e) {
  if (e) e.preventDefault();
  chrome.runtime.openOptionsPage();
}

async function rescan() {
  showLoading("Reading this page with the local model...");
  chrome.runtime.sendMessage({ type: "rescan" }, (result) => {
    if (!result) {
      setStatus("No response from extension.", "error");
      return;
    }
    if (result.error) {
      setStatus(result.error, "error");
      $("match-list").innerHTML = "";
      $("empty").classList.remove("hidden");
      return;
    }
    handleResult(result);
  });
}

function handleResult(data) {
  const oppCount = (data.opportunities || []).length;
  if (oppCount === 0) {
    setStatus("No research opportunities found on this page.");
  } else if (!data.has_profile) {
    setStatus(
      `Found ${oppCount} opportunity${oppCount === 1 ? "" : "s"}. ` +
      `Set up your profile to see match scores.`,
      "warn",
    );
  } else {
    setStatus(
      `Found ${oppCount} opportunity${oppCount === 1 ? "" : "s"}. ` +
      `Ranked by contextual fit.`,
    );
  }
  renderMatches(data.matches, data.has_profile);
}

async function init() {
  $("settings").addEventListener("click", openOptions);
  $("open-options").addEventListener("click", openOptions);
  $("rescan").addEventListener("click", rescan);
  $("rescan2").addEventListener("click", rescan);

  const [tab] = await chrome.tabs.query({
    active: true, currentWindow: true,
  });
  if (!tab) return setStatus("No active tab.", "error");

  chrome.runtime.sendMessage(
    { type: "get-tab-state", tabId: tab.id },
    (state) => {
      if (!state) {
        setStatus("Click Rescan to analyze this page.");
        $("empty").classList.remove("hidden");
        return;
      }
      handleResult(state);
    },
  );
}

init();
