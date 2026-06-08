import { request, adminRequest, verifyAdminSession } from "./api.js";
import {
  adminPanelHtml,
  dataFreshnessBadge,
  metricCard,
  latencyStatus,
  pageHeaderHtml,
  progressBarHtml,
  section,
  tableHtml,
  formatDateIsrael,
} from "./components.js";
import { escapeHtml } from "./flags.js";

const MONITOR_TABS = [
  { id: "overview", label: "Overview", href: "#/monitor" },
  { id: "pipeline", label: "Pipeline", href: "#/monitor/pipeline" },
  { id: "audit", label: "Prediction Audit", href: "#/monitor/audit" },
  { id: "data-flow", label: "Data Flow", href: "#/monitor/data-flow" },
  { id: "performance", label: "Performance", href: "#/monitor/performance" },
  { id: "cache", label: "Cache", href: "#/monitor/cache" },
  { id: "data-quality", label: "Data Quality", href: "#/monitor/data-quality" },
];

export function monitorNavHtml(active = "overview") {
  return `<nav class="monitor-subnav" aria-label="Monitor sections">
    ${MONITOR_TABS.map(
      (t) =>
        `<a class="monitor-tab${t.id === active ? " active" : ""}" href="${t.href}">${escapeHtml(t.label)}</a>`
    ).join("")}
  </nav>`;
}

function adminSignInHint() {
  return `<p class="empty admin-signin-hint">Some diagnostics require admin access. Click <strong>Run full pipeline</strong> below and enter the admin password to unlock audit data.</p>`;
}

function adminRequiredPage(title, subtitle, tab = "overview") {
  return (
    pageHeaderHtml(title, subtitle) +
    monitorNavHtml(tab) +
    adminPanelHtml() +
    adminSignInHint()
  );
}

function criteriaBadges(criteria) {
  if (!criteria) return "";
  const items = [
    ["Predictions", criteria.all_predictions_present],
    ["Explanations", criteria.all_explanations_present],
    ["Cache valid", criteria.cache_valid],
  ].filter(([, ok]) => ok !== null && ok !== undefined);
  if (!items.length) return "";
  return `<div class="criteria-row">${items
    .map(
      ([label, ok]) =>
        `<span class="criteria-badge ${ok ? "ok" : "bad"}">${escapeHtml(label)}: ${ok ? "OK" : "Gap"}</span>`
    )
    .join("")}</div>`;
}

