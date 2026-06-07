/** HTTP client for WC 2026 API. */
export const API = "";

export async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function loadFreshness() {
  try {
    return await request("/meta/freshness");
  } catch {
    return null;
  }
}
