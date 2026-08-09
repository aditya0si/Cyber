/**
 * MissionStage (docs/14 §3): the mission theater.
 * 3-column layout — objectives | event ticker + AI detection | inspector + EXECUTE —
 * with a bottom status bar and a sim-time progress bar in the header.
 */

"use client";

import { useEffect, useMemo, useState } from "react";
import { Swords, UserRound } from "lucide-react";
import { clsx } from "clsx";

import type {
  CanonicalEvent,
  Detection,
  MissionDetail,
  MissionScore,
} from "@/lib/api/types";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ObjectiveList } from "./ObjectiveList";
import { EventTicker } from "./EventTicker";
import { DetectionPanel } from "./DetectionPanel";
import { ExecuteActionDialog } from "./ExecuteActionDialog";
import { StatusBar } from "./StatusBar";
import { ShareLink } from "./ShareLink";
import type { ExecutedAction } from "./useMissionSession";

interface MissionStageProps {
  mission: MissionDetail;
  simId: string | null;
  status: string;
  events: CanonicalEvent[];
  detections: Detection[];
  score: MissionScore | null;
  lastAction: ExecutedAction | null;
  shareUrl: string | null;
  judge: boolean;
  starting: boolean;
  notice: string | null;
  onStart: () => Promise<void>;
  onExecute: (
    detection: Detection,
    actionId: string,
    confirmed: boolean,
  ) => Promise<void>;
}

type Selection =
  | { kind: "event"; event: CanonicalEvent }
  | { kind: "detection"; detection: Detection };

