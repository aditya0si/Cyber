/** StatusBar (docs/14 §3.1 bottom): sim time · elapsed · health · audit · score. */

"use client";

import { Activity, CheckCircle2, XCircle, PauseCircle } from "lucide-react";

import type { ExecutedAction } from "./useMissionSession";

function fmtClock(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = String(Math.floor(s / 3600)).padStart(2, "0");
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const sec = String(s % 60).padStart(2, "0");
  return `${h}:${m}:${sec}`;
}

const DEFAULT_META = {
  label: "queued",
  icon: Activity,
  tone: "text-cs-text-tertiary",
};

const STATUS_META: Record<string, typeof DEFAULT_META> = {
  queued: DEFAULT_META,
  running: { label: "healthy", icon: CheckCircle2, tone: "text-cs-ok-fg" },
  paused: { label: "paused", icon: PauseCircle, tone: "text-cs-warn-fg" },
  completed: { label: "completed", icon: CheckCircle2, tone: "text-cs-ok-fg" },
  failed: { label: "failed", icon: XCircle, tone: "text-cs-error-fg" },
  stopped: { label: "stopped", icon: XCircle, tone: "text-cs-warn-fg" },
};

export function StatusBar({
  status,
  simTimeMs,
  elapsedSec,
  durationSec,
  score,
  lastAction,
}: {
  status: string;
  simTimeMs: number;
  elapsedSec: number;
  durationSec: number;
  score: { score: number; max_score: number; final: boolean } | null;
  lastAction: ExecutedAction | null;
}) {
  const meta = STATUS_META[status] ?? DEFAULT_META;
  const Icon = meta.icon;
  const pct = Math.min(100, (simTimeMs / 1000 / durationSec) * 100);

  return (
    <div className="border-cs-border-subtle bg-cs-neutral-1 flex h-9 items-center gap-4 border-t px-3 text-xs">
      <span className="flex items-center gap-1.5">
        <Icon className={`h-3.5 w-3.5 ${meta.tone}`} aria-hidden />
        <span className={meta.tone}>{meta.label}</span>
      </span>
      <span className="text-cs-text-secondary font-mono">
        sim {fmtClock(simTimeMs)} / {fmtClock(durationSec * 1000)}
      </span>
      <div
        className="bg-cs-neutral-4 h-1.5 min-w-24 flex-1 overflow-hidden rounded-full"
        aria-hidden
      >
        <div className="bg-cs-accent-fg h-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-cs-text-tertiary font-mono">
        wall {fmtClock(elapsedSec * 1000)}
      </span>
      {lastAction && (
        <span className="text-cs-text-tertiary hidden truncate font-mono md:inline">
          last action: {lastAction.action_id.replace(/_/g, " ")}
        </span>
      )}
      <span className="ml-auto shrink-0 font-mono">
        <span className="text-cs-accent-fg text-base font-bold">
          {score?.score ?? 0}
        </span>
        <span className="text-cs-text-tertiary">
          /{score?.max_score ?? 100}
        </span>
        {score?.final && (
          <span className="text-cs-text-quaternary ml-1">final</span>
        )}
      </span>
    </div>
  );
}
