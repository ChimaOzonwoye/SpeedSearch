// SpeedSearch frontend logic.
// Tabs, form submission, rendering of opportunities & matches.

const loader = document.getElementById("loader");
const loaderMsg = document.getElementById("loader-msg");

function showLoader(msg) {
  loaderMsg.textContent = msg || "Analyzing with local LLM...";
  loader.classList.remove("hidden");
}
function hideLoader() { loader.classList.add("hidden"); }

// --- tabs ---
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "browse") loadOpportunities();
  });
});

// --- utility ---
function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}
function diffClass(d) {
  if (!d) return "moderate";
  const k = d.toLowerCase();
  if (k.includes("high")) return "high";
  if (k.includes("struct")) return "structured";
  return "moderate";
}
function skillTags(skills) {
  if (!skills || !skills.length) return "";
  return `<div class="skills">${skills.map(s =>
    `<span class="skill">${escapeHtml(s)}</span>`).join("")}</div>`;
}

// --- professor submit ---
document.getElementById("prof-form").addEventListener("submit", async e => {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);
  showLoader("Parsing research document...");
  try {
    const res = await fetch("/api/professor/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "upload failed");
    renderProfResult(data);
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    hideLoader();
  }
});

function renderProfResult(data) {
  const box = document.getElementById("prof-result");
  box.classList.remove("hidden");
  const opps = data.opportunities || [];
  box.innerHTML = `
    <div class="card">
      <h3>Extracted ${opps.length} opportunit${opps.length === 1 ? "y" : "ies"}</h3>
      <p style="color: var(--muted); font-size: 13px;">
        These are now searchable by students. You'll get a ping every 2 days
        asking if each is still open.
      </p>
    </div>
    ${opps.map(o => `
      <div class="opp">
        <span class="difficulty ${diffClass(o.difficulty)}">${escapeHtml(o.difficulty || "Moderate")}</span>
        <h3>${escapeHtml(o.title)}</h3>
        <p>${escapeHtml(o.description || "")}</p>
        ${skillTags(o.required_skills)}
      </div>
    `).join("")}
  `;
  box.scrollIntoView({ behavior: "smooth" });
}

// --- student submit ---
document.getElementById("student-form").addEventListener("submit", async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  showLoader("Analyzing portfolio and scoring matches...");
  try {
    const res = await fetch("/api/student/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "upload failed");
    renderStudentResult(data);
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    hideLoader();
  }
});

function renderStudentResult(data) {
  const box = document.getElementById("student-result");
  box.classList.remove("hidden");
  const p = data.portfolio || {};
  const matches = data.matches || [];

  const portfolio = `
    <div class="portfolio-box">
      <h3>What SpeedSearch sees in your work</h3>
      <p><strong>Summary:</strong> ${escapeHtml(p.summary || "")}</p>
      ${skillTags(p.skills)}
      ${p.experience && p.experience.length ? `
        <p style="margin-top:10px;"><strong>Experience signals:</strong></p>
        <ul>${p.experience.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
      ` : ""}
    </div>
  `;

  const header = `
    <div class="card">
      <h3>Top Contextual Matches</h3>
      <p style="color: var(--muted); font-size: 13px;">
        Scored by what you've actually built vs. what each project needs.
      </p>
    </div>
  `;

  const matchCards = matches.length === 0
    ? `<div class="card"><p>No open opportunities yet. Ask a professor to upload one.</p></div>`
    : matches.map((m, i) => `
      <div class="match ${i === 0 ? "top" : ""}">
        <div class="left">
          ${i === 0 ? `<span class="difficulty structured">Top Match</span>` : ""}
          <h3>${escapeHtml(m.title)}</h3>
          <p>${escapeHtml(m.reason)}</p>
        </div>
        <div class="score">${m.score}%</div>
      </div>
    `).join("");

  box.innerHTML = portfolio + header + matchCards;
  box.scrollIntoView({ behavior: "smooth" });
}

// --- browse ---
async function loadOpportunities() {
  const list = document.getElementById("opps-list");
  list.innerHTML = `<p style="color: var(--muted);">Loading...</p>`;
  try {
    const res = await fetch("/api/opportunities");
    const opps = await res.json();
    if (!opps.length) {
      list.innerHTML = `<div class="card"><p>No opportunities yet.</p></div>`;
      return;
    }
    list.innerHTML = opps.map(o => `
      <div class="opp">
        <span class="difficulty ${diffClass(o.difficulty)}">${escapeHtml(o.difficulty || "Moderate")}</span>
        ${o.is_open ? "" : `<span class="closed-badge">Closed</span>`}
        <h3>${escapeHtml(o.title)}</h3>
        <p style="color: var(--muted); font-size: 12px;">Posted by Prof. ${escapeHtml(o.professor)}</p>
        <p>${escapeHtml(o.description || "")}</p>
        ${skillTags(o.required_skills)}
      </div>
    `).join("");
  } catch (err) {
    list.innerHTML = `<div class="card"><p>Error: ${escapeHtml(err.message)}</p></div>`;
  }
}

document.getElementById("refresh-opps").addEventListener("click", loadOpportunities);
document.getElementById("ping-now").addEventListener("click", async () => {
  showLoader("Sending professor pings...");
  try {
    await fetch("/api/ping-now", { method: "POST" });
    alert("Pings sent (check console if SMTP isn't configured).");
  } finally { hideLoader(); }
});
