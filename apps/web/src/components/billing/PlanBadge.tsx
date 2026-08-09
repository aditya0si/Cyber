/** PlanBadge (docs/16 §6): current plan chip. */

"use client";

import { clsx } from "clsx";

const PLAN_STYLE: Record<string, string> = {
  free: "bg-cs-neutral-3 text-cs-text-secondary",
  trial: "bg-cs-warn-bg text-cs-warn-fg",
  pro: "bg-cs-accent-bg text-cs-accent-fg",
  enterprise: "border border-cs-border-strong text-cs-text-primary",
};

export function PlanBadge({ plan }: { plan: string }) {
  return (
    <span
      className={clsx(
        "rounded-cs-xs px-1.5 py-0.5 font-mono text-xs capitalize",
        PLAN_STYLE[plan] ?? PLAN_STYLE.free,
      )}
    >
      {plan}
    </span>
  );
}
