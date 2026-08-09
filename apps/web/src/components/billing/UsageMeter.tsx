/** UsageMeter (docs/16 §6): current-period usage vs cap bar. */

"use client";

import { clsx } from "clsx";

export function UsageMeter({
  label,
  used,
  cap,
  format,
}: {
  label: string;
  used: number;
  cap: number;
  format?: (value: number) => string;
}) {
  const pct = cap > 0 ? Math.min(100, Math.round((used / cap) * 100)) : 0;
  const fmt = format ?? ((v: number) => String(v));

  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-cs-text-secondary">{label}</span>
        <span className="text-cs-text-tertiary font-mono">
          {fmt(used)} / {fmt(cap)}
        </span>
      </div>
      <div
        className="bg-cs-neutral-4 h-1.5 overflow-hidden rounded-full"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label} usage`}
      >
        <div
          className={clsx(
            "h-full transition-[width] duration-500",
            pct >= 90 ? "bg-cs-sev-critical-fg" : "bg-cs-accent-fg",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
