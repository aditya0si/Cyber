/**
 * Typed API client (docs/13 §4, docs/08).
 * All HTTP goes through here — no raw fetch in components.
 */

import type {
  BillingPlan,
  Detection,
  EventPage,
  GraphView,
  MeResponse,
  MissionDetail,
  MissionScore,
  MissionStarted,
  PublicMissionView,
  ScenarioSummary,
  SimulationCreated,
  SimulationSummary,
  TokenResponse,
  WSTicket,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";
const PREFIX = "/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  violations:
    | Array<{ field: string; code: string; message: string }>
    | undefined;

  constructor(
    status: number,
    code: string,
    detail: string,
    violations?: unknown,
  ) {
    super(detail);
    this.status = status;
    this.code = code;
    this.violations =
      violations === undefined
        ? undefined
        : (violations as ApiError["violations"]);
  }
}

// ---- token store (localStorage-backed; server-side is unauthenticated) ----
const ACCESS_KEY = "cs.access_token";
const REFRESH_KEY = "cs.refresh_token";

export const tokenStore = {
  get access(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(ACCESS_KEY);
  },
  get refresh(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(ACCESS_KEY, access);
    window.localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(ACCESS_KEY);
    window.localStorage.removeItem(REFRESH_KEY);
  },
};

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...extraHeaders,
  };
  const access = tokenStore.access;
  if (access) headers.Authorization = `Bearer ${access}`;

  const res = await fetch(`${BASE}${PREFIX}${path}`, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });

  if (!res.ok) {
    let payload: Record<string, unknown> = {};
    try {
      payload = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      res.status,
      String(payload.code ?? "GENERAL.UNKNOWN"),
      String(payload.detail ?? res.statusText),
      payload.violations,
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function tryRefresh(): Promise<boolean> {
  const refresh = tokenStore.refresh;
  if (!refresh) return false;
  try {
    const tokens = await request<TokenResponse>(
      "POST",
      "/auth/refresh",
      { refresh_token: refresh },
      {}, // no auth header needed
    );
    tokenStore.set(tokens.access_token, tokens.refresh_token);
    return true;
  } catch {
    tokenStore.clear();
    return false;
  }
}

export const api = {
  // ---- generic (for endpoints not covered by named helpers) ----
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),

  // ---- auth ----
  register: (email: string, password: string, orgName?: string) =>
    request<TokenResponse>("POST", "/auth/register", {
      email,
      password,
      org_name: orgName,
    }),
  login: (email: string, password: string) =>
    request<TokenResponse>("POST", "/auth/login", { email, password }),
  me: () => request<MeResponse>("GET", "/me"),
  wsTicket: () => request<WSTicket>("POST", "/auth/ws-ticket", {}),

  // ---- scenarios ----
  scenarios: () => request<ScenarioSummary[]>("GET", "/scenarios"),

  // ---- simulations ----
  createSimulation: (
    scenarioId: string,
    params: Record<string, unknown>,
    label?: string,
  ) =>
    request<SimulationCreated>(
      "POST",
      "/simulations",
      { scenario_id: scenarioId, params, label },
      {
        "Idempotency-Key": crypto.randomUUID(),
      },
    ),
  simulations: () => request<SimulationSummary[]>("GET", "/simulations"),
  simulation: (id: string) =>
    request<SimulationSummary & { params: unknown; error: string | null }>(
      "GET",
      `/simulations/${id}`,
    ),
  events: (id: string, cursor = 0, limit = 200) =>
    request<EventPage>(
      "GET",
      `/simulations/${id}/events?cursor=${cursor}&limit=${limit}`,
    ),
  graph: (id: string) => request<GraphView>("GET", `/simulations/${id}/graph`),
  detections: (id: string) =>
    request<Detection[]>("GET", `/simulations/${id}/detections`),
  execute: (
    id: string,
    detectionId: string,
    actionId: string,
    params: Record<string, unknown>,
    confirm = false,
  ) =>
    request<{
      execution_id: string;
      action_id: string;
      events_emitted: number;
    }>(
      "POST",
      `/simulations/${id}/detections/${detectionId}/execute`,
      { action_id: actionId, params, confirm },
      { "Idempotency-Key": crypto.randomUUID() },
    ),

  // ---- missions ----
  mission: (id: string) => request<MissionDetail>("GET", `/missions/${id}`),
  missionStart: (id: string) =>
    request<MissionStarted>("POST", `/missions/${id}/start`, {}),
  missionScore: (simId: string) =>
    request<MissionScore>("GET", `/simulations/${simId}/score`),

  // ---- billing (docs/16) ----
  billingPlan: () => request<BillingPlan>("GET", "/billing/plan"),
  billingCheckout: () =>
    request<{ url: string }>("POST", "/billing/checkout", {}),
  billingPortal: () => request<{ url: string }>("POST", "/billing/portal", {}),

  // ---- public share (judge) routes — no auth, token-addressed ----
  publicMission: (token: string) =>
    request<PublicMissionView>("GET", `/public/missions/${token}`),
  publicEvents: (token: string, cursor = 0, limit = 200) =>
    request<EventPage>(
      "GET",
      `/public/simulations/${token}/events?cursor=${cursor}&limit=${limit}`,
    ),
  publicDetections: (token: string) =>
    request<Detection[]>("GET", `/public/simulations/${token}/detections`),
  publicScore: (token: string) =>
    request<MissionScore>("GET", `/public/simulations/${token}/score`),
  publicExecute: (
    token: string,
    detectionId: string,
    actionId: string,
    params: Record<string, unknown>,
    confirm = false,
  ) =>
    request<{
      execution_id: string;
      action_id: string;
      events_emitted: number;
    }>(
      "POST",
      `/public/simulations/${token}/detections/${detectionId}/execute`,
      { action_id: actionId, params, confirm },
    ),
};

export async function authedRequest<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401 && tokenStore.refresh) {
      if (await tryRefresh()) return await fn();
    }
    throw err;
  }
}
