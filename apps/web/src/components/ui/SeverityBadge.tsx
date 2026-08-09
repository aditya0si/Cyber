/** Severity badge (docs/02 §3.2 — color + glyph + label; never color-only). */

import type { Severity } from "@/lib/api/types";
import { SEV_BG, SEV_TEXT } from "@/lib/ui/severity";

const GLYPH: Record<Severity, string> = {
  info: "○",
  low: "◇",
  medium: "▽",
  high: "△",
  critical: "✕",
};

const LABEL: Record<Severity, string> = {
  info: "info",
  low: "low",
  medium: "medium",
  high: "high",
  critical: "critical",
};

export function SeverityBadge({
  severity,
  className,
}: {
  severity: Severity;
  className?: string;
}) {
  return (
    <span
      className={`rounded-cs-xs inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-medium ${SEV_TEXT[severity]} ${SEV_BG[severity]} ${className ?? ""}`}
      aria-label={`severity ${LABEL[severity]}`}
    >
      <span aria-hidden>{GLYPH[severity]}</span>
      {LABEL[severity]}
    </span>
  );
}

export function StatusDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="text-cs-text-tertiary inline-flex items-center gap-1.5 text-xs">
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{ backgroundColor: `var(--cs-${color}-fg)` }}
        aria-hidden
      />
      {label}
    </span>
  );
}
