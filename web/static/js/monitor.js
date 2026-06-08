import { request } from "./api.js";
import {
  adminPanelHtml,
  pageHeaderHtml,
  progressBarHtml,
  section,
  metricCard,
  formatDateIsrael,
} from "./components.js";
import { escapeHtml } from "./flags.js";

const MODE_LABELS = {
  full_model: "Full model",
  ensemble_without_xgb: "Ensemble (no XGB)",
  heuristic_plus_elo: "Heuristic + Elo",
  insufficient_data: "Insufficient data",
  baseline_only: "Baseline only",
  unknown: "Unknown",
};

const WEIGHT_LABELS = {
  elo: "Elo ratings",
  poisson_rf: "Poisson + RF",
  poisson_heuristic: "Heuristic Poisson",
  xgboost: "XGBoost",
};

function fmtPct(v) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${Math.round(v)}%`;
}

function gapClass(level) {
  if (level === "bad") return "monitor-gap bad";
  if (level === "warn") return "monitor-gap warn";
  if (level === "ok") return "monitor-gap ok";
  return "monitor-gap";
}

function diagnosticsHtml(d) {
  if (!d) return "";

  const data = d.data || {};
  const pred = d.predictions || {};
  const model = d.model || {};
  const cache = d.cache || {};
  const pipeline = d.pipeline || {};

  const modeEntries = Object.entries(pred.modes || {}).filter(([, n]) => n > 0);
  const modesHtml = modeEntries.length
    ? `<div class="chips">${modeEntries
        .map(([k, n]) => `<span class="chip">${escapeHtml(MODE_LABELS[k] || k)}: ${n}</span>`)
        .join("")}</div>`
    : `<p class="empty-inline">No predictions stored yet.</p>`;

  const weights = model.weights || {};
  const weightsHtml = Object.keys(weights).length
    ? `<table class="monitor-table"><thead><tr><th>Component</th><th>Weight</th></tr></thead><tbody>${Object.entries(weights)
        .map(
          ([k, v]) =>
            `<tr><td>${escapeHtml(WEIGHT_LABELS[k] || k)}</td><td>${(Number(v) * 100).toFixed(1)}%</td></tr>`
        )
        .join("")}</tbody></table>`
    : `<p class="empty-inline">No trained weights — using defaults until model retrain.</p>`;

  const freshnessRows = (d.freshness || []).map((f) => {
    const stale = (d.staleness_warnings || []).some((w) =>
      w.toLowerCase().includes((f.entity || "").replace("_", " "))
    );
    return `<tr>
      <td>${escapeHtml(f.entity || "—")}</td>
      <td>${f.last_updated ? formatDateIsrael(f.last_updated) : "Never"}</td>
      <td>${f.completeness_pct != null ? fmtPct(f.completeness_pct) : "—"}</td>
      <td>${escapeHtml(f.source || "—")}</td>
      <td class="${stale ? "text-warn" : "text-ok"}">${stale ? "Stale" : "OK"}</td>
    </tr>`;
  }).join("");

  const gapsHtml = (d.gaps || [])
    .map((g) => `<li class="${gapClass(g.level)}">${escapeHtml(g.text)}</li>`)
    .join("");

  return (
    section(
      "What's missing",
      gapsHtml
        ? `<ul class="monitor-gaps">${gapsHtml}</ul>`
        : `<p class="empty-inline">No gaps detected.</p>`
    ) +
    section(
      "Data inventory",
      `<div class="metric-grid">
        ${metricCard("Teams", data.teams ?? 0)}
        ${metricCard("Players (all)", data.players_total ?? 0)}
        ${metricCard("Kaggle FC26", data.fc26_players ?? 0)}
        ${metricCard("Injuries", data.injuries ?? 0, (data.injuries ?? 0) === 0 ? "warn" : "ok")}
        ${metricCard("Thin squads", data.thin_squad_teams ?? 0, data.thin_squad_teams ? "warn" : "ok")}
        ${metricCard("Squad target", data.squad_target ?? 30)}
      </div>
      <p class="section-note">Kaggle reload needed: ${data.fc26_reimport_needed ? "Yes" : "No"}</p>`
    ) +
    section(
      "Predictions",
      `<div class="form-grid">
        <div class="form-card"><span>Stored predictions</span><strong>${pred.total ?? 0}</strong></div>
        <div class="form-card"><span>Upcoming covered</span><strong>${pred.upcoming_with_predictions ?? 0} / ${pred.upcoming_matches ?? 0}</strong></div>
        <div class="form-card"><span>Missing picks</span><strong>${pred.missing ?? 0}</strong></div>
        <div class="form-card"><span>Avg confidence</span><strong>${fmtPct(pred.avg_confidence_pct)}</strong></div>
        <div class="form-card"><span>Avg data completeness</span><strong>${fmtPct(pred.avg_completeness_pct)}</strong></div>
        <div class="form-card"><span>Feature rows stored</span><strong>${pred.features_stored ?? 0}</strong></div>
        <div class="form-card"><span>Empty explanations</span><strong>${pred.empty_explanations ?? 0}</strong></div>
      </div>
      <p class="section-note">Prediction source breakdown:</p>
      ${modesHtml}`
    ) +
    section(
      "Model & ensemble weights",
      `<div class="form-grid">
        <div class="form-card"><span>Model version</span><strong>${escapeHtml(model.version || "bootstrap")}</strong></div>
        <div class="form-card"><span>Feature version</span><strong>${escapeHtml((model.feature_version || "—").slice(0, 12))}</strong></div>
        <div class="form-card"><span>Weights source</span><strong>${escapeHtml(model.weights_source || "—")}</strong></div>
        <div class="form-card"><span>XGBoost</span><strong>${model.xgboost_available ? "Available" : "Not installed"}</strong></div>
      </div>
      ${weightsHtml}`
    ) +
    section(
      "Cache & pipeline",
      `<div class="form-grid">
        <div class="form-card"><span>Home API cache</span><strong>${escapeHtml(cache.home_api || "—")}</strong></div>
        <div class="form-card"><span>Match cards cached</span><strong>${cache.match_cards ?? 0}</strong></div>
        <div class="form-card"><span>Team cards cached</span><strong>${cache.team_cards ?? 0}</strong></div>
        <div class="form-card"><span>Pipeline busy</span><strong>${pipeline.busy ? "Yes" : "No"}</strong></div>
        <div class="form-card"><span>Scheduler paused</span><strong>${pipeline.scheduler_suppressed ? "Yes (2h after cancel)" : "No"}</strong></div>
        <div class="form-card"><span>Recent step failures</span><strong>${pipeline.failed_steps_recent ?? 0}</strong></div>
      </div>`
    ) +
    (freshnessRows
      ? section(
          "Data freshness",
          `<table class="monitor-table"><thead><tr><th>Entity</th><th>Last updated</th><th>Complete</th><th>Source</th><th>Status</th></tr></thead><tbody>${freshnessRows}</tbody></table>`
        )
      : "")
  );
}

export async function pageMonitorOverview() {
  const status = await request("/monitor/lite", { noCache: true });
  const d = status.diagnostics;
  const active = status.active_pipeline;
  const last = status.last_pipeline_run || {};

  let pipelineLine = "No recent pipeline run";
  if (active?.running) {
    pipelineLine = `Running: ${active.step_label || active.current_step || "?"} — ${escapeHtml(active.message || "")}`;
  } else if (last.status) {
    pipelineLine = `${escapeHtml(last.service_name || "pipeline")} · ${escapeHtml(last.status)}` +
      (last.finished_at ? ` · ${formatDateIsrael(last.finished_at)}` : "");
    if (last.error_message) {
      pipelineLine += ` · ${escapeHtml(last.error_message)}`;
    }
  }

  return (
    pageHeaderHtml("System health", "Data, predictions, model weights & gaps") +
    adminPanelHtml() +
    progressBarHtml("pipeline-progress") +
    progressBarHtml("retrain-progress", { phaseLabel: "Starting model training…", showCancel: false }) +
    `<div class="metric-grid">
      ${metricCard("Database", status.database_connected ? "Connected" : "Down", status.database_connected ? "ok" : "bad")}
      ${metricCard("Matches", status.matches_count ?? 0)}
      ${metricCard("Predictions", status.predictions_count ?? 0)}
      ${metricCard("Missing picks", status.missing_predictions ?? 0, status.missing_predictions ? "warn" : "ok")}
    </div>` +
    section(
      "Refresh status",
      `<div class="form-grid">
        <div class="form-card"><span>Last prediction update</span><strong>${status.last_prediction_update ? formatDateIsrael(status.last_prediction_update) : "—"}</strong></div>
        <div class="form-card"><span>Last pipeline run</span><strong>${pipelineLine}</strong></div>
        <div class="form-card"><span>Backend</span><strong>${escapeHtml(status.database || "—")}</strong></div>
      </div>`
    ) +
    diagnosticsHtml(d)
  );
}

export function resolveMonitorPage(path, search = "") {
  void path;
  void search;
  return pageMonitorOverview();
}
