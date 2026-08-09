/** ObjectiveList (docs/14 §3.1 left): auto-eval checkboxes + points. */

"use client";

import { Check, Circle } from "lucide-react";
import { clsx } from "clsx";

import type { MissionObjective } from "@/lib/api/types";

export function ObjectiveList({
  objectives,
  achievedMap,
}: {
  objectives: MissionObjective[];
  achievedMap: Map<string, boolean>;
}) {
  return (
    <ul className="space-y-2.5">
      {objectives.map((o) => {
        const achieved = achievedMap.get(o.id) ?? false;
        return (
          <li key={o.id} className="flex items-start gap-2 text-sm">
            <span
              className={clsx(
                "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
                achieved
                  ? "border-cs-ok-fg bg-cs-ok-bg text-cs-ok-fg"
                  : "border-cs-border-strong text-cs-text-quaternary",
              )}
              aria-label={achieved ? "objective achieved" : "objective pending"}
            >
              {achieved ? (
                <Check className="h-3 w-3" aria-hidden />
              ) : (
                <Circle className="h-2 w-2" aria-hidden />
              )}
            </span>
            <div>
              <p className={clsx(achieved && "text-cs-ok-fg")}>{o.title}</p>
              <p className="text-cs-text-quaternary font-mono text-xs">
                {o.points} pts
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
