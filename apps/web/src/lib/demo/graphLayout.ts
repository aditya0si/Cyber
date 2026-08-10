/**
 * Backend snapshot → React Flow nodes/edges, auto-laid-out with dagre.
 * Environment-layer nodes flow left→right; overlay (attack-narrative) nodes
 * attach around their anchors. Node color encodes kind, border encodes
 * foothold state, so containment is visible at a glance (04 §Step 2).
 */

import dagre from "dagre";
import type { Edge, Node } from "reactflow";

import type { GraphNode, GraphSnapshot } from "./types";

const NODE_WIDTH = 170;
const NODE_HEIGHT = 46;

const KIND_BORDER: Record<string, string> = {
  ASSET: "var(--cs-sev-info-fg)",
  SERVICE: "var(--cs-accent-fg)",
  CREDENTIAL: "var(--cs-sev-medium-fg)",
  DATA: "var(--cs-sev-high-fg)",
  NETWORK_ZONE: "var(--cs-sev-critical-fg)",
  USER: "var(--cs-sev-critical-fg)",
  ATTACK: "var(--cs-sev-critical-fg)",
  EVENT: "var(--cs-sev-info-fg)",
  VULNERABILITY: "var(--cs-sev-medium-fg)",
};

const FOOTHOLD_BORDER: Record<string, string> = {
  compromised: "var(--cs-sev-critical-fg)",
  foothold: "var(--cs-sev-critical-fg)",
  contained: "var(--cs-ok-fg)",
  quarantined: "var(--cs-ok-fg)",
  attempted: "var(--cs-sev-medium-fg)",
  recon: "var(--cs-sev-medium-fg)",
};

const FOOTHOLD_LABEL: Record<string, string> = {
  compromised: "compromised",
  foothold: "foothold",
  contained: "contained",
  quarantined: "quarantined",
  attempted: "attempted",
  recon: "recon",
};

export function nodeStateLabel(node: GraphNode): string {
  const status = String(node.attrs.status ?? "");
  if (status) return status;
  return FOOTHOLD_LABEL[node.foothold_state] ?? "";
}

export function toReactFlow(snap: GraphSnapshot): {
  nodes: Node[];
  edges: Edge[];
} {
  const nodes: Node[] = snap.nodes.map((n) => {
    const kindBorder = KIND_BORDER[n.kind] ?? "var(--cs-border-strong)";
    const stateBorder = FOOTHOLD_BORDER[n.foothold_state];
    const stateLabel = nodeStateLabel(n);
    return {
      id: n.id,
      position: { x: 0, y: 0 },
      data: {
        label: n.label,
        kind: n.kind,
        state: n.foothold_state,
        stateLabel,
      },
      style: {
        width: NODE_WIDTH,
        minHeight: NODE_HEIGHT,
        background: "var(--cs-neutral-2)",
        color: "var(--cs-text-primary)",
        border: `2px solid ${stateBorder ?? kindBorder}`,
        borderRadius: 6,
        fontFamily: "var(--cs-font-mono)",
        fontSize: 12,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "4px 8px",
      },
    };
  });

  const envEdges: Edge[] = snap.edges
    .filter((e) => e.active)
    .map((e) => ({
      id: `env-${e.id}`,
      source: e.from,
      target: e.to,
      type: "smoothstep",
      style: {
        stroke: "var(--cs-border-strong)",
        strokeWidth: 1.5,
      },
      label: e.type,
      labelStyle: {
        fill: "var(--cs-text-quaternary)",
        fontSize: 9,
        fontFamily: "var(--cs-font-mono)",
      },
    }));

  const overlayEdges: Edge[] = snap.overlay_edges
    .filter((e) => e.active)
    .map((e) => ({
      id: `ov-${e.id}`,
      source: e.from,
      target: e.to,
      type: "smoothstep",
      animated: true,
      style: {
        stroke: "var(--cs-sev-critical-fg)",
        strokeWidth: 2,
        strokeDasharray: "6 4",
      },
      label: e.kind,
      labelStyle: {
        fill: "var(--cs-sev-critical-fg)",
        fontSize: 9,
        fontFamily: "var(--cs-font-mono)",
      },
    }));

  const laidOut = layout(nodes, envEdges.concat(overlayEdges));
  return { nodes: laidOut.nodes, edges: laidOut.edges };
}

function layout(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", ranksep: 90, nodesep: 36, marginx: 24, marginy: 24 });

  for (const n of nodes) g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  for (const e of edges) g.setEdge(e.source, e.target);

  dagre.layout(g);

  const positioned = nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
    };
  });
  return { nodes: positioned, edges };
}
