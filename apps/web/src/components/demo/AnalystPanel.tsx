/**
 * AI Security Analyst panel (04 §Step 2 Panel 3): threat card from
 * `POST /analyst/analyze`; Explain / Recommended Response expand views;
 * `Execute Response` is the human-approval gate → `POST /analyst/approve-response`.
 */

import { useState } from "react";
import { clsx } from "clsx";

import type { AnalysisResponse } from "@/lib/demo/types";
import { Button } from "@/components/ui/Button";
import { SEV_BORDER, SEV_TEXT } from "@/lib/ui/severity";
import type { Severity } from "@/lib/api/types";

const THREAT_SEVERITY: Record<string, Severity> = {
  low: "low",
  medium: "medium",
  high: "high",
  critical: "critical",
};

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="bg-cs-neutral-4 h-1.5 w-24 overflow-hidden rounded-full" aria-hidden>
        <div className="bg-cs-accent-fg h-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-cs-text-secondary font-mono text-xs">{pct}%</span>
    </div>
  );
}

export function AnalystPanel({
  analysis,
  status,
  executing,
  onExecute,
  onReset,
}: {
  analysis: AnalysisResponse | null;
  status: "idle" | "analyzing" | "awaiting_approval" | "contained" | "none";
  executing: boolean;
  onExecute: () => void;
  onReset: () => void;
}) {
  const [view, setView] = useState<"summary" | "explain" | "response">("summary");
  const [confirming, setConfirming] = useState(false);

  if (status === "idle" || status === "analyzing") {
    return (
      <div className="text-cs-text-tertiary p-4 text-sm">
        {status === "analyzing"
          ? "Analyst is correlating events, querying the attack graph, and retrieving evidence…"
          : "The analyst will assess the event stream once the simulation starts."}
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="text-cs-text-tertiary p-4 text-sm">
        No threat detected yet — keep watching the event stream.
      </div>
    );
  }

  const card = analysis.threat_card;
  const sev = THREAT_SEVERITY[card.severity] ?? "medium";

  return (
    <div className="flex min-h-0 flex-col p-3">
      <div className={clsx("rounded-cs-md border-l-2 bg-cs-neutral-2 p-3", SEV_BORDER[sev])}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span className={clsx("text-lg font-bold uppercase", SEV_TEXT[sev])}>
                {card.severity}
              </span>
              <span className="text-cs-text-primary text-sm font-semibold">
                {card.threat_class.replace(/_/g, " ")}
              </span>
              {status === "contained" && (
                <span className="rounded-cs-xs bg-cs-ok-bg text-cs-ok-fg px-1.5 py-0.5 font-mono text-xs">
                  CONTAINED
                </span>
              )}
            </div>
            <p className="text-cs-text-tertiary mt-0.5 font-mono text-xs">
              {card.threat_class}
            </p>
          </div>
          <ConfidenceBar value={card.confidence} />
        </div>

        {/* Evidence */}
        <p className="text-cs-text-secondary mt-3 text-xs font-semibold uppercase">
          Evidence
        </p>
        <ul className="mt-1 space-y-1">
          {card.evidence.map((ev, i) => (
            <li key={i} className="text-cs-text-secondary text-xs">
              <span className="text-cs-text-primary">• </span>
              {ev}
            </li>
          ))}
        </ul>

        {/* Attack path */}
        {card.attack_path.length > 0 && (
          <>
            <p className="text-cs-text-secondary mt-3 text-xs font-semibold uppercase">
              Attack path
            </p>
            <p className="text-cs-text-primary mt-1 font-mono text-xs">
              {card.attack_path.join(" → ")}
            </p>
          </>
        )}

        {/* Explain */}
        {view === "explain" && card.rationale && (
          <p className="text-cs-text-secondary mt-3 border-t border-cs-border-subtle pt-2 text-xs italic">
            {card.rationale}
          </p>
        )}

        {/* Recommended response */}
        {view === "response" && (
          <ol className="mt-3 list-decimal space-y-1.5 border-t border-cs-border-subtle pl-4 pt-2">
            {analysis.recommended_actions.map((a) => (
              <li key={a.action_id} className="text-xs">
                <span className="text-cs-text-primary font-mono">
                  {a.action_id.replace(/_/g, " ")}
                </span>
                <p className="text-cs-text-tertiary">{a.rationale}</p>
              </li>
            ))}
          </ol>
        )}
      </div>

      {/* Controls */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setView(view === "explain" ? "summary" : "explain")}
        >
          {view === "explain" ? "Hide explanation" : "Explain"}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setView(view === "response" ? "summary" : "response")}
        >
          {view === "response" ? "Hide response" : "Recommended response"}
        </Button>
        {status === "awaiting_approval" &&
          (confirming ? (
            <span className="flex items-center gap-2">
              <Button size="sm" variant="danger" disabled={executing} onClick={onExecute}>
                {executing ? "Executing…" : "Confirm — execute response"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </span>
          ) : (
            <Button size="sm" variant="danger" onClick={() => setConfirming(true)}>
              Execute Response
            </Button>
          ))}
        {status === "contained" && (
          <Button size="sm" variant="secondary" onClick={onReset}>
            Reset
          </Button>
        )}
      </div>
    </div>
  );
}
