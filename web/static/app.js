import {
  request, loadFreshness, lastResponseMeta, adminLogin, getAdminToken, setAdminToken,
  verifyAdminSession, pollPipelineProgress, abortPipelinePolling,
  pollRetrainProgress, abortRetrainPolling, cacheBust,
} from "./js/api.js";
import { freshnessBarHtml, skeletonCardsHtml, setMonitorControlsLocked } from "./js/components.js";
import {
  pageMatches, pageLive, pageResults, pageTeam, pageMatch,
  pageTournament, pageBracket, pagePlayers, pageReports, pageMonitor,
} from "./js/pages.js";

const content = document.querySelector("#content");
const loading = document.querySelector("#loading");
const errorBox = document.querySelector("#error");
const freshnessBar = document.querySelector("#freshness-bar");
const nav = document.querySelector("#main-nav");
const adminModal = document.querySelector("#admin-modal");
const adminForm = document.querySelector("#admin-form");
const adminPasswordInput = document.querySelector("#admin-password");
const adminModalError = document.querySelector("#admin-modal-error");

let activeRoute = "matches";
let pageMeta = {};
let pipelineCancelRequested = false;
let monitorPipelineActive = false;
let monitorRetrainActive = false;

const ROUTES = [
  { pattern: /^\/team\/([^/]+)$/, name: "team", handler: ([, slug]) => pageTeam(slug) },
  { pattern: /^\/match\/(\d+)$/, name: "match", handler: ([, id]) => pageMatch(id) },
  { pattern: /^\/live$/, name: "live", handler: () => pageLive() },
  { pattern: /^\/results$/, name: "results", handler: () => pageResults() },
  { pattern: /^\/tournament$/, name: "tournament", handler: () => pageTournament() },
  { pattern: /^\/bracket$/, name: "bracket", handler: () => pageBracket() },
  { pattern: /^\/players$/, name: "players", handler: () => pagePlayers() },
  { pattern: /^\/reports$/, name: "reports", handler: () => pageReports() },
  { pattern: /^\/monitor(\/.*)?$/, name: "monitor", handler: (m) => pageMonitor(m[0] || "/monitor", m.search || "") },
  { pattern: /^\/$/, name: "matches", handler: () => pageMatches() },
];

function parseHash() {
  const raw = (location.hash || "#/").slice(1);
  const [pathPart, queryPart] = raw.split("?");
  const path = pathPart.startsWith("/") ? pathPart : `/${pathPart}`;
  const search = queryPart ? `?${queryPart}` : "";
  for (const route of ROUTES) {
    const m = path.match(route.pattern);
    if (m) {
      m.search = search;
      if (route.name === "monitor") {
        return { name: route.name, handler: () => pageMonitor(path, search), match: m };
      }
      return { name: route.name, handler: route.handler, match: m };
    }
  }
  return { name: "matches", handler: () => pageMatches(), match: ["/"] };
}

function setActiveNav(name) {
  nav?.querySelectorAll(".tab").forEach((el) => {
    const r = el.dataset.route;
    el.classList.toggle("active", r === name || (name === "team" && r === "matches") || (name === "match" && r === "matches"));
  });
}

function showError(msg) {
  if (!msg) {
    errorBox?.classList.add("hidden");
    if (errorBox) errorBox.textContent = "";
    return;
  }
  if (errorBox) {
    errorBox.textContent = msg;
    errorBox.classList.remove("hidden");
  }
}

function showAdminModalError(msg) {
  if (!adminModalError) return;
  if (!msg) {
    adminModalError.textContent = "";
    adminModalError.classList.add("hidden");
    return;
  }
  adminModalError.textContent = msg;
  adminModalError.classList.remove("hidden");
}

function pipelineFinished() {
  monitorPipelineActive = false;
  if (!monitorRetrainActive) setMonitorControlsLocked(false);
}

function retrainFinished() {
  monitorRetrainActive = false;
  if (!monitorPipelineActive) setMonitorControlsLocked(false);
}

function monitorIsBusy() {
  return monitorPipelineActive || monitorRetrainActive;
}