export async function pageMonitorOverview() {
  const [status, freshness, summary, calibration] = await Promise.all([
    request("/monitor/status").catch(() => null),
    request("/meta/freshness").catch(() => null),
    adminRequest("/admin/audit/summary"),
    request("/evaluation/calibration?limit=30").catch(() => null),
  ]);
  if (!status) {
    return (
      pageHeaderHtml("Diagnostics console", "System health, data coverage, and success criteria") +
      monitorNavHtml("overview") +
      adminPanelHtml() +
      `<p class="empty">Could not load monitor status. The database may be busy — try again in a minute.</p>`
    );
  }
  window.setPageMeta?.({ lastUpdated: status.last_updated, showTimestamp: false });
  const dep = status.deployment || {};
  const counts = status.counts || status.table_counts || {};
  const pred = summary?.predictions || {};
  const criteria = summary?.success_criteria || status.success_criteria;
  const keys = status.api_keys || {};

  const freshnessRows = (freshness?.entities || []).map(
    (e) => `<tr>
      <td>${escapeHtml(e.entity || "—")}</td>
      <td>${formatDateIsrael(e.last_updated || "")}</td>
      <td>${e.completeness_pct != null ? `${e.completeness_pct}%` : "—"}</td>
      <td>${escapeHtml(e.source || "—")}</td>
    </tr>`
  );

  const countRows = [
    ["Fixtures", counts.fixtures ?? counts.matches],
    ["Teams", counts.teams],
    ["Players", counts.players],
    ["Injuries", counts.injuries],
    ["Predictions", counts.predictions],
    ["Missing predictions", pred.missing_predictions ?? counts.missing_predictions],
  ].map(([t, n]) => `<tr><td>${escapeHtml(t)}</td><td><strong>${n ?? 0}</strong></td></tr>`);

  const hints = (status.hints || freshness?.warnings || [])
    .slice(0, 5)
    .map((h) => `<li>${escapeHtml(typeof h === "string" ? h : h.message || JSON.stringify(h))}</li>`)
    .join("");

  return (
    pageHeaderHtml("Diagnostics console", "System health, data coverage, and success criteria") +
    monitorNavHtml("overview") +
    adminPanelHtml() +
    progressBarHtml("pipeline-progress") +
    (criteria ? criteriaBadges(criteria) : "") +
    (!summary && !(await verifyAdminSession()) ? adminSignInHint() : "") +
    (status.last_updated ? `<div class="monitor-updated">${dataFreshnessBadge(status.last_updated)}</div>` : "") +
    section(
      "Deployment",
      `<div class="metric-grid">
        ${metricCard("App version", dep.app_version || "—")}
        ${metricCard("Git commit", (dep.git_commit || "—").slice(0, 8))}
        ${metricCard("DB latency", dep.database_latency_ms != null ? `${dep.database_latency_ms} ms` : "—", latencyStatus(dep.database_latency_ms))}
        ${metricCard("Scheduler", dep.scheduler_enabled ? "Enabled" : "Disabled", dep.scheduler_enabled ? "ok" : "warn")}
        ${metricCard("Last heartbeat", dep.last_scheduler_heartbeat ? formatDateIsrael(dep.last_scheduler_heartbeat) : "—")}
      </div>`
    ) +
    section("Data loaded", tableHtml(["Entity", "Count"], countRows)) +
    (freshnessRows.length
      ? section("Entity freshness", tableHtml(["Entity", "Last sync", "Completeness", "Source"], freshnessRows))
      : "") +
    (hints ? section("Hints", `<ul>${hints}</ul>`) : "") +
    section(
      "Health",
      `<div class="form-grid">
        <div class="form-card"><span>Database</span><strong>${escapeHtml(status.database || "—")}</strong></div>
        <div class="form-card"><span>API-Football</span><strong>${keys.api_football ? "Set" : "Missing"}</strong></div>
        <div class="form-card"><span>football-data</span><strong>${keys.football_data ? "Set" : "Missing"}</strong></div>
      </div>`
    ) +
    (calibration?.samples
      ? section(
          "Model calibration",
          `<div class="form-grid">
            <div class="form-card"><span>Brier</span><strong>${calibration.brier_score ?? "—"}</strong></div>
            <div class="form-card"><span>Log loss</span><strong>${calibration.log_loss ?? "—"}</strong></div>
            <div class="form-card"><span>ECE</span><strong>${calibration.ece_home_win ?? "—"}</strong></div>
            <div class="form-card"><span>Samples</span><strong>${calibration.samples}</strong></div>
          </div>`
        )
      : "")
  );
}

export async function pageMonitorPipeline() {
  if (!(await verifyAdminSession())) {
    return adminRequiredPage("Pipeline history", "Step diagram and run timeline", "pipeline");
  }
  const [statusRaw, runsRaw] = await Promise.all([
    adminRequest("/admin/pipeline/status"),
    adminRequest("/admin/pipeline/runs?limit=15"),
  ]);
  const status = statusRaw || { active: {}, steps: [] };
  const runs = runsRaw || { runs: [] };
  const active = status.active || {};
  const steps = status.steps || [];
  const stepStates = {};
  (runs.runs?.[0]?.steps || []).forEach((s) => {
    stepStates[s.step_key] = s;
  });
  if (active.running && active.current_step) {
    stepStates[active.current_step] = { status: "running", message: active.message };
  }

  const diagram = steps
    .map((s) => {
      const st = stepStates[s.key] || {};
      const cls = st.status || "pending";
      const dur = st.duration_seconds != null ? `${st.duration_seconds}s` : "";
      return `<div class="pipeline-step pipeline-step-${cls}" title="${escapeHtml(s.label)}">
        <span class="pipeline-step-key">${escapeHtml(s.key)}</span>
        <span class="pipeline-step-name">${escapeHtml(s.name)}</span>
        ${dur ? `<span class="pipeline-step-dur">${dur}</span>` : ""}
      </div>`;
    })
    .join("");

  const runRows = (runs.runs || []).map((r) => {
    const failedSteps = (r.steps || []).filter((s) => s.status === "failed").length;
    return `<tr>
      <td>#${r.id}</td>
      <td>${escapeHtml(r.service_name || "—")}</td>
      <td><span class="status-${(r.status || "").toLowerCase()}">${escapeHtml(r.status || "—")}</span></td>
      <td>${r.records_written ?? 0}</td>
      <td>${r.records_failed ?? 0}</td>
      <td>${r.duration_seconds != null ? `${r.duration_seconds}s` : "—"}</td>
      <td>${failedSteps || "—"}</td>
      <td>${formatDateIsrael(r.finished_at || r.started_at || "")}</td>
    </tr>`;
  });

  return (
    pageHeaderHtml("Pipeline history", "Step diagram and run timeline") +
    monitorNavHtml("pipeline") +
    adminPanelHtml() +
    progressBarHtml("pipeline-progress") +
    (active.running
      ? section("Active run", `<p class="running-badge">Step ${escapeHtml(active.current_step || "?")}: ${escapeHtml(active.message || "Running…")}</p>`)
      : "") +
    section("Pipeline steps A → J", `<div class="pipeline-diagram">${diagram}</div>`) +
    section(
      "Historical runs",
      tableHtml(
        ["ID", "Mode", "Status", "Written", "Failed", "Duration", "Failed steps", "Finished"],
        runRows.length ? runRows : [`<tr><td colspan="8">No runs yet.</td></tr>`]
      )
    )
  );
}

