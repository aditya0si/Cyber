/** EventRow (docs/02 §4.3): severity dot · time · source · subtype · summary. */

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { clsx } from "clsx";

import type { CanonicalEvent } from "@/lib/api/types";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import { SEV_BORDER } from "@/lib/ui/severity";

function fmtTime(ms: number): string {
  const s = Math.floor(ms / 1000);
  const h = String(Math.floor(s / 3600)).padStart(2, "0");
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const sec = String(s % 60).padStart(2, "0");
  return `${h}:${m}:${sec}`;
}

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

  return (
    <article
      className={clsx(
        "border-cs-border-subtle hover:bg-cs-neutral-3 border-b px-2 py-1",
        highlighted && "bg-cs-accent-bg",
        event.severity_hint !== "info" &&
          `border-l-2 ${SEV_BORDER[event.severity_hint]}`,
      )}
      aria-label={`event ${event.subtype}`}
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
            "text-cs-text-tertiary h-3 w-3 shrink-0 transition-transform",
            open && "rotate-90",
          )}
          aria-hidden
        />
        <span className="text-cs-text-tertiary shrink-0 font-mono text-xs">
          {fmtTime(event.sim_time_ms)}
        </span>
        <SeverityBadge severity={event.severity_hint} />
        <span className="text-cs-text-tertiary shrink-0 font-mono text-xs">
          {event.source_node_id ?? event.origin}
        </span>
        <span className="truncate text-sm">{event.subtype}</span>
        {event.correlation_key && (
          <span className="text-cs-text-quaternary ml-auto hidden shrink-0 font-mono text-xs md:inline">
            {event.correlation_key}
          </span>
        )}
      </button>

      {open && (
        <pre className="rounded-cs-sm bg-cs-neutral-1 text-cs-text-secondary mt-1 ml-5 overflow-x-auto p-2 font-mono text-xs">
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      )}
    </article>
  );
}
