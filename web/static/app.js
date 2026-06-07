import { request, loadFreshness } from "./js/api.js";
import { freshnessBarHtml } from "./js/components.js";
import {
  pageMatches, pageLive, pageResults, pageTeam, pageMatch,
  pageTournament, pageBracket, pagePlayers, pageReports, pageMonitor,
} from "./js/pages.js";

const content = document.querySelector("#content");
const loading = document.querySelector("#loading");
const errorBox = document.querySelector("#error");
const freshnessBar = document.querySelector("#freshness-bar");
const nav = document.querySelector("#main-nav");

let activeRoute = "matches";

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

function showLoading(show) {
  loading?.classList.toggle("hidden", !show);
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

async function updateFreshnessBar() {
  const data = await loadFreshness();
  if (!freshnessBar) return;
  const html = freshnessBarHtml(data);
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
  showLoading(true);
  content.innerHTML = "";
  try {
    content.innerHTML = await handler(match);
    void updateFreshnessBar();
  } catch (e) {
    showError(e.message || "Failed to load page");
    content.innerHTML = "";
  } finally {
    showLoading(false);
  }
}

async function refreshData() {
  const btn = document.querySelector("#btn-refresh");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-icon">↻</span> Syncing…`;
  }
  showError(null);
  try {
    await request("/seed", { method: "POST" }).catch(() => null);
    await request("/sync/full", { method: "POST" });
    await new Promise((r) => setTimeout(r, 2000));
    await navigate();
  } catch {
    try {
      await request("/sync/matches", { method: "POST" });
      await navigate();
    } catch {
      showError("Sync failed — Render free tier may be cold-starting. Try again in a minute.");
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span class="btn-icon">↻</span> Sync data`;
    }
  }
}

async function adminRefreshPredictions() {
  const btn = document.querySelector("#btn-admin-predict");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Refreshing predictions…";
  }
  try {
    await request("/admin/predictions/refresh", { method: "POST" });
    await navigate();
  } catch (e) {
    showError(e.message || "Prediction refresh failed");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Admin: refresh predictions";
    }
  }
}

window.addEventListener("hashchange", navigate);

document.querySelector("#btn-refresh")?.addEventListener("click", refreshData);
document.addEventListener("click", (e) => {
  if (e.target.closest("#btn-admin-predict")) {
    e.preventDefault();
    adminRefreshPredictions();
  }
});

document.querySelector("#disclaimer-toggle")?.addEventListener("click", () => {
  document.querySelector("#disclaimer-panel")?.classList.toggle("hidden");
});

nav?.addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (tab) setActiveNav(tab.dataset.route);
});

navigate();
