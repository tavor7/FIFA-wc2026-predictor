const API = "";

const LIVE_STATUSES = new Set([
  "1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED",
]);

let activeTab = "matches";

const $ = (sel) => document.querySelector(sel);
const content = $("#content");
const loading = $("#loading");
const errorBox = $("#error");
const modal = $("#match-modal");
const modalBody = $("#modal-body");

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function isLive(status) {
  return LIVE_STATUSES.has(status);
}

function disclaimerHtml() {
  return `<div class="disclaimer">
    This app is for educational and research purposes only. Predictions are probabilistic estimates,
    not guarantees. Not betting or financial advice. Not affiliated with FIFA.
  </div>`;
}

function outcomeBar(pred) {
  if (!pred) return "";
  const h = (pred.home_win_prob * 100).toFixed(1);
  const d = (pred.draw_prob * 100).toFixed(1);
  const a = (pred.away_win_prob * 100).toFixed(1);
  return `<div class="outcome-bar" title="Home ${h}% · Draw ${d}% · Away ${a}%">
    <span class="bar-home" style="width:${h}%"></span>
    <span class="bar-draw" style="width:${d}%"></span>
    <span class="bar-away" style="width:${a}%"></span>
  </div>`;
}

function matchCardHtml(match, { clickable = true } = {}) {
  const live = isLive(match.status);
  const pred = match.prediction;
  const top = pred?.top_scorelines?.[0];
  const pickHome = top?.home ?? Math.round(pred?.predicted_home_goals ?? 0);
  const pickAway = top?.away ?? Math.round(pred?.predicted_away_goals ?? 0);
  const pickPct = top?.probability ?? 0;
  const hasScore = match.home_goals != null && match.away_goals != null;
  const center = hasScore
    ? `${match.home_goals}–${match.away_goals}`
    : `${pickHome}–${pickAway}`;

  const tag = live
    ? `<span class="badge-live">● LIVE</span>`
    : `<span class="badge-upcoming">UPCOMING</span>`;

  const conf =
    !hasScore && pickPct > 0
      ? `<div class="conf">${(pickPct * 100).toFixed(0)}% likely</div>`
      : "";

  const attrs = clickable
    ? `class="card${live ? " live" : ""}" data-id="${match.id}" role="button" tabindex="0"`
    : `class="card${live ? " live" : ""}"`;

  return `<article ${attrs}>
    <div class="card-meta">${tag}<span class="card-date">${formatDate(match.date)}</span></div>
    <div class="match-row">
      <div class="team home">${escapeHtml(match.home_team)}</div>
      <div class="score-block">
        <div class="score">${center}</div>
        <div class="pick-label">${hasScore ? "Score" : "Pick"}</div>
        ${conf}
      </div>
      <div class="team away">${escapeHtml(match.away_team)}</div>
    </div>
    ${outcomeBar(pred)}
  </article>`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function statsHtml(stats) {
  return `<div class="stats">
    <div class="stat"><div class="stat-val">${stats.upcoming}</div><div class="stat-lbl">Upcoming</div></div>
    <div class="stat"><div class="stat-val">${stats.live}</div><div class="stat-lbl">Live</div></div>
    <div class="stat"><div class="stat-val">${stats.predictions}</div><div class="stat-lbl">Picks</div></div>
  </div>`;
}

function showLoading(show) {
  loading.classList.toggle("hidden", !show);
}

function showError(msg) {
  if (!msg) {
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
    return;
  }
  errorBox.textContent = msg;
  errorBox.classList.remove("hidden");
}

async function loadMatches() {
  const [matches, stats] = await Promise.all([
    request("/matches/upcoming"),
    request("/stats"),
  ]);
  content.innerHTML =
    disclaimerHtml() +
    statsHtml(stats) +
    (matches.length
      ? matches.map((m) => matchCardHtml(m)).join("")
      : `<p class="empty">No matches yet. Click <strong>Refresh data</strong> to sync.</p>`);
  bindCardClicks();
}

async function loadLive() {
  await request("/sync/live", { method: "POST" }).catch(() => null);
  const matches = await request("/matches/live");
  content.innerHTML =
    disclaimerHtml() +
    (matches.length
      ? matches.map((m) => matchCardHtml(m)).join("")
      : `<p class="empty">No live matches right now.</p>`);
  bindCardClicks();
}

async function loadResults() {
  const matches = await request("/matches/recent");
  content.innerHTML =
    disclaimerHtml() +
    (matches.length
      ? matches
          .map(
            (m) => `<div class="result-row">
          <div class="result-info">
            <div class="result-teams">${escapeHtml(m.home_team)} vs ${escapeHtml(m.away_team)}</div>
            <div class="result-date">${formatDate(m.date)}</div>
          </div>
          <div class="result-score">${m.home_goals ?? "–"}–${m.away_goals ?? "–"}</div>
        </div>`
          )
          .join("")
      : `<p class="empty">No results yet.</p>`);
}

async function loadTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".tab").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === tab);
  });
  showError(null);
  showLoading(true);
  try {
    if (tab === "matches") await loadMatches();
    else if (tab === "live") await loadLive();
    else await loadResults();
  } catch (e) {
    showError(e.message || "Failed to load");
    content.innerHTML = disclaimerHtml();
  } finally {
    showLoading(false);
  }
}

