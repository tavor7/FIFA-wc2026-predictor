import { request } from "./api.js";
import { teamBadgeHtml, teamLinkHtml, escapeHtml, slugify } from "./flags.js";
import {
  disclaimerHtml, matchCardHtml, statsHtml, section, tableHtml,
  timelineHtml, lineupsHtml, statsGridHtml, bracketHtml,
  factorChartHtml, renderFactorChart, simChartHtml, renderSimChart,
  liveProbChartHtml, renderLiveProbChart,
  formatDate,
} from "./components.js";

export async function pageMatches() {
  const [matches, stats] = await Promise.all([
    request("/matches/upcoming"),
    request("/stats"),
  ]);
  return disclaimerHtml() + statsHtml(stats) +
    (matches.length
      ? matches.map((m) => matchCardHtml(m)).join("")
      : `<p class="empty">No matches yet. Click <strong>Sync data</strong> to load fixtures.</p>`);
}

export async function pageLive() {
  await request("/sync/live", { method: "POST" }).catch(() => null);
  const matches = await request("/matches/live");
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
  const data = await request(`/teams/${encodeURIComponent(slug)}`);
  const t = data.team;
  const form = data.form || {};
  const mom = data.momentum || {};

  const header = `<div class="page-header team-header">
    ${teamBadgeHtml(t.name, data, "lg")}
    <div>
      <h2>${escapeHtml(t.name)}</h2>
      <div class="badges-row">
        <span class="metric-badge">Momentum ${Math.round(mom.score ?? 0)}</span>
        ${form.form_last_5 != null ? `<span class="metric-badge">L5 form ${(form.form_last_5 * 100).toFixed(0)}%</span>` : ""}
        ${form.opponent_adjusted_form != null ? `<span class="metric-badge">Adj form ${(form.opponent_adjusted_form * 100).toFixed(0)}%</span>` : ""}
        ${form.source ? `<span class="metric-badge">${escapeHtml(form.source)}</span>` : ""}
        ${data.strength?.matches ? `<span class="metric-badge">${data.strength.matches} WC matches · atk ${data.strength.attack?.toFixed(2)}</span>` : ""}
      </div>
    </div>
  </div>`;

  const players = data.players || [];
  const injuries = data.injuries || [];

  const formSection = section("Recent form", `<div class="form-grid">
    <div class="form-card"><span>L5 form</span><strong>${form.form_last_5 != null ? (form.form_last_5 * 100).toFixed(0) + "%" : "—"}</strong></div>
    <div class="form-card"><span>L10 form</span><strong>${form.form_last_10 != null ? (form.form_last_10 * 100).toFixed(0) + "%" : "—"}</strong></div>
    <div class="form-card"><span>Goals L5</span><strong>${form.goals_scored_last_5 != null ? `${form.goals_scored_last_5}–${form.goals_conceded_last_5}` : "—"}</strong></div>
    <div class="form-card"><span>Clean sheets L5</span><strong>${form.clean_sheets_last_5 ?? "—"}</strong></div>
    <div class="form-card"><span>Home form</span><strong>${form.home_form != null ? (form.home_form * 100).toFixed(0) + "%" : "—"}</strong></div>
    <div class="form-card"><span>Away form</span><strong>${form.away_form != null ? (form.away_form * 100).toFixed(0) + "%" : "—"}</strong></div>
  </div>`);

  const squadRows = players
    .sort((a, b) => (b.rating || 0) - (a.rating || 0))
    .map(
      (p) => `<tr>
        <td>${escapeHtml(p.name || "?")}</td>
        <td>${escapeHtml(p.position || "—")}</td>
        <td>${p.rating != null ? p.rating.toFixed(1) : "—"}</td>
        <td>${p.form ?? "—"}</td>
        <td>${p.appearances ?? p.caps ?? "—"}</td>
        <td>${p.injured ? '<span class="badge badge-injury">Injured</span>' : ""}</td>
      </tr>`
    );

  const squadSection = section(
    "Squad",
    players.length
      ? tableHtml(["Player", "Pos", "Rating", "Form", "Apps", "Status"], squadRows)
      : `<p class="empty">Squad data not synced yet.</p>`
  );

  const injSection = injuries.length
    ? section("Injuries & suspensions", `<ul class="injury-list">${injuries
        .map((i) => `<li>${escapeHtml(i.player_name)} — ${escapeHtml(i.reason || i.injury_type || "Out")}</li>`)
        .join("")}</ul>`)
    : "";

  const hist = data.history;
  const histSection = hist && Object.keys(hist).length
    ? section("World Cup history", `<div class="form-grid">
        <div class="form-card"><span>Appearances</span><strong>${hist.appearances ?? "—"}</strong></div>
        <div class="form-card"><span>Best finish</span><strong>${escapeHtml(hist.best_finish || "—")}</strong></div>
        <div class="form-card"><span>Total WC goals</span><strong>${hist.total_goals ?? "—"}</strong></div>
      </div>`)
    : "";

  return disclaimerHtml(true) + header + formSection + squadSection + injSection + histSection;
}

