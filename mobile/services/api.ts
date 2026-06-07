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

  home: () =>
    request<{
      stats: { upcoming: number; live: number; predictions: number; teams?: number };
      matches: import("@/types").Match[];
      live?: import("@/types").Match[];
      last_updated?: string;
    }>("/home"),

  matches: (status = "upcoming", page = 1) =>
    request<{ matches: import("@/types").Match[]; pagination: Record<string, number> }>(
      `/matches?status=${status}&page=${page}`
    ),

  stats: () => request<{ upcoming: number; live: number; predictions: number }>("/stats"),

  upcoming: () => request<import("@/types").Match[]>("/matches/upcoming"),

  live: () => request<import("@/types").Match[]>("/matches/live"),

  recent: () => request<import("@/types").Match[]>("/matches/recent"),

  detail: (id: number) => request<import("@/types").Match>(`/matches/${id}`),

  monitorStatus: () => request<Record<string, unknown>>("/monitor/status"),

  pipelineProgress: () =>
    request<{ running: boolean; overall_progress_pct?: number; message?: string }>(
      "/admin/pipeline/progress"
    ),

  adminAuth: (password: string) =>
    request<{ token: string }>("/admin/auth", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  runPipeline: (mode: string, token: string) =>
    request<{ run_id: number }>(`/admin/pipeline/run?mode=${mode}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }),
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