async function updateFreshnessBar() {
  const data = await loadFreshness();
  if (!freshnessBar) return;
  const html = freshnessBarHtml(data, {
    ...pageMeta,
    responseTimeMs: lastResponseMeta.responseTimeMs,
    cache: lastResponseMeta.cache,
    showTimestamp: activeRoute !== "monitor",
  });
  if (html) {
    freshnessBar.innerHTML = html;
    freshnessBar.classList.remove("hidden");
  } else {
    freshnessBar.classList.add("hidden");
    freshnessBar.innerHTML = "";
  }
}

let livePollTimer = null;

async function navigate() {
  if (livePollTimer) {
    clearInterval(livePollTimer);
    livePollTimer = null;
  }
  const { name, handler, match } = parseHash();
  activeRoute = name;
  setActiveNav(name === "team" || name === "match" ? "matches" : name);
  showError(null);

  if (name === "monitor") {
    if (!(await ensureAdminAuth())) {
      loading?.classList.add("hidden");
      content.innerHTML = "";
      if (location.hash.includes("monitor")) {
        location.hash = "#/";
      }
      return;
    }
  }

  loading?.classList.remove("hidden");
  content.innerHTML = skeletonCardsHtml(name === "monitor" ? 2 : 4);
  try {
    const html = await handler(match);
    content.innerHTML = html;
    void updateFreshnessBar();
    if (name === "live") {
      livePollTimer = setInterval(() => {
        if (activeRoute === "live") void navigate();
      }, 30000);
    }
    if (name === "monitor" && !monitorIsBusy()) {
      void resumePipelineProgressIfRunning();
      void resumeRetrainProgressIfRunning();
    }
  } catch (e) {
    showError(e.message || "Failed to load page");
    content.innerHTML =
      `<p class="empty">Could not load this page. If a data sync is running on Render, wait a minute or open <a href="#/monitor">Monitor</a> to cancel it.</p>`;
  } finally {
    loading?.classList.add("hidden");
  }
}

async function ensureAdminAuth() {
  if (await verifyAdminSession()) return true;
  if (!adminModal || !adminForm) return false;

  showAdminModalError(null);
  if (adminPasswordInput) adminPasswordInput.value = "";
  adminModal.showModal();
  requestAnimationFrame(() => adminPasswordInput?.focus());

  return new Promise((resolve) => {
    const onCancel = () => {
      adminModal.close();
      cleanup();
      resolve(false);
    };

    const onSubmit = async (e) => {
      e.preventDefault();
      const password = adminPasswordInput?.value?.trim();
      if (!password) return;
      try {
        await adminLogin(password);
        adminModal.close();
        cleanup();
        resolve(true);
      } catch {
        showAdminModalError("Invalid password. Try again.");
        if (adminPasswordInput) {
          adminPasswordInput.value = "";
          adminPasswordInput.focus();
        }
      }
    };

    const cleanup = () => {
      adminForm.removeEventListener("submit", onSubmit);
      adminModal.removeEventListener("cancel", onCancel);
      document.querySelector("#admin-cancel")?.removeEventListener("click", onCancel);
      document.querySelector("#admin-modal-close")?.removeEventListener("click", onCancel);
    };

    adminForm.addEventListener("submit", onSubmit);
    adminModal.addEventListener("cancel", onCancel);
    document.querySelector("#admin-cancel")?.addEventListener("click", onCancel);
    document.querySelector("#admin-modal-close")?.addEventListener("click", onCancel);
  });
}

async function adminReloadPlayers() {
  if (monitorIsBusy()) return;
  const btn = document.querySelector("#btn-admin-players");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Loading squads…";
  }
  try {
    const data = await request("/admin/players/reload", { method: "POST" });
    alert(data.message || "Kaggle squads reload started.");
  } catch (e) {
    showError(e.message || "Squad reload failed");
  } finally {
    if (btn && !monitorIsBusy()) {
      btn.disabled = false;
      btn.textContent = "Reload Kaggle squads";
    }
  }
}

async function adminRefreshPredictions() {
  if (monitorIsBusy()) return;
  const btn = document.querySelector("#btn-admin-predict");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Refreshing…";
  }
  try {
    const data = await request("/admin/predictions/refresh", { method: "POST" });
    cacheBust();
    showError(null);
    if (btn) btn.textContent = "Running in background…";
    await new Promise((r) => setTimeout(r, 8000));
    await navigate();
  } catch (e) {
    showError(e.message || "Prediction refresh failed");
  } finally {
    if (btn && !monitorIsBusy()) {
      btn.disabled = false;
      btn.textContent = "Refresh predictions";
    }
  }
}

