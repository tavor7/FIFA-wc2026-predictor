import { request } from "./api.js";
import { teamBadgeHtml, teamLinkHtml, escapeHtml, slugify } from "./flags.js";
import { renderKnockoutBracket } from "./knockout-bracket.js";
import {
  disclaimerHtml, matchCardHtml, statsHtml, section, tableHtml,
  timelineHtml, lineupsHtml, statsGridHtml,
  factorChartHtml, renderFactorChart,
  featureContributionsChartHtml, renderFeatureContributionsChart,
  simChartHtml, renderSimChart,
  liveProbChartHtml, renderLiveProbChart,
  progressBarHtml, dataFreshnessBadge, pageHeaderHtml, metricCard, latencyStatus, adminPanelHtml,
  formatDate,
  formatDateIsrael,
  formatPct,
  formatAvg,
} from "./components.js";
import { resolveMonitorPage } from "./monitor.js";

function regionalBadge(form) {
  const boost = formatPct(form.regional_boost ?? form.host_region_boost);
  if (form.regional_advantage === "co_host") {
    return `<span class="metric-badge">2026 co-host · +${boost} boost</span>`;
  }
  if (form.regional_advantage === "south_america") {
    return `<span class="metric-badge">South America · +${boost} boost</span>`;
  }
  return "";
}

function regionalVenueCard(form) {
  const boost = formatPct(form.regional_boost ?? form.host_region_boost);
  if (form.regional_advantage === "co_host") {
    return `<div class="form-card"><span>2026 co-host</span><strong>+${boost} region</strong></div>`;
  }
  if (form.regional_advantage === "south_america") {
    return `<div class="form-card"><span>South America</span><strong>+${boost} Americas</strong></div>`;
  }
  return `<div class="form-card"><span>Venue</span><strong>Neutral site</strong></div>`;
}

export async function pageMatches() {
  const data = await request("/home-lite");
  window.setPageMeta?.({ lastUpdated: data.last_updated || data.last_prediction_update });
  const stats = data.stats || {};
  const matches = data.matches || [];
  const live = data.live || [];
  let html = disclaimerHtml() + statsHtml(stats);
  if (live.length) {
    html += section("Live now", live.map((m) => matchCardHtml(m)).join(""));
  }
  html += matches.length
    ? matches.map((m) => matchCardHtml(m)).join("")
    : `<p class="empty">No matches loaded yet. Open <a href="#/monitor">Monitor</a> (admin) to refresh predictions.</p>`;
  return html;
}

export async function pageLive() {
  const data = await request("/home-lite");
  const matches = data.live || [];
  return disclaimerHtml() +
    (matches.length
      ? matches.map((m) => matchCardHtml(m)).join("")
      : `<p class="empty">No live matches right now.</p>`);
}

export async function pageResults() {
  const matches = await request("/matches/recent");
  return disclaimerHtml() +
    (matches.length
      ? matches.map((m) => matchCardHtml(m)).join("")
      : `<p class="empty">No results yet.</p>`);
}

export async function pageTeam(slug) {
  const data = await request(`/teams-lite/${encodeURIComponent(slug)}`);
  const t = data.team;
  const players = data.players || [];
  const injuries = data.injuries || [];

  const header = `<div class="page-header team-header">
    ${teamBadgeHtml(t.name, data, "lg")}
    <div>
      <h2>${escapeHtml(t.name)}</h2>
      <div class="badges-row">
        <span class="metric-badge">${data.squad_count ?? players.length} squad players</span>
      </div>
    </div>
  </div>`;

  const squadRows = players.map(
    (p) => `<tr>
      <td>${escapeHtml(p.name || "?")}</td>
      <td>${escapeHtml(p.position || "—")}</td>
      <td>${p.rating != null ? Math.round(p.rating) : "—"}</td>
      <td>${p.injured ? "Injured" : "OK"}</td>
    </tr>`
  );

  const squadSection = section(
    "Squad (top players)",
    players.length
      ? tableHtml(["Player", "Pos", "OVR", "Status"], squadRows)
      : `<p class="empty">Squad not loaded — refresh from Monitor (admin).</p>`
  );

  const injSection = injuries.length
    ? section("Injuries", `<ul class="injury-list">${injuries
        .map((i) => `<li>${escapeHtml(i.player_name)} — ${escapeHtml(i.reason || i.injury_type || "Out")}</li>`)
        .join("")}</ul>`)
    : "";

  return disclaimerHtml(true) + header + squadSection + injSection;
}

