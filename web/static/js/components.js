import { escapeHtml, teamBadgeHtml, teamLinkHtml } from "./flags.js";

export const LIVE_STATUSES = new Set([
  "1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED",
]);

export function parseUtcIso(iso) {
  if (!iso) return null;
  const s = String(iso).trim();
  if (!s) return null;
  // Server stores UTC without a Z suffix — treat naive ISO as UTC.
  const normalized = /[Zz]$|[+-]\d{2}:\d{2}$/.test(s) ? s : `${s}Z`;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDate(iso) {
  try {
    const d = parseUtcIso(iso);
    if (!d) return iso;
    return d.toLocaleString("en-US", {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function formatPct(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${(Number(value) * 100).toFixed(0)}%`;
}

export function formatAvg(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(2);
}

/** Monitor / admin timestamps — always Israel (Asia/Jerusalem). */
export function formatDateIsrael(iso) {
  try {
    const d = parseUtcIso(iso);
    if (!d) return iso || "—";
    return d.toLocaleString("en-IL", {
      timeZone: "Asia/Jerusalem",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return iso || "—";
  }
}

export function isLive(status) {
  return LIVE_STATUSES.has(status);
}

export function disclaimerHtml(compact = false) {
  return `<div class="disclaimer${compact ? " compact" : ""}">
    <strong>Research only.</strong> Predictions are estimates, not guarantees.
    Not betting advice. Not affiliated with FIFA.
  </div>`;
}

export function outcomeBar(pred) {
  if (!pred) return "";
  const h = (pred.home_win_prob * 100).toFixed(0);
  const d = (pred.draw_prob * 100).toFixed(0);
  const a = (pred.away_win_prob * 100).toFixed(0);
  return `<div class="outcome-wrap">
    <div class="outcome-bar" title="Home ${h}% · Draw ${d}% · Away ${a}%">
      <span class="bar-home" style="width:${h}%"></span>
      <span class="bar-draw" style="width:${d}%"></span>
      <span class="bar-away" style="width:${a}%"></span>
    </div>
    <div class="outcome-legend">
      <span class="home">Home ${h}%</span>
      <span class="draw">Draw ${d}%</span>
      <span class="away">Away ${a}%</span>
    </div>
  </div>`;
}

export function confidenceBlock(pred) {
  if (!pred?.confidence_pct && !pred?.model_agreement) return "";
  const conf = pred.confidence_pct != null ? `${Math.round(pred.confidence_pct)}%` : "—";
  const data = pred.data_completeness_pct != null ? `${Math.round(pred.data_completeness_pct)}%` : "—";
  const agree = pred.model_agreement || "—";
  return `<div class="confidence-block">
    <div class="conf-row"><span>Confidence</span><strong>${conf}</strong></div>
    <div class="conf-row"><span>Data completeness</span><strong>${data}</strong></div>
    <div class="conf-row"><span>Model agreement</span><strong class="agree-${agree.toLowerCase()}">${agree}</strong></div>
  </div>`;
}

export function factorBreakdownData(pred) {
  if (!pred) return null;
  const fb = pred.factor_breakdown;
  if (fb?.factor_breakdown) return fb.factor_breakdown;
  if (fb && typeof fb === "object" && !Array.isArray(fb) && fb.recent_form == null && fb.confidence_pct == null) {
    return fb;
  }
  return null;
}

export function factorChartHtml(pred, canvasId) {
  const data = factorBreakdownData(pred);
  if (!data || !Object.keys(data).length) return "";
  return `<div class="section"><h3>Factor breakdown</h3>
    <canvas id="${canvasId}" height="160"></canvas></div>`;
}

export function renderFactorChart(canvasId, pred) {
  const el = document.getElementById(canvasId);
  if (!el || !window.Chart) return;
  const fb = factorBreakdownData(pred);
  if (!fb) return;
  const entries = Object.entries(fb).filter(([, v]) => typeof v === "number");
  if (!entries.length) return;
  new Chart(el, {
    type: "bar",
    data: {
      labels: entries.map(([k]) => k.replace(/_/g, " ")),
      datasets: [{
        data: entries.map(([, v]) => v),
        backgroundColor: "rgba(34, 197, 94, 0.65)",
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148,163,184,0.1)" } },
        y: { ticks: { color: "#cbd5e1" }, grid: { display: false } },
      },
    },
  });
}

export function matchCardHtml(match, { clickable = true, linkPrefix = "#/match" } = {}) {
  const live = isLive(match.status);
  const pred = match.prediction;
  const top = pred?.top_scorelines?.[0];
  const pickHome = Math.round(pred?.predicted_home_goals ?? top?.home ?? 0);
  const pickAway = Math.round(pred?.predicted_away_goals ?? top?.away ?? 0);
  const pickPct = top?.probability ?? 0;
  const hasScore = match.home_goals != null && match.away_goals != null;
  const center = hasScore ? `${match.home_goals}–${match.away_goals}` : `${pickHome}–${pickAway}`;

  const tag = live
    ? `<span class="badge badge-live">● LIVE</span>`
    : hasScore
      ? `<span class="badge badge-finished">FINAL</span>`
      : `<span class="badge badge-upcoming">UPCOMING</span>`;

  const pickRow = hasScore
    ? `<div class="pick-row"><span class="pick-label">FINAL</span></div>`
    : `<div class="pick-row">
        <span class="pick-label">PICK</span>
        ${pickPct > 0 ? `<span class="pick-conf">${(pickPct * 100).toFixed(0)}% likely</span>` : ""}
      </div>`;

  const teamCol = (name, meta, side) =>
    `<div class="team-col ${side}">
      ${teamBadgeHtml(name, meta)}
      <div class="team">${escapeHtml(name)}</div>
    </div>`;

  const inner = `<div class="card-meta">${tag}<span class="card-date">${formatDate(match.date)}</span></div>
    <div class="match-row">
      ${teamCol(match.home_team, match.home, "home")}
      <div class="score-block">
        <div class="score">${center}</div>
        ${pickRow}
      </div>
      ${teamCol(match.away_team, match.away, "away")}
    </div>
    ${outcomeBar(pred)}
    ${confidenceBlock(pred)}`;

  if (clickable) {
    return `<a href="${linkPrefix}/${match.id}" class="card card-link${live ? " live" : ""}">${inner}</a>`;
  }
  return `<article class="card${live ? " live" : ""}">${inner}</article>`;
}

export function statsHtml(stats) {
  return `<div class="stats">
    <div class="stat"><div class="stat-val">${stats.upcoming ?? 0}</div><div class="stat-lbl">Upcoming</div></div>
    <div class="stat"><div class="stat-val">${stats.live ?? 0}</div><div class="stat-lbl">Live</div></div>
    <div class="stat"><div class="stat-val">${stats.predictions ?? 0}</div><div class="stat-lbl">Picks</div></div>
    ${stats.teams != null ? `<div class="stat"><div class="stat-val">${stats.teams}</div><div class="stat-lbl">Teams</div></div>` : ""}
  </div>`;
}

export function section(title, body) {
  return `<div class="section"><h3>${escapeHtml(title)}</h3>${body}</div>`;
}

export function tableHtml(headers, rows) {
  return `<div class="table-wrap"><table class="data-table">
    <thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
    <tbody>${rows.join("")}</tbody>
  </table></div>`;
}

export function freshnessBarHtml(data) {
  if (!data?.warnings?.length) return "";
  const w = data.warnings[0];
  return `<div class="freshness-warn">⚠ ${escapeHtml(w.entity || "Data")}: ${Math.round(w.completeness_pct || 0)}% complete — some features use fallback priors.</div>`;
}

export function timelineHtml(events) {
  if (!events?.length) return `<p class="empty">No timeline events yet.</p>`;
  return `<ul class="timeline">${events
    .map(
      (e) => `<li class="timeline-item type-${(e.event_type || "").toLowerCase()}">
        <span class="tl-minute">${e.minute ?? "?"}'</span>
        <span class="tl-type">${escapeHtml(e.event_type || "")}</span>
        <span class="tl-player">${escapeHtml(e.player_name || "")}</span>
        <span class="tl-team">${escapeHtml(e.team || "")}</span>
        ${e.detail ? `<span class="tl-detail">${escapeHtml(e.detail)}</span>` : ""}
      </li>`
    )
    .join("")}</ul>`;
}

export function lineupsHtml(lineups) {
  if (!lineups?.length) return `<p class="empty">Lineups not available yet.</p>`;
  const byTeam = {};
  for (const l of lineups) {
    const key = l.team || "Unknown";
    if (!byTeam[key]) byTeam[key] = { xi: [], subs: [] };
    const row = `<li>${escapeHtml(l.player_name || "?")} <span class="pos">${escapeHtml(l.position || "")}</span></li>`;
    if (l.is_starter) byTeam[key].xi.push(row);
    else byTeam[key].subs.push(row);
  }
  return Object.entries(byTeam)
    .map(
      ([team, g]) => `<div class="lineup-block">
        <h4>${escapeHtml(team)}</h4>
        <p class="lineup-label">Starting XI</p><ul>${g.xi.join("") || "<li>—</li>"}</ul>
        ${g.subs.length ? `<p class="lineup-label">Subs</p><ul>${g.subs.join("")}</ul>` : ""}
      </div>`
    )
    .join("");
}

export function statsGridHtml(teamStats) {
  if (!teamStats?.length) return `<p class="empty">Match stats not available yet.</p>`;
  return `<div class="stats-grid">${teamStats
    .map(
      (s) => `<div class="stats-card">
        <h4>${escapeHtml(s.team || "")}</h4>
        <div class="stat-line"><span>Possession</span><strong>${s.possession ?? "—"}%</strong></div>
        <div class="stat-line"><span>Shots</span><strong>${s.shots ?? "—"}</strong></div>
        <div class="stat-line"><span>On target</span><strong>${s.shots_on_target ?? "—"}</strong></div>
        <div class="stat-line"><span>Corners</span><strong>${s.corners ?? "—"}</strong></div>
        <div class="stat-line"><span>Fouls</span><strong>${s.fouls ?? "—"}</strong></div>
      </div>`
    )
    .join("")}</div>`;
}

export function bracketHtml(nodes) {
  if (!nodes?.length) return `<p class="empty">Bracket will populate as knockout fixtures are synced.</p>`;
  const byStage = {};
  for (const n of nodes) {
    const stage = n.stage || n.round_name || "Knockout";
    if (!byStage[stage]) byStage[stage] = [];
    byStage[stage].push(n);
  }
  return `<div class="bracket-grid">${Object.entries(byStage)
    .map(
      ([stage, items]) => `<div class="bracket-col">
        <h4>${escapeHtml(stage)}</h4>
        ${items
          .map((n) => {
            const m = n.match;
            if (m) return matchCardHtml(m, { clickable: true });
            return `<div class="bracket-slot">${escapeHtml(n.slot || "TBD")}</div>`;
          })
          .join("")}
      </div>`
    )
    .join("")}</div>`;
}

export function simChartHtml(sim, canvasId) {
  if (!sim?.team_probabilities && !sim?.results) return "";
  return `<div class="section"><h3>Tournament simulation</h3>
    <canvas id="${canvasId}" height="220"></canvas></div>`;
}

export function liveProbChartHtml(canvasId) {
  return `<div class="section"><h3>Live win probability</h3>
    <canvas id="${canvasId}" height="180"></canvas></div>`;
}

export function renderLiveProbChart(canvasId, points) {
  const el = document.getElementById(canvasId);
  if (!el || !window.Chart || !points?.length) return;
  new Chart(el, {
    type: "line",
    data: {
      labels: points.map((p, i) => p.match_minute != null ? `${p.match_minute}'` : `#${i + 1}`),
      datasets: [
        {
          label: "Home",
          data: points.map((p) => (p.home_win_prob * 100).toFixed(1)),
          borderColor: "#38bdf8",
          tension: 0.25,
        },
        {
          label: "Draw",
          data: points.map((p) => (p.draw_prob * 100).toFixed(1)),
          borderColor: "#94a3b8",
          tension: 0.25,
        },
        {
          label: "Away",
          data: points.map((p) => (p.away_win_prob * 100).toFixed(1)),
          borderColor: "#a78bfa",
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        y: { min: 0, max: 100, ticks: { color: "#94a3b8", callback: (v) => v + "%" } },
        x: { ticks: { color: "#cbd5e1" } },
      },
    },
  });
}

export function renderSimChart(canvasId, sim) {
  const el = document.getElementById(canvasId);
  if (!el || !window.Chart || !sim) return;
  const probs = sim.team_probabilities || sim.results?.team_probabilities;
  if (!probs) return;
  const entries = Object.entries(probs)
    .sort((a, b) => (b[1].win ?? b[1]) - (a[1].win ?? a[1]))
    .slice(0, 12);
  new Chart(el, {
    type: "bar",
    data: {
      labels: entries.map(([t]) => t),
      datasets: [{
        label: "Win %",
        data: entries.map(([, v]) => ((v.win ?? v) * 100).toFixed(1)),
        backgroundColor: "rgba(251, 191, 36, 0.7)",
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: { ticks: { color: "#94a3b8", callback: (v) => v + "%" }, grid: { color: "rgba(148,163,184,0.1)" } },
        x: { ticks: { color: "#cbd5e1", maxRotation: 45 }, grid: { display: false } },
      },
    },
  });
}
