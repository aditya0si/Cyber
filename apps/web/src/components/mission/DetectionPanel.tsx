/** DetectionPanel (docs/14 §3.1 center): pinned "current" detection + history scroller. */

"use client";

import { clsx } from "clsx";

import type { Detection } from "@/lib/api/types";
import { Card } from "@/components/ui/Card";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import { Button } from "@/components/ui/Button";
import { SEV_BORDER } from "@/lib/ui/severity";

function ConfidencePct({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <span className="text-cs-text-secondary font-mono text-xs">{pct}%</span>
  );
}

export function DetectionPanel({
  detections,
  selectedDetectionId,
  onSelect,
  onExecute,
}: {
  detections: Detection[];
  selectedDetectionId: string | null;
  onSelect: (detection: Detection) => void;
  onExecute: (detection: Detection) => void;
}) {
  if (detections.length === 0) {
    return (
      <div className="text-cs-text-tertiary p-4 text-sm">
        No threats detected yet — watching…
      </div>
    );
  }

  const pinned = detections[detections.length - 1]!;
  const history = detections.slice(0, -1);

  return (
    <div className="space-y-2 p-3">
      {/* Pinned current detection */}
      <Card className={clsx("border-l-2 p-3", SEV_BORDER[pinned.severity])}>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <SeverityBadge severity={pinned.severity} />
            <span className="text-sm font-semibold">{pinned.title}</span>
            <span className="rounded-cs-xs bg-cs-accent-bg text-cs-accent-fg px-1.5 py-0.5 font-mono text-xs">
              {pinned.threat_class}
            </span>
          </div>
          <ConfidencePct value={pinned.confidence} />
        </div>

        {pinned.attack_path.length > 0 && (
          <div className="text-cs-text-secondary mt-2 flex flex-wrap items-center gap-1 font-mono text-xs">
            {pinned.attack_path.map((node, i) => (
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

        {pinned.evidence.length > 0 && (
          <ul className="mt-2 space-y-1">
            {pinned.evidence.slice(0, 3).map((ev) => (
              <li key={ev.label} className="text-cs-text-secondary text-xs">
                <span className="text-cs-text-primary">• {ev.label}</span>
                <span className="text-cs-text-quaternary ml-2 font-mono">
                  [{ev.kind}]
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-3 flex items-center gap-2">
          <Button size="sm" variant="primary" onClick={() => onExecute(pinned)}>
            Open response
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onSelect(pinned)}>
            Inspect
          </Button>
        </div>
      </Card>

      {/* Past detections scroller */}
      {history.length > 0 && (
        <div>
          <p className="text-cs-text-tertiary mb-1 text-xs font-medium tracking-wide uppercase">
            Past detections
          </p>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {[...history].reverse().map((d) => (
              <button
                key={d.detection_id}
                onClick={() => onSelect(d)}
                className={clsx(
                  "rounded-cs-xs shrink-0 border px-2 py-1 text-left font-mono text-xs",
                  selectedDetectionId === d.detection_id
                    ? "border-cs-accent-fg text-cs-accent-fg"
                    : "border-cs-border-default text-cs-text-secondary hover:bg-cs-neutral-3",
                )}
                aria-label={`past detection ${d.title}`}
              >
                {d.title.slice(0, 28)}
                <span className="text-cs-text-quaternary ml-1">
                  {Math.round(d.confidence * 100)}%
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
