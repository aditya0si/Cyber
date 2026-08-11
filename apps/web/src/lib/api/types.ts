/** API model types (docs/08 §12) — hand-typed mirror of schema.lock.json. */

export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type DetectionSource = "ai" | "rules" | "hybrid";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  org_id: string;
  org_role: string;
}

export interface ScenarioDisplay {
  title: string;
  blurb: string;
  category: string;
  difficulty: string;
  duration_sec: number;
}

export interface ScenarioSummary {
  id: string;
  simulator: string;
  category: string;
  status: string;
  display: ScenarioDisplay;
}

export interface SimulationCreated {
  simulation_id: string;
  status: string;
  ws_channel: string;
  scenario: { id: string; display: ScenarioDisplay };
  graph_seed_seq: number;
  entitlements: Record<string, unknown>;
}

export interface SimulationSummary {
  id: string;
  org_id: string;
  scenario_id: string;
  seed: number;
  status: string;
  phase: string | null;
  label: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  events_count: number;
  detections_count: number;
  actions_count: number;
}

export interface CanonicalEvent {
  event_id: string;
  timestamp: string;
  event_type: string;
  severity: string;
  source_ip: string;
  target_asset: string;
  actor: string;
  raw_context: Record<string, unknown>;
}

export interface EvidenceItem {
  label: string;
  kind: string;
  weight: number;
  event_ids: string[];
  graph_node_ids: string[];
  citation_refs: string[];
  summary: string;
}

export interface RecommendedAction {
  action_id: string;
  order: number;
  params: Record<string, unknown>;
  rationale: string;
}

export interface Detection {
  detection_id: string;
  simulation_id: string;
  created_at: string;
  threat_class: string;
  title: string;
  severity: Severity;
  confidence: number;
  confidence_band: string;
  mitre: string[];
  owasp: string[];
  attack_path: Array<{
    node_id: string;
    label: string;
    kind: string;
    foothold_state: string;
  }>;
  evidence: EvidenceItem[];
  rationale: string;
  recommended_actions: RecommendedAction[];
  source: DetectionSource;
  validated: boolean;
}

export interface EventPage {
  items: CanonicalEvent[];
  cursor: number;
  has_more: boolean;
  total: number;
}

export interface GraphView {
  simulation_id: string;
  seq: number;
  nodes: Array<{
    id: string;
    kind: string;
    type: string | null;
    label: string;
    attrs: Record<string, unknown>;
    foothold_state: string;
  }>;
  edges: Array<{
    id: string;
    from: string;
    to: string;
    type: string;
    attrs: Record<string, unknown>;
    active: boolean;
  }>;
  overlay_footholds: unknown[];
}

export interface WSTicket {
  ticket: string;
  expires_in: number;
}

export interface MeResponse {
  user_id: string;
  email: string;
  org: { id: string; name: string; slug: string; default_density: string };
  role: string;
}

// ---- WS frames (docs/08 §5.2) ----
export interface WSEventUpsert {
  kind: "event.upsert";
  event: CanonicalEvent;
}
export interface WSEventBatch {
  kind: "event.batch";
  events: CanonicalEvent[];
  frames: unknown[];
  count: number;
}
export interface WSDetectionCreated {
  kind: "detection.created";
  detection: Detection;
}
export interface WSSimStatus {
  kind: "sim.status";
  status: string;
  phase?: string;
  reason?: string;
}
export interface WSLag {
  kind: "sim.lag";
  lag_ms: number;
}
export interface WSActionExecuted {
  kind: "action.executed";
  execution_id: string;
  detection_id: string;
  action_id: string;
  events_emitted: number;
}
export interface WSHello {
  kind: "hello";
  channel: string;
  server_time_ms: number;
}

// ---- missions (docs/14) ----
export interface MissionObjective {
  id: string;
  title: string;
  kind: string;
  points: number;
}

export interface MissionDetail {
  id: string;
  title: string;
  subtitle: string;
  simulator: string;
  scenario_id: string;
  duration_sec: number;
  objectives: MissionObjective[];
  max_score: number;
  shareable: boolean;
}

export interface MissionStarted {
  simulation_id: string;
  mission_id: string;
  ws_channel: string;
  share_url: string | null;
  status: string;
}

export interface ObjectiveResult {
  objective_id: string;
  achieved: boolean;
  points: number;
  detail: string;
}

export interface MissionScore {
  mission_id: string;
  score: number;
  max_score: number;
  final: boolean;
  objectives: ObjectiveResult[];
}

export interface PublicMissionView extends MissionDetail {
  simulation_id: string;
  sim_status: string;
  started_at: string | null;
  ended_at: string | null;
}

// ---- billing (docs/16) ----
export interface Entitlements {
  max_concurrent_sims: number;
  ai_tier: string;
  sim_minutes_month?: number;
  missions_month?: number;
  retention_days?: number;
  public_mission_links_per_day?: number;
}

export interface PeriodUsage {
  sim_minutes?: number;
  llm_tokens?: number;
  llm_calls?: number;
  missions_started?: number;
  exports?: number;
}

export interface BillingPlan {
  plan: string;
  entitlements: Entitlements;
  current_period_usage: PeriodUsage;
}

export type WSFrame =
  | WSEventUpsert
  | WSEventBatch
  | WSDetectionCreated
  | WSSimStatus
  | WSLag
  | WSActionExecuted
  | WSHello
  | { kind: "pong" }
  | { kind: "subscribed"; channel: string }
  | { kind: "error"; code: string; detail: string };