export async function pageMatch(id) {
  const match = await request(`/match-lite/${id}`);
  const pred = match.prediction;

  let html = disclaimerHtml(true) +
    `<div class="page-header"><a class="back-link" href="#/">← Back</a></div>` +
    matchCardHtml(match, { clickable: false });

  if (pred) {
    const alts = (pred.top_scorelines || []).slice(0, 3);
    html += section("Explanation", `
      ${pred.baseline_notice ? `<p class="prob-note">${escapeHtml(pred.baseline_notice)}</p>` : ""}
      <p>${escapeHtml(pred.explanation || "No explanation stored yet.")}</p>
      ${alts.length ? `<p class="section-note">Top scorelines (exact-score probability — not outcome confidence):</p>
        <div class="chips">${alts.map((s) =>
          `<span class="chip">${s.home}–${s.away} · ${(s.probability * 100).toFixed(0)}%</span>`
        ).join("")}</div>` : ""}
      <div class="form-grid">
        <div class="form-card"><span>Source</span><strong>${escapeHtml((pred.prediction_source_mode || "—").replace(/_/g, " "))}</strong></div>
        <div class="form-card"><span>Prediction confidence</span><strong>${pred.confidence_pct != null ? `${Math.round(pred.confidence_pct)}%` : "—"}</strong></div>
        ${pred.generated_at ? `<div class="form-card"><span>Last update</span><strong>${formatDateIsrael(pred.generated_at)}</strong></div>` : ""}
      </div>`);
  }

  if (match.injuries?.length) {
    html += section("Injuries", `<ul>${match.injuries.map((i) =>
      `<li>${escapeHtml(i.player_name)} (${escapeHtml(i.team || "")}) — ${escapeHtml(i.reason || "Out")}</li>`
    ).join("")}</ul>`);
  }

  if (match.lineups?.length) {
    html += section("Lineups", lineupsHtml(match.lineups));
  }

  if (match.team_stats?.length) {
    html += section("Match stats", statsGridHtml(match.team_stats));
  }

  return html;
}

export async function pageTournament() {
  const data = await request("/tournament/overview");
  const groups = data.standings || {};
  const sim = data.simulation;

  let html = disclaimerHtml(true) +
    `<h2 class="page-title">Group stage standings</h2>
    <div class="page-intro">Who leads each group (top 2 + 8 best 3rd places advance).
    For the full <strong>fixture list</strong> and knockout rounds (once scheduled), open
    <a href="#/bracket">Schedule</a>.</div>`;

  const groupKeys = Object.keys(groups).sort();
  if (groupKeys.length) {
    for (const g of groupKeys) {
      const rows = (groups[g] || []).map(
        (s) => `<tr>
          <td>${teamLinkHtml(s.team_name || s.team, { slug: slugify(s.team_name || s.team) })}</td>
          <td>${s.played ?? 0}</td><td>${s.wins ?? 0}</td><td>${s.draws ?? 0}</td><td>${s.losses ?? 0}</td>
          <td>${s.goals_for ?? 0}</td><td>${s.goals_against ?? 0}</td><td><strong>${s.points ?? 0}</strong></td>
        </tr>`
      );
      html += section(`Group ${escapeHtml(g)}`, tableHtml(
        ["Team", "P", "W", "D", "L", "GF", "GA", "Pts"], rows
      ));
    }
  } else {
    html += `<p class="empty">Standings will appear after group-stage results are synced.</p>`;
  }

  if (data.upcoming?.length) {
    html += section("Upcoming", data.upcoming.slice(0, 10).map((m) => matchCardHtml(m)).join(""));
  }

  const simId = "sim-chart";
  html += simChartHtml(sim, simId);
  setTimeout(() => renderSimChart(simId, sim), 50);
  return html;
}

export async function pageBracket() {
  const data = await request("/tournament/knockout-bracket");
  const subtitle = data.has_knockout ? "Knockout stage" : "Group stage fixtures";
  return disclaimerHtml(true) +
    `<h2 class="page-title">${escapeHtml(data.title || "World Cup 2026")}</h2>
    <p class="page-intro">${escapeHtml(subtitle)}</p>` +
    renderKnockoutBracket(data);
}

export async function pagePlayers() {
  const data = await request("/players/leaders");
  const renderBoard = (title, rows, metric) => {
    if (!rows?.length) return section(title, `<p class="empty">No ${title.toLowerCase()} data yet.</p>`);
    const trs = rows.map(
      (p, i) => `<tr>
        <td>${i + 1}</td>
        <td>${escapeHtml(p.player_name || "?")}</td>
        <td>${teamLinkHtml(p.team, { slug: slugify(p.team) })}</td>
        <td><strong>${metric === "rating" ? (p.rating?.toFixed?.(1) ?? p.rating) : p[metric] ?? 0}</strong></td>
      </tr>`
    );
    return section(title, tableHtml(["#", "Player", "Team", metric === "rating" ? "Avg rating" : metric], trs));
  };

  return disclaimerHtml(true) +
    `<h2 class="page-title">Player leaders</h2>
    <p class="page-intro">Squad ratings from <strong>Kaggle FC 26</strong> (<a href="https://www.kaggle.com/datasets/rovnez/fc-26-fifa-26-player-data" target="_blank" rel="noopener">rovnez dataset</a>). Goals and assists fill in during the World Cup from live match sync.</p>` +
    renderBoard("Top scorers", data.top_scorers, "goals") +
    renderBoard("Top assists", data.top_assists, "assists") +
    renderBoard(data.ratings_source === "fc26" ? "Top squad ratings (FC26)" : "Top ratings", data.top_ratings, "rating");
}

