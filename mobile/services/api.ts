const BASE = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; author: string; disclaimer: string }>("/health"),

  stats: () => request<{ upcoming: number; live: number; predictions: number }>("/stats"),

  upcoming: () => request<import("@/types").Match[]>("/matches/upcoming"),

  live: () => request<import("@/types").Match[]>("/matches/live"),

  recent: () => request<import("@/types").Match[]>("/matches/recent"),

  detail: (id: number) => request<import("@/types").Match>(`/matches/${id}`),

  bootstrap: () => request<{ bootstrapped: boolean }>("/bootstrap", { method: "POST" }),

  refresh: async () => {
    await request("/sync/full", { method: "POST" });
  },

  syncLive: () => request("/sync/live", { method: "POST" }),
};

export function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function isLive(status: string): boolean {
  return ["1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED"].includes(status);
}
