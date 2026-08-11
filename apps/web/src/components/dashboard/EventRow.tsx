/** EventRow (docs/02 §4.3): severity dot · time · source · subtype · summary. */

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { clsx } from "clsx";

import type { CanonicalEvent } from "@/lib/api/types";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import { SEV_BORDER } from "@/lib/ui/severity";


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
        event.severity.toLowerCase() !== "info" &&
          `border-l-2 ${SEV_BORDER[event.severity.toLowerCase() as Severity]}`,
      )}
      aria-label={`event ${event.event_type}`}
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
          {new Date(event.timestamp).toLocaleTimeString()}
        </span>
        <SeverityBadge severity={event.severity.toLowerCase() as Severity} />
        <span className="text-cs-text-tertiary shrink-0 font-mono text-xs">
          {event.source_ip}
        </span>
        <span className="truncate text-sm">{event.event_type}</span>
      </button>

      {open && (
        <pre className="rounded-cs-sm bg-cs-neutral-1 text-cs-text-secondary mt-1 ml-5 overflow-x-auto p-2 font-mono text-xs">
          {JSON.stringify(event.raw_context, null, 2)}
        </pre>
      )}
    </article>
  );
}
