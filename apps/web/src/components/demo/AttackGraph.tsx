/**
 * Attack Graph panel (04 §Step 2 Panel 2): React Flow canvas fed by
 * `GET /graph`. Node color = kind, border = foothold state; animated dashed
 * edges are the attack-narrative overlay links.
 */

import { useMemo } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";

import { toReactFlow, nodeStateLabel } from "@/lib/demo/graphLayout";
import type { GraphSnapshot } from "@/lib/demo/types";

const STATE_TEXT: Record<string, string> = {
  compromised: "var(--cs-sev-critical-fg)",
  foothold: "var(--cs-sev-critical-fg)",
  contained: "var(--cs-ok-fg)",
  quarantined: "var(--cs-ok-fg)",
  attempted: "var(--cs-sev-medium-fg)",
  recon: "var(--cs-sev-medium-fg)",
};

function FlowNode({ data }: NodeProps) {
  const kind = String(data.kind ?? "");
  const stateLabel = String(data.stateLabel ?? "");
  return (
    <>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div className="text-cs-text-primary px-2 text-center font-mono text-xs leading-tight">
        <div className="font-semibold">{String(data.label ?? "")}</div>
        <div className="text-cs-text-quaternary text-[10px]">
          {kind.toLowerCase()}
          {stateLabel && (
            <span
              className="ml-1.5 font-semibold"
              style={{ color: STATE_TEXT[String(data.state)] ?? "var(--cs-text-quaternary)" }}
            >
              · {stateLabel}
            </span>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </>
  );
}

const nodeTypes = { default: FlowNode };

export function AttackGraph({ snap }: { snap: GraphSnapshot | null }) {
  const { nodes, edges } = useMemo(
    () => (snap ? toReactFlow(snap) : { nodes: [], edges: [] }),
    [snap],
  );

  return (
    <div className="bg-cs-neutral-1 min-h-0 flex-1">
      {snap === null && (
        <p className="text-cs-text-tertiary p-4 text-sm">
          Attack graph will render here once the simulation starts.
        </p>
      )}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesConnectable={false}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

export { nodeStateLabel };
