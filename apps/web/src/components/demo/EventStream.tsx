/**
 * Event Stream panel (04 §Step 2 Panel 1): reverse-chronological list,
 * human-readable event type, severity badge, monospace timestamp.
 */

import type { DemoEvent } from "@/lib/demo/types";
import { SEV_BORDER, SEV_BG, SEV_TEXT } from "@/lib/ui/severity";
import type { Severity } from "@/lib/api/types";

const EVENT_LABEL: Record<string, string> = {
  LOGIN_FAILED: "Failed login",
  LOGIN_SUCCESS: "Successful login",
  PRIVILEGE_ESCALATION: "Privilege escalation",
  DB_ACCESS: "Database access",
  DATA_TRANSFER: "Data transfer",
  CONTAINMENT_EXECUTED: "Containment executed",
};

const EVENT_SEVERITY: Record<string, Severity> = {
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
};

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  const s = String(d.getSeconds()).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function parseEventContext(ev: DemoEvent): string {
  const ctx = ev.raw_context || {};
  switch (ev.event_type) {
    case "LOGIN_FAILED":
      return `Failed login attempt #${ctx.attempt || "?"} (${ctx.reason || "unknown"})`;
    case "LOGIN_SUCCESS":
      return `Successful login via ${ctx.auth_method || "unknown"}`;
    case "PRIVILEGE_ESCALATION":
      return `Escalated privileges to ${ctx.new_role || "unknown"}`;
    case "DB_ACCESS":
      return `Database query: ${ctx.query || "unknown"}`;
    case "DATA_TRANSFER":
      return `Data transfer: ${ctx.bytes_sent || "?"} bytes to ${ctx.destination || "unknown"}`;
    case "CONTAINMENT_EXECUTED":
      return `Containment applied: ${ctx.action_id || "unknown"}`;
    default:
      return EVENT_LABEL[ev.event_type] ?? ev.event_type;
  }
}

export function EventStream({ events }: { events: DemoEvent[] }) {
  const rows = [...events].reverse();
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {rows.length === 0 && (
        <p className="text-cs-text-tertiary p-4 text-sm">
          No events yet — start the simulation to watch the attack unfold.
        </p>
      )}
      {rows.map((ev) => {
        const sev = EVENT_SEVERITY[ev.severity] ?? "info";
        return (
          <article
            key={ev.event_id}
            className={`border-cs-border-subtle border-b border-l-2 px-2 py-1.5 animate-slide-in ${SEV_BORDER[sev]}`}
          >
            <div className="flex items-center gap-2">
              <span className="text-cs-text-tertiary shrink-0 font-mono text-xs">
                {fmtTime(ev.timestamp)}
              </span>
              <span
                className={`rounded-cs-xs inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-medium ${SEV_TEXT[sev]} ${SEV_BG[sev]}`}
              >
                {ev.severity.toLowerCase()}
              </span>
              <span className="text-cs-text-secondary truncate text-sm" title={parseEventContext(ev)}>
                {parseEventContext(ev)}
              </span>
              <span className="text-cs-text-quaternary ml-auto shrink-0 font-mono text-xs">
                {ev.target_asset}
              </span>
            </div>
            <p className="text-cs-text-quaternary mt-0.5 ml-0 font-mono text-[11px]">
              {ev.source_ip} → {ev.actor}
            </p>
          </article>
        );
      })}
    </div>
  );
}
