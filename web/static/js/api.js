/** HTTP client for WC 2026 API. */
export const API = "";

const CACHE_MS = 90_000;
const memoryCache = new Map();
const ADMIN_TOKEN_KEY = "wc2026_admin_token";

export let lastResponseMeta = {
  cache: null,
  responseTimeMs: null,
  dataVersion: null,
  lastPredictionUpdate: null,
};

function cacheKey(path) {
  return path;
}

function readCache(path) {
  const key = cacheKey(path);
  const mem = memoryCache.get(key);
  if (mem && Date.now() - mem.t < CACHE_MS) return mem.data;
  try {
    const raw = sessionStorage.getItem(`api:${key}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Date.now() - parsed.t < CACHE_MS) {
      memoryCache.set(key, parsed);
      return parsed.data;
    }
  } catch {
    /* ignore */
  }
  return null;
}

function writeCache(path, data) {
  const entry = { t: Date.now(), data };
  memoryCache.set(cacheKey(path), entry);
  try {
    sessionStorage.setItem(`api:${cacheKey(path)}`, JSON.stringify(entry));
  } catch {
    /* quota */
  }
}

export function cacheBust() {
  memoryCache.clear();
  try {
    Object.keys(sessionStorage).forEach((k) => {
      if (k.startsWith("api:")) sessionStorage.removeItem(k);
    });
  } catch {
    /* ignore */
  }
}

export function getAdminToken() {
  try {
    return sessionStorage.getItem(ADMIN_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAdminToken(token) {
  try {
    if (token) sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
    else sessionStorage.removeItem(ADMIN_TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export async function adminLogin(password) {
  const data = await request("/admin/auth", {
    method: "POST",
    body: JSON.stringify({ password }),
    noCache: true,
  });
  setAdminToken(data.token);
  return data;
}

export async function request(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const useCache = method === "GET" && !options.noCache;
  if (useCache) {
    const hit = readCache(path);
    if (hit !== null) {
      lastResponseMeta.cache = "HIT";
      return hit;
    }
  }

  const headers = { "Content-Type": "application/json", ...options.headers };
  const token = getAdminToken();
  if (token && (method !== "GET" || path.startsWith("/admin"))) {
    headers.Authorization = `Bearer ${token}`;
  }

  const timeoutMs = options.timeoutMs ?? 60_000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(`${API}${path}`, {
      ...options,
      headers,
      signal: options.signal ?? controller.signal,
    });
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new Error("Request timed out — the database may be busy (pipeline sync on Render?). Try again shortly.");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
  lastResponseMeta = {
    cache: res.headers.get("X-Cache"),
    responseTimeMs: res.headers.get("X-Response-Time-ms"),
    dataVersion: res.headers.get("X-Data-Version"),
    lastPredictionUpdate: res.headers.get("X-Last-Prediction-Update"),
  };

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  const data = await res.json();
  if (useCache) writeCache(path, data);
  if (method !== "GET") cacheBust();
  return data;
}

export async function loadFreshness() {
  try {
    return await request("/meta/freshness");
  } catch {
    return null;
  }
}

export async function pollPipelineProgress(onUpdate, intervalMs = 800) {
  let pollErrors = 0;
  const maxPollErrors = 40;

  return new Promise((resolve) => {
    const poll = async () => {
      try {
        const data = await request("/admin/pipeline/progress", { noCache: true });
        pollErrors = 0;
        onUpdate(data);
        if (data.running) {
          setTimeout(poll, intervalMs);
        } else {
          resolve(data);
        }
      } catch (e) {
        pollErrors += 1;
        if (pollErrors < maxPollErrors) {
          setTimeout(poll, intervalMs * 2);
        } else {
          resolve({ running: false, error: e.message });
        }
      }
    };
    poll();
  });
}
