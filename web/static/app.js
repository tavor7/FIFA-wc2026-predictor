import { request, loadFreshness, lastResponseMeta, adminLogin, getAdminToken, pollPipelineProgress } from "./js/api.js";
import { freshnessBarHtml, skeletonCardsHtml } from "./js/components.js";
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

const ROUTES = [
  { pattern: /^\/team\/([^/]+)$/, name: "team", handler: ([, slug]) => pageTeam(slug) },
  { pattern: /^\/match\/(\d+)$/, name: "match", handler: ([, id]) => pageMatch(id) },
  { pattern: /^\/live$/, name: "live", handler: () => pageLive() },
  { pattern: /^\/results$/, name: "results", handler: () => pageResults() },
  { pattern: /^\/tournament$/, name: "tournament", handler: () => pageTournament() },
  { pattern: /^\/bracket$/, name: "bracket", handler: () => pageBracket() },
  { pattern: /^\/players$/, name: "players", handler: () => pagePlayers() },
  { pattern: /^\/reports$/, name: "reports", handler: () => pageReports() },
  { pattern: /^\/monitor$/, name: "monitor", handler: () => pageMonitor() },
  { pattern: /^\/$/, name: "matches", handler: () => pageMatches() },
];

function parseHash() {
  const raw = (location.hash || "#/").slice(1);
  const path = raw.startsWith("/") ? raw : `/${raw}`;
  for (const route of ROUTES) {
    const m = path.match(route.pattern);
    if (m) return { name: route.name, handler: route.handler, match: m };
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

async function navigate() {
  const { name, handler, match } = parseHash();
  activeRoute = name;
  setActiveNav(name === "team" || name === "match" ? "matches" : name);
  showError(null);
  loading?.classList.add("hidden");
  content.innerHTML = skeletonCardsHtml(name === "monitor" ? 2 : 4);
  try {
    const html = await handler(match);
    content.innerHTML = html;
    void updateFreshnessBar();
  } catch (e) {
    showError(e.message || "Failed to load page");
    content.innerHTML = "";
  }
}

async function ensureAdminAuth() {
  if (getAdminToken()) return true;
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
  if (!(await ensureAdminAuth())) return;
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
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Reload Kaggle squads";
    }
  }
}

async function adminRefreshPredictions() {
  if (!(await ensureAdminAuth())) return;
  const btn = document.querySelector("#btn-admin-predict");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Refreshing…";
  }
  try {
    await request("/admin/predictions/refresh", { method: "POST" });
    await navigate();
  } catch (e) {
    showError(e.message || "Prediction refresh failed");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Refresh predictions";
    }
  }
}

async function adminRunPipeline(mode) {
  if (!(await ensureAdminAuth())) return;
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
    if (result?.error) {
      showError(`Pipeline polling lost connection: ${result.error}`);
    } else if (activeRoute === "monitor") {
      await navigate();
    }
  } catch (e) {
    showError(e.message || "Pipeline run failed");
  }
}

window.addEventListener("hashchange", navigate);

document.addEventListener("click", (e) => {
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
});

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
  try {
    const { pollPipelineProgress } = await import("./js/api.js");
    const { updateProgressBar } = await import("./js/components.js");
    const data = await request("/admin/pipeline/progress", { noCache: true });
    if (data?.running) {
      updateProgressBar("pipeline-progress", data);
      await pollPipelineProgress((p) => updateProgressBar("pipeline-progress", p));
      if (activeRoute === "monitor") await navigate();
    }
  } catch {
    /* ignore */
  }
}

navigate();
resumePipelineProgressIfRunning();
