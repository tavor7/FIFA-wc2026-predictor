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
    <div class="outcome-label">Outcome probabilities</div>
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
  if (!pred?.confidence_pct && !pred?.model_agreement && !pred?.generated_at) return "";
  const conf = pred.confidence_pct != null ? `${Math.round(pred.confidence_pct)}%` : "—";
  const data = pred.data_completeness_pct != null ? `${Math.round(pred.data_completeness_pct)}%` : "—";
  const agree = pred.model_agreement || "—";
  const updated = pred.generated_at
    ? `<div class="conf-row"><span>Last prediction update</span><strong>${formatDateIsrael(pred.generated_at)}</strong></div>`
    : "";
  const stale = pred.staleness_warnings?.length
    ? `<div class="freshness-warn">${escapeHtml(pred.staleness_warnings[0])}</div>`
    : "";
  return `<div class="confidence-block">
    ${updated}
    <div class="conf-row"><span>Prediction confidence</span><strong>${conf}</strong></div>
    <div class="conf-row"><span>Data completeness</span><strong>${data}</strong></div>
    ${agree !== "—" ? `<div class="conf-row"><span>Model agreement</span><strong class="agree-${String(agree).toLowerCase()}">${agree}</strong></div>` : ""}
    ${stale}
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

export function featureContributionsChartHtml(pred, canvasId) {
  const c = pred?.feature_contributions;
  if (!c || !Object.keys(c).length) return "";
  return `<div class="section"><h3>Main drivers (feature contributions)</h3>
    <canvas id="${canvasId}" height="180"></canvas></div>`;
}

export function renderFeatureContributionsChart(canvasId, pred) {
  const el = document.getElementById(canvasId);
  if (!el || !window.Chart) return;
  const c = pred?.feature_contributions;
  if (!c) return;
  const entries = Object.entries(c).filter(([, v]) => typeof v === "number");
  if (!entries.length) return;
  new Chart(el, {
    type: "bar",
    data: {
      labels: entries.map(([k]) => k.replace(/_/g, " ")),
      datasets: [{
        data: entries.map(([, v]) => v),
        backgroundColor: entries.map(([, v]) =>
          v >= 0 ? "rgba(34, 197, 94, 0.65)" : "rgba(248, 113, 113, 0.65)"
        ),
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

export function predictionSourceBadge(pred) {
  if (!pred) return "";
  if (pred.is_placeholder) {
    return `<span class="source-badge source-pending">Prediction pending</span>`;
  }
  const mode = pred.prediction_source_mode || "";
  const labels = {
    full_model: "Full model",
    ensemble_without_xgb: "Ensemble",
    heuristic_plus_elo: "Heuristic + Elo",
    insufficient_data: "Limited data",
    baseline_only: "Baseline estimate",
    pending: "Pending",
  };
  const label = labels[mode] || (mode ? mode.replace(/_/g, " ") : "Unknown");
  let cls = "source-badge";
  if (mode === "full_model" || mode === "ensemble_without_xgb") cls += " source-strong";
  else if (mode === "baseline_only" || mode === "insufficient_data") cls += " source-weak";
  return `<span class="${cls}">${escapeHtml(label)}</span>`;
}

export function matchCardHtml(match, { clickable = true, linkPrefix = "#/match" } = {}) {
  const live = isLive(match.status);
  const pred = match.prediction;
  const isPlaceholder = !!pred?.is_placeholder;
  const top = pred?.top_scorelines?.[0];
  const pickHome = top?.home ?? Math.round(Number(pred?.predicted_home_goals ?? 0));
  const pickAway = top?.away ?? Math.round(Number(pred?.predicted_away_goals ?? 0));
  const pickPct = top?.probability ?? 0;
  const hasScore = match.home_goals != null && match.away_goals != null;
  const center = hasScore ? `${match.home_goals}–${match.away_goals}` : `${pickHome}–${pickAway}`;

  const tag = live
    ? `<span class="badge badge-live">● LIVE</span>`
    : hasScore
      ? `<span class="badge badge-finished">FINAL</span>`
      : `<span class="badge badge-upcoming">UPCOMING</span>`;

  const sourceBadge = predictionSourceBadge(pred);

  const pickRow = hasScore
    ? `<div class="pick-row"><span class="pick-label">FINAL</span></div>`
    : isPlaceholder
      ? `<div class="pick-row">
          <span class="pick-label">Research pick</span>
          <span class="pick-conf muted">Not generated yet</span>
          ${sourceBadge}
        </div>`
      : `<div class="pick-row">
          <span class="pick-label">Most likely scoreline</span>
          <span class="pick-conf">${pickHome}–${pickAway}${pickPct > 0 ? ` <span class="muted">(${(pickPct * 100).toFixed(0)}% exact score)</span>` : ""}</span>
          ${sourceBadge}
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
        <div class="score">${hasScore || !isPlaceholder ? center : "—"}</div>
        ${pickRow}
      </div>
      ${teamCol(match.away_team, match.away, "away")}
    </div>
    ${isPlaceholder ? "" : outcomeBar(pred)}
    ${isPlaceholder ? "" : confidenceBlock(pred)}`;

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

export function skeletonCardsHtml(n = 4) {
  return Array.from({ length: n }, () =>
    `<article class="card skeleton-card">
      <div class="sk-line sk-w60"></div>
      <div class="sk-row"><div class="sk-block"></div><div class="sk-score"></div><div class="sk-block"></div></div>
      <div class="sk-line sk-w100"></div>
    </article>`
  ).join("");
}

export function dataFreshnessBadge(lastUpdated, meta = {}) {
  if (!lastUpdated && !meta.dataVersion) return "";
  const ts = lastUpdated ? formatDateIsrael(lastUpdated) : "—";
  const badge = meta.stale ? "stale" : "fresh";
  return `<div class="data-freshness-badge badge-${badge}">
    <span class="freshness-dot" aria-hidden="true"></span>
    <span>Updated ${escapeHtml(ts)}</span>
    ${meta.responseTimeMs ? `<span class="freshness-meta">${escapeHtml(String(meta.responseTimeMs))}ms</span>` : ""}
    ${meta.cache ? `<span class="cache-tag">${escapeHtml(meta.cache)}</span>` : ""}
  </div>`;
}

export function pageHeaderHtml(title, subtitle = "") {
  return `<header class="page-header-block">
    <h2 class="page-title">${escapeHtml(title)}</h2>
    ${subtitle ? `<p class="page-subtitle">${escapeHtml(subtitle)}</p>` : ""}
  </header>`;
}

export function metricCard(label, value, status = "") {
  const statusClass = status ? ` metric-${status}` : "";
  return `<div class="metric-card${statusClass}">
    <span class="metric-label">${escapeHtml(label)}</span>
    <strong class="metric-value">${escapeHtml(String(value))}</strong>
  </div>`;
}

export function latencyStatus(ms) {
  if (ms == null || ms === "—") return "";
  const n = Number(ms);
  if (Number.isNaN(n)) return "";
  if (n < 150) return "ok";
  if (n < 400) return "warn";
  return "bad";
}

export function setMonitorControlsLocked(locked) {
  const panel = document.querySelector(".admin-panel");
  if (!panel) return;
  panel.classList.toggle("admin-locked", locked);
  panel.querySelectorAll("button").forEach((btn) => {
    if (btn.id === "btn-pipeline-cancel" || btn.id === "btn-admin-logout") {
      btn.disabled = false;
      return;
    }
    btn.disabled = locked;
  });
}

export function adminPanelHtml() {
  return `<div class="admin-panel">
    <div class="admin-panel-head">
      <div>
        <h3 class="admin-panel-title">Pipeline controls</h3>
        <p class="admin-panel-hint">Admin only · normal browsing uses fast read-only endpoints</p>
      </div>
      <button class="btn-ghost btn-admin-logout" type="button" id="btn-admin-logout">Sign out</button>
    </div>
    <div class="admin-panel-body">
      <button class="btn-primary btn-pipeline-main" type="button" data-pipeline-mode="full_pipeline">
        Run full pipeline
      </button>
      <div class="btn-row">
        <button class="btn-secondary" type="button" data-pipeline-mode="data_sync_only">Sync data</button>
        <button class="btn-secondary" type="button" data-pipeline-mode="predictions_only">Predictions</button>
        <button class="btn-secondary" type="button" id="btn-admin-retrain">Retrain models</button>
        <button class="btn-ghost" type="button" id="btn-admin-predict">Refresh predictions</button>
        <button class="btn-ghost" type="button" id="btn-admin-players">Reload Kaggle squads</button>
        <button class="btn-ghost" type="button" id="btn-repair-predictions">Repair missing predictions</button>
      </div>
    </div>
  </div>`;
}

function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem ? `${m}m ${rem}s` : `${m}m`;
}

export function progressBarHtml(id = "pipeline-progress", options = {}) {
  const {
    phaseLabel = "Starting pipeline…",
    showCancel = id === "pipeline-progress",
  } = options;
  const cancelBtn = showCancel
    ? `<button type="button" id="btn-pipeline-cancel" class="btn-ghost btn-pipeline-cancel hidden" aria-label="Cancel pipeline run">Cancel</button>`
    : "";
  return `<div id="${id}" class="progress-panel hidden" role="status" aria-live="polite">
    <div class="progress-header">
      <span class="progress-phase">${phaseLabel}</span>
      <div class="progress-header-actions">
        <span class="progress-pct">0%</span>
        ${cancelBtn}
      </div>
    </div>
    <div class="progress-track"><div class="progress-fill" style="width:0%"></div></div>
    <div class="progress-meta">
      <span class="progress-steps">Step 1 of 10</span>
      <span class="progress-timing">Calculating…</span>
    </div>
    <p class="progress-detail">Preparing…</p>
  </div>`;
}

export function updateProgressBar(panelId, progress) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  const cancelBtn = panel.querySelector("#btn-pipeline-cancel");
  if (!progress?.running) {
    if (progress?.cancelled) {
      panel.classList.remove("hidden", "progress-cancelling");
      panel.classList.add("progress-cancelled");
      panel.querySelector(".progress-fill").style.width = `${Math.round(progress.overall_progress_pct || 0)}%`;
      panel.querySelector(".progress-pct").textContent = "Stopped";
      panel.querySelector(".progress-phase").textContent = "Pipeline cancelled";
      panel.querySelector(".progress-steps").textContent = "Run stopped by user";
      panel.querySelector(".progress-timing").textContent = progress.elapsed_seconds
        ? `${formatDuration(progress.elapsed_seconds)} elapsed`
        : "";
      panel.querySelector(".progress-detail").textContent =
        progress.message || "Cancelled after the current step finished.";
      if (cancelBtn) cancelBtn.classList.add("hidden");
      setMonitorControlsLocked(false);
      return;
    }
    if (progress?.overall_progress_pct >= 100) {
      panel.classList.remove("hidden", "progress-cancelling", "progress-cancelled");
      panel.querySelector(".progress-fill").style.width = "100%";
      panel.querySelector(".progress-pct").textContent = "100%";
      const isTraining = progress.mode_label === "Model training";
      panel.querySelector(".progress-phase").textContent = isTraining ? "Training complete" : "Complete";
      panel.querySelector(".progress-steps").textContent = isTraining
        ? (progress.model_version ? `Model ${progress.model_version}` : "All training steps finished")
        : "All steps finished";
      panel.querySelector(".progress-timing").textContent = progress.elapsed_seconds
        ? `${formatDuration(progress.elapsed_seconds)} total`
        : "";
      panel.querySelector(".progress-detail").textContent = isTraining
        ? (progress.message || "Reloading monitor…")
        : "Refreshing page…";
      if (cancelBtn) cancelBtn.classList.add("hidden");
      setMonitorControlsLocked(false);
      return;
    }
    if (progress?.failed) {
      panel.classList.remove("hidden", "progress-cancelling");
      panel.classList.add("progress-cancelled");
      panel.querySelector(".progress-fill").style.width = `${Math.round(progress.overall_progress_pct || 0)}%`;
      panel.querySelector(".progress-pct").textContent = "Failed";
      panel.querySelector(".progress-phase").textContent =
        progress.mode_label === "Model training" ? "Training failed" : "Pipeline failed";
      panel.querySelector(".progress-steps").textContent = progress.step_label || "Error";
      panel.querySelector(".progress-timing").textContent = progress.elapsed_seconds
        ? `${formatDuration(progress.elapsed_seconds)} elapsed`
        : "";
      panel.querySelector(".progress-detail").textContent = progress.error || progress.message || "Unknown error";
      if (cancelBtn) cancelBtn.classList.add("hidden");
      setMonitorControlsLocked(false);
      return;
    }
    panel.classList.add("hidden");
    panel.classList.remove("progress-cancelling", "progress-cancelled");
    if (cancelBtn) cancelBtn.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden", "progress-cancelled");
  setMonitorControlsLocked(true);
  if (progress.cancel_requested) {
    panel.classList.add("progress-cancelling");
  } else {
    panel.classList.remove("progress-cancelling");
  }
  if (cancelBtn) {
    const showCancel = progress.cancellable && !progress.cancel_requested;
    cancelBtn.classList.toggle("hidden", !showCancel);
    cancelBtn.disabled = !!progress.cancel_requested;
    cancelBtn.textContent = progress.cancel_requested ? "Cancelling…" : "Cancel";
  }
  const pct = Math.round(progress.overall_progress_pct || 2);
  const stepPct = Math.round(progress.step_progress_pct || 0);
  panel.querySelector(".progress-fill").style.width = `${pct}%`;
  panel.querySelector(".progress-pct").textContent = `${pct}%`;

  const mode = progress.mode_label || "Pipeline";
  const phase = progress.phase_label || progress.step_label || "Running";
  panel.querySelector(".progress-phase").textContent = `${mode} · ${phase}`;

  const stepNum = progress.step_number ?? 1;
  const stepsTotal = progress.steps_total ?? progress.total_steps ?? 10;
  const phaseStep = progress.phase_step_number ?? 1;
  const phaseTotal = progress.phase_steps_total ?? 1;
  const taskLabel = progress.step_label || phase;
  panel.querySelector(".progress-steps").textContent =
    `Step ${stepNum} of ${stepsTotal} · ${taskLabel} (${phaseStep}/${phaseTotal} in phase)` +
    (stepPct > 0 && stepPct < 100 ? ` · ${stepPct}%` : "");

  const timingParts = [];
  const remaining = progress.estimated_remaining_seconds;
  const isTraining = progress.mode_label === "Model training";
  if (isTraining) {
    if (progress.timing_hint) {
      timingParts.push(progress.timing_hint);
    }
  } else if (remaining != null && remaining > 0) {
    timingParts.push(`~${formatDuration(remaining)} left`);
  } else if (pct > 2 && pct < 99) {
    timingParts.push("estimating…");
  }
  if (progress.elapsed_seconds) {
    timingParts.push(`${formatDuration(progress.elapsed_seconds)} elapsed`);
  }
  panel.querySelector(".progress-timing").textContent = timingParts.join(" · ") || "";

  const detail = (progress.message || "").replace(/…\s*\d+s\s*$/, "…").trim();
  panel.querySelector(".progress-detail").textContent = detail || taskLabel;
}

export function freshnessBarHtml(data, pageMeta = {}) {
  const parts = [];
  if (pageMeta.lastUpdated && pageMeta.showTimestamp !== false) {
    parts.push(dataFreshnessBadge(pageMeta.lastUpdated, pageMeta));
  }
  if (data?.warnings?.length) {
    const w = data.warnings[0];
    parts.push(`<div class="freshness-warn">⚠ ${escapeHtml(w.entity || "Data")}: ${Math.round(w.completeness_pct || 0)}% complete — some features use fallback priors.</div>`);
  }
  return parts.join("");
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
