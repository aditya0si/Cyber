/**
 * Types for the Stage 01–03 demo API surface (unauthenticated demo endpoints
 * in `cybersim/api/main.py`) — NOT the /v1 platform API.
 */

export type DemoSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ThreatSeverity = "info" | "low" | "medium" | "high" | "critical";

export interface DemoEvent {
  event_id: string;
  timestamp: string;
  event_type: string;
  severity: DemoSeverity;
  source_ip: string;
  target_asset: string;
  actor: string;
  raw_context: Record<string, unknown>;
}

export interface GraphNode {
  id: string;
  kind: string;
  type: string | null;
  label: string;
  attrs: Record<string, unknown>;
  foothold_state: string;
}

export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  type: string;
  attrs: Record<string, unknown>;
  active: boolean;
}

export interface OverlayNode {
  node_id: string;
  parent: string | null;
  state: string;
  flags: Record<string, unknown>;
}

export interface OverlayEdge {
  id: string;
  from: string;
  to: string;
  kind: string;
  active: boolean;
}

export interface GraphSnapshot {
  simulation_id: string;
  at_seq: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  overlay: OverlayNode[];
  overlay_edges: OverlayEdge[];
}

export interface RecommendedAction {
  action_id: string;
  order: number;
  params: Record<string, unknown>;
  rationale: string;
}

export interface ThreatCard {
  severity: ThreatSeverity;
  confidence: number;
  threat_class: string;
  rationale: string;
  evidence: string[];
  attack_path: string[];
}

export interface AnalysisResponse {
  threat_card: ThreatCard;
  recommended_actions: RecommendedAction[];
}