function bindCardClicks() {
  content.querySelectorAll(".card[data-id]").forEach((el) => {
    el.addEventListener("click", () => openMatch(Number(el.dataset.id)));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openMatch(Number(el.dataset.id));
      }
    });
  });
}

async function openMatch(id) {
  modalBody.innerHTML = `<div class="loading"><div class="spinner"></div><p>Loading match…</p></div>`;
  modal.showModal();
  try {
    const match = await request(`/matches/${id}`);
    const pred = match.prediction;
    const alts = pred?.top_scorelines?.slice(1, 5) ?? [];
    let extra = "";
    if (pred?.explanation) {
      extra += `<div class="section"><h3>Why this score?</h3><p>${escapeHtml(pred.explanation)}</p>`;
      if (alts.length) {
        extra += `<div class="chips">${alts
          .map(
            (s) =>
              `<span class="chip">${s.home}–${s.away} · ${(s.probability * 100).toFixed(0)}%</span>`
          )
          .join("")}</div>`;
      }
      extra += `</div>`;
    }
    if (match.injuries?.length) {
      extra += `<div class="section"><h3>Injuries</h3><ul>${match.injuries
        .map(
          (i) =>
            `<li>${escapeHtml(i.player_name)} (${escapeHtml(i.team)}) — ${escapeHtml(i.reason || i.injury_type || "Out")}</li>`
        )
        .join("")}</ul></div>`;
    }
    modalBody.innerHTML = disclaimerHtml() + matchCardHtml(match, { clickable: false }) + extra;
  } catch (e) {
    modalBody.innerHTML = `<p class="empty">${escapeHtml(e.message)}</p>`;
  }
}

async function refreshData() {
  const btn = $("#btn-refresh");
  btn.disabled = true;
  btn.textContent = "Refreshing…";
  showError(null);
  try {
    await request("/sync/matches", { method: "POST" });
    await request("/predictions/generate", { method: "POST" }).catch(() => null);
    await loadTab(activeTab);
  } catch (e) {
    showError("Refresh failed — try again in a minute (Render free tier can be slow).");
  } finally {
    btn.disabled = false;
    btn.textContent = "Refresh data";
  }
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => loadTab(tab.dataset.tab));
});

$("#btn-refresh").addEventListener("click", refreshData);
$("#modal-close").addEventListener("click", () => modal.close());
modal.addEventListener("click", (e) => {
  if (e.target === modal) modal.close();
});

loadTab("matches");
