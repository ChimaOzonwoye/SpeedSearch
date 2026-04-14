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

const DEFAULT_BACKEND = "http://localhost:5000";
const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function getBackend() {
  const { backend } = await chrome.storage.local.get("backend");
  return backend || DEFAULT_BACKEND;
}

async function setBackend(url) {
  await chrome.storage.local.set({ backend: url });
}

function setStatus(el, text, level) {
  el.textContent = text;
  el.className = "status" + (level ? " " + level : "");
}

async function testBackend() {
  const url = $("backend").value.trim() || DEFAULT_BACKEND;
  setStatus($("backend-status"), "Contacting backend...", "working");
  try {
    const r = await fetch(`${url}/health`);
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error("backend not healthy");
    await setBackend(url);
    setStatus(
      $("backend-status"),
      data.ollama
        ? `Connected. Model: ${data.model}.`
        : `Connected, but Ollama is not reachable from the backend.`,
      data.ollama ? "ok" : "error",
    );
    if (data.profile) loadProfile();
  } catch (err) {
    setStatus(
      $("backend-status"),
      `Cannot reach ${url}. Make sure the backend is running (./run.sh).`,
      "error",
    );
  }
}

async function loadProfile() {
  const backend = await getBackend();
  try {
    const r = await fetch(`${backend}/api/profile`);
    const p = await r.json();
    if (!p || !p.name) return;
    $("profile-form").name.value = p.name || "";
    $("profile-form").email.value = p.email || "";
    $("profile-form").availability.value = p.availability || "";
    renderCurrent(p);
  } catch (_) { /* ignore */ }
}

function renderCurrent(p) {
  if (!p || !p.summary) return;
  $("current").classList.remove("hidden");
  $("current-summary").textContent = p.summary || "";
  $("current-skills").innerHTML = (p.skills || [])
    .map((s) => `<span class="skill">${escapeHtml(s)}</span>`).join("");
  $("current-experience").innerHTML = (p.experience || [])
    .map((x) => `<li>${escapeHtml(x)}</li>`).join("");
}

async function saveProfile(event) {
  event.preventDefault();
  const backend = await getBackend();
  const fd = new FormData(event.target);
  setStatus($("save-status"),
    "Analyzing with local model, this can take a minute on first run...",
    "working");
  try {
    const r = await fetch(`${backend}/api/profile`, {
      method: "POST",
      body: fd,
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "save failed");
    setStatus($("save-status"), "Saved.", "ok");
    renderCurrent(data);
  } catch (err) {
    setStatus($("save-status"), `Error: ${err.message}`, "error");
  }
}

async function init() {
  $("backend").value = await getBackend();
  $("test-backend").addEventListener("click", testBackend);
  $("profile-form").addEventListener("submit", saveProfile);
  await loadProfile();
}

init();
