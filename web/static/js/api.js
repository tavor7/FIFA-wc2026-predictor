/** HTTP client for WC 2026 API. */
export const API = "";

const CACHE_MS = 90_000;
const memoryCache = new Map();

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

export async function request(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const useCache = method === "GET" && !options.noCache;
  if (useCache) {
    const hit = readCache(path);
    if (hit !== null) return hit;
  }

  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  const data = await res.json();
  if (useCache) writeCache(path, data);
  return data;
}

export async function loadFreshness() {
  try {
    return await request("/meta/freshness");
  } catch {
    return null;
  }
}