export async function pageMatch(id) {
  const match = await request(`/matches/${id}`);
  const pred = match.prediction;
  const canvasId = `factor-${id}`;

  let html = disclaimerHtml(true) +
    `<div class="page-header"><a class="back-link" href="#/">← Back</a></div>` +
    matchCardHtml(match, { clickable: false });

  html += factorChartHtml(pred, canvasId);

  const liveProbId = `live-prob-${id}`;
  try {
    const livePts = await request(`/matches/${id}/live-probs`);
    if (livePts.length) {
      html += liveProbChartHtml(liveProbId);
    }
  } catch { /* optional */ }

  try {
    const hist = await request(`/matches/${id}/history`);
    if (hist.what_changed?.reason) {
      html += section("What changed", `<p>${escapeHtml(hist.what_changed.reason)}</p>`);
    }
  } catch { /* optional */ }

  if (pred?.explanation) {
    const alts = pred.top_scorelines?.slice(1, 5) ?? [];
    html += section("Why this pick?", `<p>${escapeHtml(pred.explanation)}</p>` +
      (alts.length
        ? `<div class="chips">${alts.map((s) =>
            `<span class="chip">${s.home}–${s.away} · ${(s.probability * 100).toFixed(0)}%</span>`
          ).join("")}</div>`
        : ""));
  }

  if (match.events?.length) {
    html += section("Timeline", timelineHtml(match.events));
  } else {
    const events = await request(`/matches/${id}/timeline`).catch(() => []);
    if (events.length) html += section("Timeline", timelineHtml(events));
  }

  html += section("Lineups", lineupsHtml(match.lineups));
  html += section("Match stats", statsGridHtml(match.team_stats));

  if (match.weather && Object.keys(match.weather).length) {
    const w = match.weather;
    html += section("Weather forecast", `<div class="form-grid">
      <div class="form-card"><span>Temp</span><strong>${w.temperature_c ?? "—"}°C</strong></div>
      <div class="form-card"><span>Humidity</span><strong>${w.humidity_pct ?? "—"}%</strong></div>
      <div class="form-card"><span>Wind</span><strong>${w.wind_kmh ?? "—"} km/h</strong></div>
      <div class="form-card"><span>Rain</span><strong>${w.precipitation_mm ?? "—"} mm</strong></div>
    </div>`);
  }

  if (match.referee_name) {
    html += section("Referee", `<p>${escapeHtml(match.referee_name)}</p>`);
  }

  if (match.injuries?.length) {
    html += section("Injuries", `<ul>${match.injuries.map((i) =>
      `<li>${escapeHtml(i.player_name)} (${escapeHtml(i.team)}) — ${escapeHtml(i.reason || "Out")}</li>`
    ).join("")}</ul>`);
  }

  setTimeout(() => {
    renderFactorChart(canvasId, pred);
    request(`/matches/${id}/live-probs`)
      .then((pts) => renderLiveProbChart(liveProbId, pts))
      .catch(() => null);
  }, 50);
  return html;
}

export async function pageTournament() {
  const data = await request("/tournament/overview");
  const groups = data.standings || {};
  const sim = data.simulation;

  let html = disclaimerHtml(true) + `<h2 class="page-title">Tournament overview</h2>`;

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
  const nodes = await request("/tournament/bracket");
  return disclaimerHtml(true) +
    `<h2 class="page-title">Knockout bracket</h2>` +
    bracketHtml(nodes);
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
    `<h2 class="page-title">Player leaders</h2>` +
    renderBoard("Top scorers", data.top_scorers, "goals") +
    renderBoard("Top assists", data.top_assists, "assists") +
    renderBoard("Top ratings", data.top_ratings, "rating");
}

export async function pageReports() {
  const [report, freshness] = await Promise.all([
    request("/reports/summary"),
    request("/meta/freshness").catch(() => null),
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
  return html;
}

export async function pageMonitor() {
  const [status, freshness] = await Promise.all([
    request("/monitor/status"),
    request("/meta/freshness").catch(() => null),
  ]);

  const jobs = (status.recent_jobs || []).map(
    (j) => `<tr>
      <td>${escapeHtml(j.job_name || j.job || "—")}</td>
      <td><span class="status-${(j.status || "").toLowerCase()}">${escapeHtml(j.status || "—")}</span></td>
      <td>${j.records_processed ?? j.records ?? "—"}</td>
      <td>${formatDate(j.finished_at || j.started_at || "")}</td>
    </tr>`
  );

  const entities = (freshness?.entities || []).slice(0, 8).map(
    (e) => `<tr>
      <td>${escapeHtml(e.entity || "—")}</td>
      <td>${Math.round(e.completeness_pct || 0)}%</td>
      <td>${escapeHtml(e.source || "—")}</td>
      <td>${formatDate(e.last_updated || "")}</td>
    </tr>`
  );

  return disclaimerHtml(true) +
    `<h2 class="page-title">System monitor</h2>` +
    section("Health", `<div class="form-grid">
      <div class="form-card"><span>Database</span><strong>${escapeHtml(status.database || "—")}</strong></div>
      <div class="form-card"><span>Status</span><strong class="status-ok">${escapeHtml(status.health || "ok")}</strong></div>
      <div class="form-card"><span>Ensemble</span><strong>${status.models?.ensemble ? "Active" : "—"}</strong></div>
      <div class="form-card"><span>Elo</span><strong>${status.models?.elo ? "Active" : "—"}</strong></div>
    </div>`) +
    section("Stats", statsHtml(status.stats || {})) +
    section("Recent sync jobs", tableHtml(["Job", "Status", "Records", "Finished"], jobs.length ? jobs : [`<tr><td colspan="4">No jobs logged yet</td></tr>`])) +
    section("Data freshness", tableHtml(["Entity", "Complete", "Source", "Updated"], entities.length ? entities : [`<tr><td colspan="4">No freshness data</td></tr>`]));
}