export async function pageReports() {
  const [report, freshness, calibration, backtest] = await Promise.all([
    request("/reports/summary"),
    request("/meta/freshness").catch(() => null),
    request("/evaluation/calibration").catch(() => null),
    request("/evaluation/backtest/latest").catch(() => null),
  ]);

  const momHigh = (report.most_momentum || []).map(
    (t) => `<li>${teamLinkHtml(t.team, { slug: slugify(t.team) })} — ${Math.round(t.momentum)}</li>`
  ).join("");
  const momLow = (report.least_momentum || []).map(
    (t) => `<li>${teamLinkHtml(t.team, { slug: slugify(t.team) })} — ${Math.round(t.momentum)}</li>`
  ).join("");

  let html = disclaimerHtml(true) +
    `<h2 class="page-title">Research reports</h2>` +
    section("Summary", `<div class="form-grid">
      <div class="form-card"><span>Predictions</span><strong>${report.prediction_count ?? 0}</strong></div>
      <div class="form-card"><span>Upcoming matches</span><strong>${report.upcoming_count ?? 0}</strong></div>
    </div>`) +
    section("Highest momentum", `<ul class="rank-list">${momHigh || "<li>—</li>"}</ul>`) +
    section("Lowest momentum", `<ul class="rank-list">${momLow || "<li>—</li>"}</ul>`);

  if (freshness?.warnings?.length) {
    html += section("Data gaps", `<ul>${freshness.warnings.map((w) =>
      `<li>${escapeHtml(w.entity)}: ${Math.round(w.completeness_pct || 0)}% complete (${escapeHtml(w.source || "")})</li>`
    ).join("")}</ul>`);
  }

  if (calibration?.samples) {
    const calId = "calibration-curve-chart";
    html += section("Calibration (stored predictions)", `<div class="form-grid">
      <div class="form-card"><span>Samples</span><strong>${calibration.samples}</strong></div>
      <div class="form-card"><span>Brier score</span><strong>${calibration.brier_score ?? "—"}</strong></div>
      <div class="form-card"><span>Log loss</span><strong>${calibration.log_loss ?? "—"}</strong></div>
      <div class="form-card"><span>ECE (home win)</span><strong>${calibration.ece_home_win ?? "—"}</strong></div>
    </div>
    ${calibration.calibration_curve?.length ? `<canvas id="${calId}" height="200"></canvas>` : ""}`);
    if (calibration.calibration_curve?.length) {
      setTimeout(() => {
        const el = document.getElementById(calId);
        if (!el || !window.Chart) return;
        const curve = calibration.calibration_curve;
        new Chart(el, {
          type: "line",
          data: {
            labels: curve.map((b) => b.bin),
            datasets: [
              { label: "Predicted", data: curve.map((b) => b.mean_predicted), borderColor: "#22c55e", tension: 0.2 },
              { label: "Observed", data: curve.map((b) => b.mean_observed), borderColor: "#94a3b8", borderDash: [4, 4], tension: 0.2 },
            ],
          },
          options: { responsive: true, plugins: { legend: { labels: { color: "#cbd5e1" } } } },
        });
      }, 50);
    }
  }

  if (backtest?.matches) {
    html += section("Backtest (walk-forward)", `<div class="form-grid">
      <div class="form-card"><span>Matches</span><strong>${backtest.matches}</strong></div>
      <div class="form-card"><span>Outcome accuracy</span><strong>${((backtest.outcome_accuracy || 0) * 100).toFixed(1)}%</strong></div>
      <div class="form-card"><span>Exact score</span><strong>${((backtest.exact_score_accuracy || 0) * 100).toFixed(1)}%</strong></div>
      <div class="form-card"><span>Top-3 scoreline</span><strong>${((backtest.top3_scoreline_accuracy || 0) * 100).toFixed(1)}%</strong></div>
    </div>`);
  }
  return html;
}

export async function pageMonitor(path = "/monitor", search = "") {
  return resolveMonitorPage(path, search);
}
