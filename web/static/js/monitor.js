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

export async function pageMonitorOverview() {
  const status = await request("/monitor/lite", { noCache: true });
  const active = status.active_pipeline;
  const last = status.last_pipeline_run || {};

  let pipelineLine = "No recent pipeline run";
  if (active?.running) {
    pipelineLine = `Running: ${active.step_label || active.current_step || "?"} — ${escapeHtml(active.message || "")}`;
  } else if (last.status) {
    pipelineLine = `${escapeHtml(last.service_name || "pipeline")} · ${escapeHtml(last.status)}` +
      (last.finished_at ? ` · ${formatDateIsrael(last.finished_at)}` : "");
  }

  return (
    pageHeaderHtml("System health", "Core status — read-only") +
    adminPanelHtml() +
    progressBarHtml("pipeline-progress") +
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
      </div>
      <p class="section-note">Heavy sync and diagnostics are admin-only. Use the buttons below to refresh data.</p>`
    )
  );
}

export function resolveMonitorPage(path, search = "") {
  void path;
  void search;
  return pageMonitorOverview();
}
