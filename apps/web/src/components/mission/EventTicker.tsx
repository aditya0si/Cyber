/** EventTicker (docs/14 §3.1 center): live event stream rows. */

"use client";

import type { CanonicalEvent } from "@/lib/api/types";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import { clsx } from "clsx";


export function EventTicker({
  events,
  selectedId,
  onSelect,
  streaming,
}: {
  events: CanonicalEvent[];
  selectedId: string | null;
  onSelect: (event: CanonicalEvent) => void;
  streaming: boolean;
}) {
  if (events.length === 0) {
    return (
      <p className="text-cs-text-tertiary p-4 text-sm">
        {streaming ? "Events streaming in…" : "No events yet."}
      </p>
    );
  }

  return (
    <div className="flex flex-col">
      {[...events]
        .reverse()
        .slice(0, 300)
        .map((ev) => (
          <button
            key={ev.event_id}
            onClick={() => onSelect(ev)}
            className={clsx(
              "border-cs-border-subtle hover:bg-cs-neutral-3 flex items-center gap-2 border-b px-2 py-1 text-left",
              selectedId === ev.event_id && "bg-cs-accent-bg",
            )}
            aria-label={`event ${ev.event_type}`}
          >
            <span className="text-cs-text-tertiary shrink-0 font-mono text-xs">
              {new Date(ev.timestamp).toLocaleTimeString()}
            </span>
            <SeverityBadge severity={ev.severity.toLowerCase() as any} />
            <span className="text-cs-text-tertiary shrink-0 font-mono text-xs">
              {ev.source_ip}
            </span>
            <span className="truncate text-sm">{ev.event_type}</span>
          </button>
        ))}
    </div>
  );
}
