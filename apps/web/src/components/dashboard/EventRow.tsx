/** EventRow — uses narrative system for human-readable display. */

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { clsx } from "clsx";

import type { CanonicalEvent } from "@/lib/api/types";
import { buildNarrative } from "@/lib/sim/eventNarrative";

const SEV_BORDER: Record<string, string> = {
  CRITICAL: "border-red-500",
  HIGH: "border-orange-400",
  MEDIUM: "border-yellow-400",
  LOW: "border-slate-600",
  INFO: "border-slate-700",
};

export function EventRow({
  event,
  highlighted,
  onSelect,
}: {
  event: CanonicalEvent;
  highlighted?: boolean;
  onSelect?: (event: CanonicalEvent) => void;
}) {
  const [open, setOpen] = useState(false);
  const narrative = buildNarrative(event);
  const sev = event.severity?.toUpperCase() ?? "LOW";
  const ctx = event.raw_context as Record<string, unknown>;
  const benign = Boolean(ctx?.benign ?? false);

  return (
    <article
      className={clsx(
        "border-b border-white/5 px-2 py-1.5 hover:bg-white/4",
        highlighted && "bg-white/8",
        !benign && sev !== "LOW" && sev !== "INFO" && `border-l-2 ${SEV_BORDER[sev] ?? "border-slate-600"}`,
      )}
      aria-label={`event ${narrative.headline}`}
    >
      <button
        className="flex w-full items-center gap-2 text-left"
        onClick={() => {
          setOpen((o) => !o);
          onSelect?.(event);
        }}
        aria-expanded={open}
      >
        <ChevronRight
          className={clsx(
            "text-slate-600 h-3 w-3 shrink-0 transition-transform",
            open && "rotate-90",
          )}
          aria-hidden
        />
        <span className="text-slate-500 shrink-0 font-mono text-xs">
          {new Date(event.timestamp).toLocaleTimeString()}
        </span>
        <span className={clsx(
          "shrink-0 font-mono text-xs",
          benign ? "text-slate-600" : sev === "CRITICAL" ? "text-red-400" : sev === "HIGH" ? "text-orange-400" : sev === "MEDIUM" ? "text-yellow-400" : "text-slate-500"
        )}>
          {sev}
        </span>
        <span className="text-slate-400 shrink-0 font-mono text-xs">
          {event.source_ip}
        </span>
        <span className={clsx("truncate text-sm", benign ? "text-slate-500" : "text-slate-200")}>
          {narrative.headline}
        </span>
      </button>

      {open && (
        <pre className="rounded bg-white/4 text-slate-300 mt-1 ml-5 overflow-x-auto p-2 font-mono text-xs">
          {narrative.payloadSummary}
        </pre>
      )}
    </article>
  );
}
