/**
 * Client for the Stage 01–03 demo endpoints (cybersim/api/main.py).
 * Raw fetch is fine here — these endpoints are unauthenticated and the demo
 * dashboard polls them on a 1s cadence.
 */

import type {
  AnalysisResponse,
  DemoEvent,
  GraphSnapshot,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    throw new Error(`${path} → ${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const demoApi = {
  start: (delay = 0.8) =>
    request<{ status: string }>(`/simulation/start?delay=${delay}`, {
      method: "POST",
    }),
  reset: () =>
    request<{ status: string }>("/simulation/reset", { method: "POST" }),
  events: () => request<DemoEvent[]>("/simulation/events"),
  graph: () => request<GraphSnapshot>("/graph"),
  analyze: () =>
    request<AnalysisResponse>("/analyst/analyze", { method: "POST" }),
  approve: () =>
    request<{ status: string }>("/analyst/approve-response", {
      method: "POST",
    }),
};