function adminLogout() {
  setAdminToken(null);
  cacheBust();
  if (location.hash.includes("monitor")) {
    location.hash = "#/";
  } else {
    navigate();
  }
}

async function adminCancelPipeline() {
  const btn = document.getElementById("btn-pipeline-cancel");
  if (btn?.disabled && btn.textContent === "Cancelling…") return;

  abortPipelinePolling();
  pipelineCancelRequested = true;
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Cancelling…";
  }

  try {
    const { updateProgressBar } = await import("./js/components.js");
    const resp = await request("/admin/pipeline/cancel", { method: "POST" });

    if (resp?.status === "cancelled" || resp?.status === "no_active_run") {
      pipelineFinished();
      pipelineCancelRequested = false;
      updateProgressBar("pipeline-progress", {
        running: false,
        cancelled: true,
        overall_progress_pct: 0,
        message: resp.message || "All pipeline runs stopped. Scheduler paused 2 hours.",
      });
      return;
    }

    updateProgressBar("pipeline-progress", {
      running: true,
      cancellable: true,
      cancel_requested: true,
      overall_progress_pct: 0,
      message: resp?.message || "Cancelling all runs…",
    });

    const result = await pollPipelineProgress((p) => updateProgressBar("pipeline-progress", p));
    pipelineFinished();
    pipelineCancelRequested = false;
    updateProgressBar("pipeline-progress", {
      running: false,
      cancelled: true,
      overall_progress_pct: result?.overall_progress_pct ?? 0,
      elapsed_seconds: result?.elapsed_seconds,
      message: "All pipeline runs stopped. Scheduler paused 2 hours.",
    });
  } catch (e) {
    pipelineFinished();
    pipelineCancelRequested = false;
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Cancel";
    }
    showError(e.message || "Could not cancel pipeline");
  }
}

async function adminRunPipeline(mode) {
  if (monitorIsBusy()) {
    showError(monitorRetrainActive
      ? "Model training is running. Wait for it to finish."
      : "A pipeline is already running. Cancel it first.");
    return;
  }

  pipelineCancelRequested = false;
  abortPipelinePolling();
  monitorPipelineActive = true;
  setMonitorControlsLocked(true);

  const { updateProgressBar } = await import("./js/components.js");
  const panel = document.getElementById("pipeline-progress");
  if (panel) panel.classList.remove("hidden");

  try {
    const start = await request(
      `/admin/pipeline/run?mode=${encodeURIComponent(mode)}`,
      { method: "POST" }
    );
    if (start?.plan?.skip_count > 0) {
      const skipped = Object.values(start.plan.steps_skipped || {})
        .map((s) => s.label)
        .join(", ");
      updateProgressBar("pipeline-progress", {
        running: true,
        overall_progress_pct: 2,
        phase_label: "Planning",
        step_label: "Pipeline",
        message: `Skipping ${start.plan.skip_count} done step(s)${skipped ? `: ${skipped}` : ""}`,
        step_number: 1,
        steps_total: start.plan.run_count + start.plan.skip_count,
      });
    }
    const result = await pollPipelineProgress((p) => updateProgressBar("pipeline-progress", p));

    if (result?.aborted) {
      return;
    }
    if (pipelineCancelRequested && !result?.running) {
      updateProgressBar("pipeline-progress", {
        running: false,
        cancelled: true,
        overall_progress_pct: result?.overall_progress_pct ?? 0,
        elapsed_seconds: result?.elapsed_seconds,
        message: "Pipeline run was cancelled.",
      });
    } else if (result?.error) {
      showError(`Pipeline polling lost connection: ${result.error}`);
    } else if (!result?.running) {
      updateProgressBar("pipeline-progress", {
        running: false,
        overall_progress_pct: 100,
        elapsed_seconds: result?.elapsed_seconds,
        message: "Pipeline complete",
      });
      cacheBust();
      if (activeRoute === "monitor") {
        await navigate();
      }
    }
  } catch (e) {
    const msg = e.message || "Pipeline run failed";
    if (e.status === 409 || msg.toLowerCase().includes("already running")) {
      showError(msg);
    } else if (msg.toLowerCase().includes("authentication")) {
      showError("Admin session expired — sign in again from Monitor.");
    } else {
      showError(msg);
    }
  } finally {
    pipelineFinished();
    pipelineCancelRequested = false;
  }
}

