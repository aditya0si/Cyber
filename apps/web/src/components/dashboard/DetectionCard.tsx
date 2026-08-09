/** DetectionCard (docs/02 §4.4) — the evidence-grounded AI decision surface. */

import { useState } from "react";

import type { Detection } from "@/lib/api/types";
import { Card } from "@/components/ui/Card";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import { Button } from "@/components/ui/Button";
import { api, authedRequest } from "@/lib/api/client";
import { SEV_BORDER } from "@/lib/ui/severity";

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div
        className="bg-cs-neutral-4 h-1.5 w-24 overflow-hidden rounded-full"
        aria-hidden
      >
        <div className="bg-cs-accent-fg h-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-cs-text-secondary font-mono text-xs">{pct}%</span>
    </div>
  );
}

export function DetectionCard({
  detection,
  onExecute,
}: {
  detection: Detection;
  onExecute?: (detection: Detection, actionId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className={`mb-3 border-l-2 p-3 ${SEV_BORDER[detection.severity]}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <SeverityBadge severity={detection.severity} />
            <span className="text-sm font-semibold">{detection.title}</span>
            <span className="rounded-cs-xs bg-cs-accent-bg text-cs-accent-fg px-1.5 py-0.5 font-mono text-xs">
              {detection.source}
            </span>
          </div>
          <p className="text-cs-text-tertiary mt-1 font-mono text-xs">
            {detection.threat_class} · {detection.detection_id}
          </p>
        </div>
        <ConfidenceBar value={detection.confidence} />
      </div>

      {/* Attack path */}
      {detection.attack_path.length > 0 && (
        <div className="text-cs-text-secondary mt-2 flex flex-wrap items-center gap-1 font-mono text-xs">
          {detection.attack_path.map((node, i) => (
            <span
              key={`${node.node_id}-${i}`}
              className="flex items-center gap-1"
            >
              {i > 0 && <span aria-hidden>→</span>}
              <span
                className={
                  node.foothold_state === "compromised"
                    ? "text-cs-sev-critical-fg"
                    : undefined
                }
              >
                {node.label}
              </span>
            </span>
          ))}
        </div>
      )}

      {/* Evidence */}
      <button
        className="text-cs-accent-fg mt-2 text-xs font-medium hover:underline"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
      >
        Evidence ({detection.evidence.length})
      </button>
      {expanded && (
        <ul className="mt-1 space-y-1">
          {detection.evidence.map((ev) => (
            <li key={ev.label} className="text-cs-text-secondary text-xs">
              <span className="text-cs-text-primary">• {ev.label}</span>
              <span className="text-cs-text-quaternary ml-2 font-mono">
                [{ev.kind} · {Math.round(ev.weight * 100)}%]
              </span>
              <p className="text-cs-text-tertiary ml-4">{ev.summary}</p>
            </li>
          ))}
        </ul>
      )}

      {/* Recommended actions */}
      <div className="mt-3 flex flex-wrap gap-2">
        {detection.recommended_actions.map((action) => (
          <Button
            key={action.action_id}
            size="sm"
            variant="primary"
            onClick={() => onExecute?.(detection, action.action_id)}
          >
            {action.action_id.replace(/_/g, " ")}
          </Button>
        ))}
      </div>

      {detection.rationale && (
        <p className="text-cs-text-tertiary mt-2 text-xs italic">
          {detection.rationale}
        </p>
      )}
    </Card>
  );
}