export async function pageMonitorAudit(offset = 0) {
  if (!(await verifyAdminSession())) {
    return adminRequiredPage("Prediction audit", "Per-match prediction completeness", "audit");
  }
  const data = await adminRequest(`/admin/audit/predictions?limit=50&offset=${offset}`);
  if (!data) {
    return adminRequiredPage("Prediction audit", "Per-match prediction completeness", "audit");
  }
  const s = data.summary || {};
  const rows = (data.items || []).map((r) => {
    const statusCls = !r.has_prediction ? "bad" : r.stale_cache ? "warn" : "ok";
    return `<tr class="audit-row-${statusCls}">
      <td><a href="#/match/${r.match_id}">${r.match_id}</a></td>
      <td>${escapeHtml(r.home_team)} vs ${escapeHtml(r.away_team)}</td>
      <td>${formatDateIsrael(r.kickoff || "")}</td>
      <td>${r.has_prediction ? "✓" : "✗"}</td>
      <td>${escapeHtml(r.prediction_source_mode || "—")}</td>
      <td>${r.confidence != null ? `${Math.round(r.confidence)}%` : "—"}</td>
      <td>${r.data_completeness != null ? `${Math.round(r.data_completeness)}%` : "—"}</td>
      <td>${escapeHtml(r.top_scoreline || "—")}</td>
      <td>${r.is_present_in_match_cards_cache ? "✓" : "✗"}</td>
    </tr>`;
  });

  const summaryCards = `<div class="metric-grid">
    ${metricCard("Upcoming", s.total_upcoming_matches ?? 0)}
    ${metricCard("With prediction", s.predictions_generated ?? 0, s.missing_predictions ? "warn" : "ok")}
    ${metricCard("Missing", s.missing_predictions ?? 0, s.missing_predictions ? "bad" : "ok")}
    ${metricCard("Empty explanations", s.empty_explanations ?? 0, s.empty_explanations ? "bad" : "ok")}
    ${metricCard("Stale cache", s.stale_cache_entries ?? 0, s.stale_cache_entries ? "warn" : "ok")}
  </div>`;

  const pager =
    data.total > data.limit
      ? `<div class="pager">
          ${offset > 0 ? `<a class="btn-ghost" href="#/monitor/audit?offset=${Math.max(0, offset - 50)}">← Prev</a>` : ""}
          <span>${offset + 1}–${Math.min(offset + data.limit, data.total)} of ${data.total}</span>
          ${offset + data.limit < data.total ? `<a class="btn-ghost" href="#/monitor/audit?offset=${offset + data.limit}">Next →</a>` : ""}
        </div>`
      : "";

  return (
    pageHeaderHtml("Prediction audit", "Per-match prediction completeness") +
    monitorNavHtml("audit") +
    `<div class="admin-actions"><button class="btn-secondary" type="button" id="btn-repair-predictions">Repair missing predictions</button></div>` +
    summaryCards +
    section(
      "Matches",
      tableHtml(
        ["ID", "Match", "Kickoff", "Pred", "Source", "Conf", "Complete", "Score", "Cache"],
        rows.length ? rows : [`<tr><td colspan="9">No upcoming matches.</td></tr>`]
      ) + pager
    )
  );
}