async function adminRetrainModels() {
  if (monitorIsBusy()) {
    showError(monitorPipelineActive
      ? "A pipeline is running — wait or cancel it first."
      : "Model training is already in progress.");
    return;
  }

  abortRetrainPolling();
  monitorRetrainActive = true;
  setMonitorControlsLocked(true);

  const { updateProgressBar } = await import("./js/components.js");
  const panel = document.getElementById("retrain-progress");
  if (panel) panel.classList.remove("hidden");

  try {
    await request("/admin/model/retrain", { method: "POST" });
    updateProgressBar("retrain-progress", {
      running: true,
      mode_label: "Model training",
      overall_progress_pct: 2,
      step_label: "Starting",
      message: "Training Random Forest, XGBoost, and Elo…",
      step_number: 1,
      steps_total: 8,
    });

    const result = await pollRetrainProgress((p) => updateProgressBar("retrain-progress", p));

    if (result?.aborted) return;

    if (result?.status === "failed" || result?.error) {
      updateProgressBar("retrain-progress", {
        running: false,
        failed: true,
        mode_label: "Model training",
        overall_progress_pct: result.overall_progress_pct ?? 0,
        elapsed_seconds: result.elapsed_seconds,
        error: result.error || result.message,
        step_label: result.step_label,
      });
      showError(result.error || "Model training failed");
      return;
    }

    if (result?.error && !result?.running) {
      showError(`Training polling lost connection: ${result.error}`);
      return;
    }

    updateProgressBar("retrain-progress", {
      running: false,
      mode_label: "Model training",
      overall_progress_pct: 100,
      elapsed_seconds: result?.elapsed_seconds,
      model_version: result?.model_version,
      message: result?.message || "Training complete — reloading…",
    });
    await navigate();
  } catch (e) {
    const msg = e.message || "Model training failed";
    if (e.status === 409 || msg.toLowerCase().includes("already")) {
      showError(msg);
    } else if (msg.toLowerCase().includes("authentication")) {
      showError("Admin session expired — sign in again from Monitor.");
    } else {
      showError(msg);
    }
  } finally {
    retrainFinished();
  }
}

window.addEventListener("hashchange", navigate);

document.addEventListener("click", (e) => {
  if (monitorPipelineActive && !e.target.closest("#btn-pipeline-cancel")) {
    const blocked =
      e.target.closest("[data-pipeline-mode]") ||
      e.target.closest("#btn-admin-predict") ||
      e.target.closest("#btn-admin-players") ||
      e.target.closest("#btn-admin-retrain") ||
      e.target.closest("#btn-repair-predictions");
    if (blocked) {
      e.preventDefault();
      showError("Wait for the current pipeline to finish or click Cancel.");
      return;
    }
  }
  if (monitorRetrainActive) {
    const blocked =
      e.target.closest("[data-pipeline-mode]") ||
      e.target.closest("#btn-admin-predict") ||
      e.target.closest("#btn-admin-players") ||
      e.target.closest("#btn-admin-retrain") ||
      e.target.closest("#btn-repair-predictions");
    if (blocked) {
      e.preventDefault();
      showError("Wait for model training to finish.");
      return;
    }
  }

  if (e.target.closest("#btn-admin-logout")) {
    e.preventDefault();
    adminLogout();
  }
  if (e.target.closest("#btn-admin-retrain")) {
    e.preventDefault();
    adminRetrainModels();
  }

  if (e.target.closest("#btn-admin-predict")) {
    e.preventDefault();
    adminRefreshPredictions();
  }
  if (e.target.closest("#btn-admin-players")) {
    e.preventDefault();
    adminReloadPlayers();
  }
  const pipeBtn = e.target.closest("[data-pipeline-mode]");
  if (pipeBtn) {
    e.preventDefault();
    adminRunPipeline(pipeBtn.dataset.pipelineMode);
  }
  if (e.target.closest("#btn-pipeline-cancel")) {
    e.preventDefault();
    adminCancelPipeline();
  }
  if (e.target.closest("#btn-repair-predictions")) {
    e.preventDefault();
    adminRepairPredictions();
  }
});