export function MissionStage({
  mission,
  simId,
  status,
  events,
  detections,
  score,
  lastAction,
  shareUrl,
  judge,
  starting,
  notice,
  onStart,
  onExecute,
}: MissionStageProps) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const [dialogDetection, setDialogDetection] = useState<Detection | null>(
    null,
  );
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    if (!simId) return;
    const start = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [simId]);

  const simTimeMs = useMemo(() => events.at(-1)?.sim_time_ms ?? 0, [events]);
  const progressPct = Math.min(
    100,
    (simTimeMs / 1000 / mission.duration_sec) * 100,
  );

  const achievedMap = new Map(
    (score?.objectives ?? []).map((o) => [o.objective_id, o.achieved]),
  );

  const executeButtonEnabled =
    simId !== null && selection?.kind === "detection";

  function openResponse(detection: Detection) {
    setDialogDetection(detection);
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="border-cs-border-subtle bg-cs-neutral-1 border-b px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Swords className="text-cs-accent-fg h-5 w-5" aria-hidden />
            <h1 className="text-lg font-semibold">{mission.title}</h1>
          </div>
          {judge && (
            <span className="rounded-cs-xs border-cs-border-strong text-cs-warn-fg flex items-center gap-1 border px-1.5 py-0.5 font-mono text-xs">
              <UserRound className="h-3 w-3" aria-hidden />
              JUDGE MODE
            </span>
          )}
          <p className="text-cs-text-tertiary hidden text-sm md:block">
            {mission.subtitle}
          </p>
          {shareUrl && !judge && (
            <span className="ml-auto">
              <ShareLink url={shareUrl} />
            </span>
          )}
        </div>

        {/* Sim-time progress */}
        <div className="mt-3 flex items-center gap-2">
          <div
            className="bg-cs-neutral-4 h-1.5 flex-1 overflow-hidden rounded-full"
            aria-hidden
          >
            <div
              className={clsx(
                "h-full transition-[width] duration-500",
                progressPct >= 100
                  ? "bg-cs-sev-critical-fg"
                  : "bg-cs-accent-fg",
              )}
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <span className="text-cs-text-secondary shrink-0 font-mono text-xs">
            {Math.floor(simTimeMs / 1000)}s / {mission.duration_sec}s
          </span>
        </div>
      </header>

      {notice && (
        <div className="rounded-cs-sm bg-cs-warn-bg text-cs-warn-fg m-3 px-2 py-1 text-xs">
          {notice}
        </div>
      )}

      {!simId ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-16">
          <p className="text-cs-text-secondary text-sm">
            This mission is a scored, interactive attack/defense run. You are
            the defender — respond to threats as they appear.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            {mission.objectives.map((o) => (
              <span
                key={o.id}
                className="rounded-cs-xs border-cs-border-default bg-cs-neutral-2 text-cs-text-tertiary border px-2 py-1 text-xs"
              >
                {o.title} · {o.points} pts
              </span>
            ))}
          </div>
          <Button
            variant="primary"
            size="lg"
            className="shadow-[0_0_28px_var(--cs-accent-ring)]"
            onClick={() => void onStart()}
            disabled={starting}
          >
            {starting ? <Spinner size={16} /> : "Start mission"}
          </Button>
        </div>
      ) : (
        <>
          <div className="grid min-h-0 flex-1 grid-cols-[250px_1fr_280px]">
            {/* LEFT: objectives */}
            <section className="border-cs-border-subtle flex min-h-0 flex-col border-r">
              <CardHeader title="Objectives" />
              <div className="min-h-0 flex-1 overflow-y-auto p-3">
                <ObjectiveList
                  objectives={mission.objectives}
                  achievedMap={achievedMap}
                />
                <p className="text-cs-text-quaternary mt-4 font-mono text-xs">
                  max {mission.max_score} pts
                </p>
              </div>
            </section>

            {/* CENTER: event ticker + AI detection */}
            <section className="grid min-h-0 flex-1 grid-rows-[1fr_auto]">
              <div className="border-cs-border-subtle flex min-h-0 flex-col border-b">
                <CardHeader title="Event ticker" />
                <div className="min-h-0 flex-1 overflow-y-auto">
                  <EventTicker
                    events={events}
                    selectedId={
                      selection?.kind === "event"
                        ? selection.event.event_id
                        : null
                    }
                    onSelect={(event) => setSelection({ kind: "event", event })}
                    streaming={simId !== null}
                  />
                </div>
              </div>
              <div className="flex min-h-0 flex-col">
                <CardHeader
                  title="AI analyst"
                  right={
                    <span className="text-cs-text-tertiary font-mono text-xs">
                      {detections.length} detection
                      {detections.length === 1 ? "" : "s"}
                    </span>
                  }
                />
                <div className="min-h-0 flex-1 overflow-y-auto">
                  <DetectionPanel
                    detections={detections}
                    selectedDetectionId={
                      selection?.kind === "detection"
                        ? selection.detection.detection_id
                        : null
                    }
                    onSelect={(detection) =>
                      setSelection({ kind: "detection", detection })
                    }
                    onExecute={openResponse}
                  />
                </div>
              </div>
            </section>

            {/* RIGHT: inspector + EXECUTE */}
            <section className="border-cs-border-subtle flex min-h-0 flex-col border-l">
              <CardHeader title="Inspector" />
              <div className="min-h-0 flex-1 overflow-y-auto p-3">
                {selection ? (
                  selection.kind === "event" ? (
                    <div className="space-y-2">
                      <h3 className="text-sm font-medium">
                        {selection.event.subtype}
                      </h3>
                      <p className="text-cs-text-tertiary font-mono text-xs">
                        {selection.event.event_id}
                      </p>
                      <dl className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <dt className="text-cs-text-tertiary">Origin</dt>
                          <dd>{selection.event.origin}</dd>
                        </div>
                        <div className="flex justify-between">
                          <dt className="text-cs-text-tertiary">Stage</dt>
                          <dd>{selection.event.attack_stage ?? "—"}</dd>
                        </div>
                        <div className="flex justify-between">
                          <dt className="text-cs-text-tertiary">MITRE</dt>
                          <dd className="font-mono">
                            {selection.event.mitre_techniques.join(", ") || "—"}
                          </dd>
                        </div>
                      </dl>
                      <pre className="rounded-cs-sm bg-cs-neutral-1 text-cs-text-secondary overflow-x-auto p-2 font-mono text-xs">
                        {JSON.stringify(selection.event.payload, null, 2)}
                      </pre>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <h3 className="text-sm font-medium">
                        {selection.detection.title}
                      </h3>
                      <p className="text-cs-text-tertiary font-mono text-xs">
                        {selection.detection.threat_class}
                      </p>
                      <p className="text-cs-text-secondary text-xs italic">
                        {selection.detection.rationale}
                      </p>
                      <p className="text-cs-text-quaternary text-xs">
                        confidence{" "}
                        {Math.round(selection.detection.confidence * 100)}% ·
                        source {selection.detection.source}
                      </p>
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => openResponse(selection.detection)}
                      >
                        Execute response
                      </Button>
                    </div>
                  )
                ) : (
                  <p className="text-cs-text-tertiary text-sm">
                    Select an event or a detection to inspect it.
                  </p>
                )}
              </div>

              {/* EXECUTE console */}
              <div className="border-cs-border-subtle bg-cs-neutral-1 border-t p-3">
                <p className="text-cs-text-tertiary mb-2 text-xs font-medium tracking-wide uppercase">
                  Response console
                </p>
                <button
                  className={clsx(
                    "rounded-cs-md h-14 w-full text-base font-semibold transition-all",
                    executeButtonEnabled
                      ? "bg-cs-accent-fg text-cs-text-inverse shadow-[0_0_28px_var(--cs-accent-ring)] hover:shadow-[0_0_44px_var(--cs-accent-ring)]"
                      : "bg-cs-neutral-4 text-cs-text-tertiary cursor-not-allowed",
                  )}
                  disabled={!executeButtonEnabled}
                  onClick={() => {
                    if (selection?.kind === "detection")
                      openResponse(selection.detection);
                  }}
                  aria-label="Execute response for the selected detection"
                >
                  {judge ? "EXECUTE (judge)" : "EXECUTE RESPONSE"}
                </button>
                {!executeButtonEnabled && simId !== null && (
                  <p className="text-cs-text-quaternary mt-1.5 text-center text-[11px]">
                    Select a detection to arm the console
                  </p>
                )}
              </div>
            </section>
          </div>

          <StatusBar
            status={status}
            simTimeMs={simTimeMs}
            elapsedSec={elapsedSec}
            durationSec={mission.duration_sec}
            score={score}
            lastAction={lastAction}
          />
        </>
      )}

      <ExecuteActionDialog
        detection={dialogDetection}
        open={dialogDetection !== null}
        onOpenChange={(open) => {
          if (!open) setDialogDetection(null);
        }}
        onExecute={async (actionId, confirmed) => {
          if (dialogDetection) {
            await onExecute(dialogDetection, actionId, confirmed);
          }
        }}
      />
    </div>
  );
}