export async function pageMonitorDataFlow() {
  if (!(await verifyAdminSession())) {
    return adminRequiredPage("Data flow", "Where data is lost between pipeline stages", "data-flow");
  }
  const flow = await adminRequest("/admin/audit/data-flow");
  if (!flow) {
    return adminRequiredPage("Data flow", "Where data is lost between pipeline stages", "data-flow");
  }
  const stages = flow.stages || [];
  const max = Math.max(...stages.map((s) => s.count), 1);
  const funnel = stages
    .map((s) => {
      const pct = Math.round((s.count / max) * 100);
      const drop = s.drop_off > 0 ? `<span class="funnel-drop">−${s.drop_off}</span>` : "";
      return `<div class="funnel-stage">
        <div class="funnel-label">${escapeHtml(s.stage)} ${drop}</div>
        <div class="funnel-bar"><div class="funnel-fill" style="width:${pct}%"></div></div>
        <div class="funnel-count">${s.count}</div>
      </div>`;
    })
    .join("");

  const gaps = `<ul class="gap-list">
    <li>Matches without features: <strong>${flow.matches_without_features ?? 0}</strong></li>
    <li>Matches without predictions: <strong>${flow.matches_without_predictions ?? 0}</strong></li>
    <li>Predictions without explanations: <strong>${flow.predictions_without_explanations ?? 0}</strong></li>
    <li>Predictions without cache: <strong>${flow.predictions_without_cache ?? 0}</strong></li>
  </ul>`;

  return (
    pageHeaderHtml("Data flow", "Where data is lost between pipeline stages") +
    monitorNavHtml("data-flow") +
    section("Pipeline funnel", `<div class="data-flow-funnel">${funnel}</div>`) +
    section("Drop-offs", gaps)
  );
}

export async function pageMonitorPerformance() {
  if (!(await verifyAdminSession())) {
    return adminRequiredPage("Performance", "API and database latency", "performance");
  }
  const perf = await adminRequest("/admin/audit/performance");
  if (!perf) {
    return adminRequiredPage("Performance", "API and database latency", "performance");
  }
  const endpoints = (perf.slowest_endpoints || []).map(
    (e) => `<tr>
      <td>${escapeHtml(e.path || "—")}</td>
      <td>${e.requests ?? 0}</td>
      <td>${e.avg_ms ?? "—"} ms</td>
      <td>${e.max_ms ?? "—"} ms</td>
      <td>${e.cache_hits ?? 0}</td>
      <td>${e.slow_count ?? 0}</td>
    </tr>`
  );
  const queries = (perf.slowest_queries || []).map(
    (q) => `<tr>
      <td><code>${escapeHtml(q.sql_fingerprint || "—")}</code></td>
      <td>${q.hits ?? 0}</td>
      <td>${q.avg_ms ?? "—"} ms</td>
      <td>${q.max_ms ?? "—"} ms</td>
    </tr>`
  );

  return (
    pageHeaderHtml("Performance", "API and database latency (measure first)") +
    monitorNavHtml("performance") +
    `<div class="metric-grid">
      ${metricCard("Requests logged", perf.total_requests ?? 0)}
      ${metricCard("Avg response", perf.avg_total_ms != null ? `${perf.avg_total_ms} ms` : "—")}
      ${metricCard("Avg DB time", perf.avg_db_ms != null ? `${perf.avg_db_ms} ms` : "—")}
      ${metricCard("Cache hit %", perf.cache_hit_ratio != null ? `${perf.cache_hit_ratio}%` : "—")}
      ${metricCard("DB ping", perf.database_latency_ms != null ? `${perf.database_latency_ms} ms` : "—", latencyStatus(perf.database_latency_ms))}
    </div>` +
    section(
      "Slowest endpoints (24h)",
      tableHtml(["Path", "Requests", "Avg", "Max", "Cache hits", "Slow"], endpoints.length ? endpoints : [`<tr><td colspan="6">No metrics yet — browse the app to collect data.</td></tr>`])
    ) +
    section(
      "Slow queries (>500ms)",
      tableHtml(["SQL", "Hits", "Avg", "Max"], queries.length ? queries : [`<tr><td colspan="4">No slow queries logged.</td></tr>`])
    )
  );
}