async function adminRepairPredictions() {
  if (monitorIsBusy()) return;
  const btn = document.querySelector("#btn-repair-predictions");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Repairing…";
  }
  try {
    const data = await request("/admin/audit/repair-predictions", { method: "POST" });
    alert(`Fixed ${data.generated ?? 0} predictions. Missing after: ${data.missing_after ?? "?"}`);
    await navigate();
  } catch (err) {
    showError(err.message || "Repair failed");
  } finally {
    if (btn && !monitorIsBusy()) {
      btn.disabled = false;
      btn.textContent = "Repair missing predictions";
    }
  }
}

window.setPageMeta = (meta) => {
  pageMeta = meta || {};
};

document.querySelector("#disclaimer-toggle")?.addEventListener("click", () => {
  document.querySelector("#disclaimer-panel")?.classList.toggle("hidden");
});

nav?.addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (tab) setActiveNav(tab.dataset.route);
});

async function resumePipelineProgressIfRunning() {
  if (activeRoute !== "monitor" || !(await verifyAdminSession())) return;
  if (monitorIsBusy()) return;

  try {
    const { updateProgressBar } = await import("./js/components.js");
    const data = await request("/admin/pipeline/progress", { noCache: true });
    if (!data?.running) return;

    monitorPipelineActive = true;
    setMonitorControlsLocked(true);
    pipelineCancelRequested = !!data.cancel_requested;
    updateProgressBar("pipeline-progress", data);

    const result = await pollPipelineProgress((p) => updateProgressBar("pipeline-progress", p));
    if (result?.aborted) return;

    if (pipelineCancelRequested && !result?.running) {
      updateProgressBar("pipeline-progress", {
        running: false,
        cancelled: true,
        overall_progress_pct: result?.overall_progress_pct ?? data.overall_progress_pct ?? 0,
        elapsed_seconds: result?.elapsed_seconds ?? data.elapsed_seconds,
        message: "Pipeline run was cancelled.",
      });
    } else if (!result?.running && (result?.overall_progress_pct ?? 0) >= 99) {
      updateProgressBar("pipeline-progress", {
        running: false,
        overall_progress_pct: 100,
        elapsed_seconds: result?.elapsed_seconds,
        message: "Pipeline complete",
      });
      cacheBust();
      if (activeRoute === "monitor") {
        await navigate();
      }
    }
  } catch {
    /* ignore */
  } finally {
    pipelineFinished();
    pipelineCancelRequested = false;
  }
}

async function resumeRetrainProgressIfRunning() {
  if (activeRoute !== "monitor" || !(await verifyAdminSession())) return;
  if (monitorIsBusy()) return;

  try {
    const { updateProgressBar } = await import("./js/components.js");
    const data = await request("/admin/model/retrain/progress", { noCache: true });
    if (!data?.running) return;

    monitorRetrainActive = true;
    setMonitorControlsLocked(true);
    updateProgressBar("retrain-progress", data);

    const result = await pollRetrainProgress((p) => updateProgressBar("retrain-progress", p));
    if (result?.aborted) return;

    if (result?.status === "failed") {
      updateProgressBar("retrain-progress", {
        running: false,
        failed: true,
        mode_label: "Model training",
        overall_progress_pct: result.overall_progress_pct ?? data.overall_progress_pct ?? 0,
        elapsed_seconds: result.elapsed_seconds ?? data.elapsed_seconds,
        error: result.error,
        step_label: result.step_label,
      });
    } else if (!result?.running && (result?.overall_progress_pct ?? 0) >= 99) {
      updateProgressBar("retrain-progress", {
        running: false,
        mode_label: "Model training",
        overall_progress_pct: 100,
        elapsed_seconds: result?.elapsed_seconds,
        model_version: result?.model_version,
        message: result?.message || "Training complete",
      });
    }
  } catch {
    /* ignore */
  } finally {
    retrainFinished();
  }
}

navigate();
