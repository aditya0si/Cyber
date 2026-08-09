/**
 * Static severity class maps (docs/02 §3.2).
 * Tailwind JIT only scans complete literal class names — dynamic templates
 * like `text-cs-sev-${sev}-fg` never generate utilities. Use these maps.
 */

import type { Severity } from "@/lib/api/types";

export const SEV_TEXT: Record<Severity, string> = {
  info: "text-cs-sev-info-fg",
  low: "text-cs-sev-low-fg",
  medium: "text-cs-sev-medium-fg",
  high: "text-cs-sev-high-fg",
  critical: "text-cs-sev-critical-fg",
};

export const SEV_BG: Record<Severity, string> = {
  info: "bg-cs-sev-info-bg",
  low: "bg-cs-sev-low-bg",
  medium: "bg-cs-sev-medium-bg",
  high: "bg-cs-sev-high-bg",
  critical: "bg-cs-sev-critical-bg",
};

export const SEV_BORDER: Record<Severity, string> = {
  info: "border-cs-sev-info-fg",
  low: "border-cs-sev-low-fg",
  medium: "border-cs-sev-medium-fg",
  high: "border-cs-sev-high-fg",
  critical: "border-cs-sev-critical-fg",
};