export async function pageMonitorCache() {
  if (!(await verifyAdminSession())) {
    return adminRequiredPage("Cache validation", "Stale, orphan, and missing UI cache entries", "cache");
  }
  const cache = await adminRequest("/admin/audit/cache");
  if (!cache) {
    return adminRequiredPage("Cache validation", "Stale, orphan, and missing UI cache entries", "cache");
  }
  const s = cache.summary || {};
  const rows = (cache.match_cards || [])
    .filter((r) => r.status !== "ok")
    .slice(0, 80)
    .map(
      (r) => `<tr class="audit-row-${r.status === "missing" ? "bad" : "warn"}">
        <td>${r.match_id}</td>
        <td>${escapeHtml(r.home_team)} vs ${escapeHtml(r.away_team)}</td>
        <td><span class="status-${r.status}">${escapeHtml(r.status)}</span></td>
        <td>${r.cache_age_hours != null ? `${r.cache_age_hours.toFixed(1)}h` : "—"}</td>
        <td>${r.source_data_age_hours != null ? `${r.source_data_age_hours.toFixed(1)}h` : "—"}</td>
      </tr>`
    );

  return (
    pageHeaderHtml("Cache validation", "Stale, orphan, and missing UI cache entries") +
    monitorNavHtml("cache") +
    `<div class="metric-grid">
      ${metricCard("OK", s.ok ?? 0, "ok")}
      ${metricCard("Stale", s.stale ?? 0, s.stale ? "warn" : "ok")}
      ${metricCard("Missing", s.missing ?? 0, s.missing ? "bad" : "ok")}
      ${metricCard("Orphan", s.orphan ?? 0, s.orphan ? "warn" : "ok")}
    </div>
    <div class="admin-actions"><button class="btn-secondary" type="button" data-pipeline-mode="predictions_only">Refresh UI cache</button></div>` +
    section(
      "Issues",
      tableHtml(
        ["Match", "Teams", "Status", "Cache age", "Source age"],
        rows.length ? rows : [`<tr><td colspan="5">All match cards look healthy.</td></tr>`]
      )
    )
  );
}

export async function pageMonitorDataQuality() {
  if (!(await verifyAdminSession())) {
    return adminRequiredPage("Data quality", "Team squads, ratings, injuries, and fixtures", "data-quality");
  }
  const dq = await adminRequest("/admin/audit/data-quality");
  if (!dq) {
    return adminRequiredPage("Data quality", "Team squads, ratings, injuries, and fixtures", "data-quality");
  }
  const s = dq.summary || {};
  const rows = (dq.teams || []).map((t) => {
    const cls = t.status === "ok" ? "ok" : t.status === "warn" ? "warn" : "bad";
    return `<tr class="audit-row-${cls}">
      <td>${escapeHtml(t.team)}</td>
      <td>${t.squad_size}/${t.squad_target}</td>
      <td>${t.avg_rating ?? "—"}</td>
      <td>${t.injuries}</td>
      <td>${t.recent_matches_90d}</td>
      <td>${t.elo_rating ?? "—"}</td>
      <td>${(t.issues || []).map((i) => escapeHtml(i)).join("; ") || "—"}</td>
    </tr>`;
  });

  return (
    pageHeaderHtml("Data quality", "Team squads, ratings, injuries, and fixtures") +
    monitorNavHtml("data-quality") +
    `<div class="metric-grid">
      ${metricCard("Teams", s.teams_audited ?? 0)}
      ${metricCard("Thin nations", s.thin_nation_count ?? 0, s.thin_nation_count ? "warn" : "ok")}
      ${metricCard("Missing ratings", s.missing_ratings ?? 0)}
      ${metricCard("No injuries data", s.missing_injuries_teams ?? 0, "warn")}
    </div>` +
    section(
      "Per team",
      tableHtml(
        ["Team", "Squad", "Avg OVR", "Injuries", "Recent", "Elo", "Issues"],
        rows
      )
    )
  );
}

export function resolveMonitorPage(path, search = "") {
  const params = new URLSearchParams(search);
  const offset = parseInt(params.get("offset") || "0", 10);
  if (path === "/monitor/pipeline") return pageMonitorPipeline();
  if (path === "/monitor/audit") return pageMonitorAudit(offset);
  if (path === "/monitor/data-flow") return pageMonitorDataFlow();
  if (path === "/monitor/performance") return pageMonitorPerformance();
  if (path === "/monitor/cache") return pageMonitorCache();
  if (path === "/monitor/data-quality") return pageMonitorDataQuality();
  return pageMonitorOverview();
}
