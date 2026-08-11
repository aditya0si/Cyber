/**
 * Simulation SOC Console — tells the full attack story in plain English.
 * Three panes: Live Feed (what happened) | AI Analyst (what we found) | Inspector (deep dive)
 */

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { clsx } from "clsx";
import { ShieldAlert, ShieldCheck, Radar, Activity, ChevronRight, AlertTriangle, Info } from "lucide-react";

import { api, authedRequest } from "@/lib/api/client";
import type { CanonicalEvent, Detection } from "@/lib/api/types";
import { useSimulationChannel } from "@/lib/ws/useSimulationChannel";
import { buildNarrative, detectionSummary } from "@/lib/sim/eventNarrative";
import { Spinner } from "@/components/ui/Spinner";
import { useResize } from "@/hooks/useResize";

// ────────────────────────────────────────────────
// Severity → color mappings
// ────────────────────────────────────────────────
const SEV_COLOR: Record<string, string> = {
  CRITICAL: "text-red-400 border-red-500/60 bg-red-500/10",
  HIGH: "text-orange-400 border-orange-500/60 bg-orange-500/10",
  MEDIUM: "text-yellow-400 border-yellow-500/60 bg-yellow-500/10",
  LOW: "text-slate-400 border-slate-600 bg-transparent",
  INFO: "text-slate-500 border-slate-700 bg-transparent",
};

const SEV_DOT: Record<string, string> = {
  CRITICAL: "bg-red-500",
  HIGH: "bg-orange-400",
  MEDIUM: "bg-yellow-400",
  LOW: "bg-slate-500",
  INFO: "bg-slate-700",
};

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "text-red-400",
  medium: "text-yellow-400",
  low: "text-slate-400",
};

// ────────────────────────────────────────────────
// EventFeedRow — one line in the live feed
// ────────────────────────────────────────────────
function EventFeedRow({
  ev,
  selected,
  onSelect,
}: {
  ev: CanonicalEvent;
  selected: boolean;
  onSelect: () => void;
}) {
  const narrative = useMemo(() => buildNarrative(ev), [ev]);
  const sev = ev.severity?.toUpperCase() ?? "LOW";
  const ctx = ev.raw_context as Record<string, unknown>;
  const benign = Boolean(ctx?.benign ?? false);
  const subtype = String(ctx?.subtype ?? ev.event_type ?? "");
  const isAttack = narrative.kind === "attack";

  return (
    <button
      onClick={onSelect}
      className={clsx(
        "group flex w-full items-start gap-2.5 border-b border-white/5 px-3 py-2.5 text-left transition-all",
        selected ? "bg-white/8" : "hover:bg-white/4",
        isAttack && !benign && "border-l-2",
        sev === "CRITICAL" && !benign && "border-l-red-500",
        sev === "HIGH" && !benign && "border-l-orange-400",
        sev === "MEDIUM" && !benign && "border-l-yellow-400",
      )}
    >
      {/* Severity dot */}
      <div className="mt-1 flex shrink-0 flex-col items-center gap-1">
        <div className={clsx("h-2 w-2 rounded-full", benign ? "bg-slate-600" : SEV_DOT[sev] ?? "bg-slate-600")} />
      </div>

      <div className="min-w-0 flex-1">
        {/* Headline */}
        <p className={clsx(
          "truncate text-sm font-medium leading-snug",
          benign ? "text-slate-500" : isAttack ? "text-slate-100" : "text-slate-400"
        )}>
          {narrative.headline}
        </p>
        {/* Sub-line: IP + subtype */}
        <p className="mt-0.5 truncate font-mono text-xs text-slate-500">
          {ev.source_ip} · {subtype.replace(/_/g, " ")}
        </p>
      </div>

      {/* Severity badge */}
      {!benign && sev !== "LOW" && (
        <span className={clsx(
          "mt-0.5 shrink-0 rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide",
          SEV_COLOR[sev] ?? "text-slate-400 border-slate-600"
        )}>
          {sev}
        </span>
      )}
    </button>
  );
}

// ────────────────────────────────────────────────
// EventInspector — right pane detail card
// ────────────────────────────────────────────────
function EventInspector({ ev }: { ev: CanonicalEvent }) {
  const narrative = useMemo(() => buildNarrative(ev), [ev]);
  const sev = ev.severity?.toUpperCase() ?? "LOW";
  const ctx = ev.raw_context as Record<string, unknown>;
  const attackStage = String(ctx?.attack_stage ?? "");

  return (
    <div className="space-y-4 p-4">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          {narrative.kind === "attack" ? (
            <AlertTriangle className="h-4 w-4 text-orange-400" />
          ) : (
            <Info className="h-4 w-4 text-slate-500" />
          )}
          <h3 className="text-sm font-semibold text-slate-100 leading-tight">
            {narrative.headline}
          </h3>
        </div>
        <p className="mt-1 font-mono text-xs text-slate-500">{ev.event_id}</p>
      </div>

      {/* What happened */}
      <div className="rounded-lg border border-white/8 bg-white/4 p-3">
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-slate-500">
          What happened
        </p>
        <p className="text-sm leading-relaxed text-slate-300">{narrative.what}</p>
      </div>

      {/* Payload sent */}
      <div className="rounded-lg border border-white/8 bg-white/4 p-3">
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-slate-500">
          Payload / Request
        </p>
        <pre className="whitespace-pre-wrap break-all font-mono text-xs text-slate-300 leading-relaxed">
          {narrative.payloadSummary}
        </pre>
      </div>

      {/* How we categorized it */}
      <div className="rounded-lg border border-white/8 bg-white/4 p-3 space-y-2">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          How we analyzed it
        </p>
        <div className="flex justify-between text-xs">
          <span className="text-slate-500">Classification</span>
          <span className={clsx("font-medium", narrative.kind === "attack" ? "text-orange-400" : "text-slate-400")}>
            {narrative.classification}
          </span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-slate-500">Severity</span>
          <span className={clsx("font-mono font-semibold", SEV_COLOR[sev]?.split(" ")[0] ?? "text-slate-400")}>
            {sev}
          </span>
        </div>
        {attackStage && (
          <div className="flex justify-between text-xs">
            <span className="text-slate-500">Kill-chain stage</span>
            <span className="font-medium text-slate-300">
              {attackStage.replace(/_/g, " ")}
            </span>
          </div>
        )}
        {narrative.mitreTactic && (
          <div className="flex justify-between text-xs">
            <span className="text-slate-500">MITRE ATT&CK</span>
            <span className="font-mono text-violet-400">{narrative.mitreTactic}</span>
          </div>
        )}
        <div className="flex justify-between text-xs">
          <span className="text-slate-500">Source IP</span>
          <span className={clsx("font-mono", ev.source_ip === "203.0.113.42" ? "text-red-400 font-semibold" : "text-slate-300")}>
            {ev.source_ip}{ev.source_ip === "203.0.113.42" && " ← attacker"}
          </span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-slate-500">Target asset</span>
          <span className="font-mono text-slate-300">{ev.target_asset}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-slate-500">Timestamp</span>
          <span className="font-mono text-slate-400">
            {new Date(ev.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────
// DetectionCard — AI analyst threat finding
// ────────────────────────────────────────────────
function DetectionCard({ d, index }: { d: Detection; index: number }) {
  const [open, setOpen] = useState(index === 0);
  const pct = Math.round((d.confidence ?? 0) * 100);
  const sev = d.severity?.toUpperCase() ?? "MEDIUM";
  const bandColor = CONFIDENCE_COLOR[d.confidence_band ?? "medium"] ?? "text-slate-400";

  return (
    <div className={clsx(
      "rounded-xl border transition-all",
      sev === "CRITICAL" ? "border-red-500/40 bg-red-500/5" :
        sev === "HIGH" ? "border-orange-500/40 bg-orange-500/5" :
          "border-yellow-500/30 bg-yellow-500/5"
    )}>
      <button
        className="flex w-full items-start gap-3 p-4 text-left"
        onClick={() => setOpen(o => !o)}
      >
        <ShieldAlert className={clsx(
          "mt-0.5 h-5 w-5 shrink-0",
          sev === "CRITICAL" ? "text-red-400" :
            sev === "HIGH" ? "text-orange-400" : "text-yellow-400"
        )} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-slate-100">{d.title}</p>
            <span className={clsx(
              "rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide",
              SEV_COLOR[sev] ?? "text-slate-400 border-slate-600"
            )}>
              {sev}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-slate-400">{d.threat_class?.replace(/_/g, " ")}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className={clsx("font-mono text-lg font-bold tabular-nums", bandColor)}>{pct}%</p>
          <p className="text-xs text-slate-500">confidence</p>
        </div>
        <ChevronRight className={clsx("mt-1 h-4 w-4 shrink-0 text-slate-500 transition-transform", open && "rotate-90")} />
      </button>

      {open && (
        <div className="border-t border-white/8 px-4 pb-4 pt-3 space-y-3">
          {/* Plain-English summary */}
          <p className="text-sm leading-relaxed text-slate-300">
            {detectionSummary(d)}
          </p>

          {/* MITRE tags */}
          {d.mitre.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {d.mitre.slice(0, 4).map(m => (
                <span key={m} className="rounded border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 font-mono text-xs text-violet-400">
                  {m}
                </span>
              ))}
            </div>
          )}

          {/* Attack path */}
          {d.attack_path.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-slate-500">Attack path</p>
              <div className="flex flex-wrap items-center gap-1">
                {d.attack_path.map((node, i) => (
                  <span key={node.node_id} className="flex items-center gap-1">
                    <span className={clsx(
                      "rounded border px-2 py-0.5 text-xs",
                      node.foothold_state === "compromised" ? "border-red-500/60 bg-red-500/10 text-red-400" :
                        node.foothold_state === "foothold" ? "border-orange-500/60 bg-orange-500/10 text-orange-400" :
                          "border-white/10 text-slate-400"
                    )}>
                      {node.label}
                    </span>
                    {i < d.attack_path.length - 1 && <span className="text-slate-600">→</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Recommended actions */}
          {d.recommended_actions.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-slate-500">Recommended actions</p>
              <ul className="space-y-1">
                {d.recommended_actions.map(a => (
                  <li key={a.action_id} className="flex items-start gap-2 text-xs">
                    <span className="mt-0.5 shrink-0 text-green-400">✓</span>
                    <span className="text-slate-300">{a.rationale}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────
// StatusBar — top strip showing simulation state
// ────────────────────────────────────────────────
function StatusBar({ status, eventCount, detectionCount, scenarioTitle }: {
  status: string;
  eventCount: number;
  detectionCount: number;
  scenarioTitle: string;
}) {
  const isLive = status === "running";
  const isDone = status === "completed";

  return (
    <div className="flex items-center gap-4 border-b border-white/8 bg-[#0d0d10] px-5 py-3">
      <div className="flex items-center gap-2">
        {isLive ? (
          <>
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-green-400" />
            </span>
            <span className="text-sm font-medium text-green-400">Live</span>
          </>
        ) : isDone ? (
          <>
            <ShieldCheck className="h-4 w-4 text-slate-400" />
            <span className="text-sm text-slate-400">Completed</span>
          </>
        ) : (
          <>
            <Spinner size={14} />
            <span className="text-sm text-slate-400">{status}</span>
          </>
        )}
      </div>

      <span className="text-slate-700">|</span>
      <p className="text-sm font-semibold text-slate-200">{scenarioTitle}</p>

      <div className="ml-auto flex items-center gap-4">
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Activity className="h-3.5 w-3.5" />
          <span className="tabular-nums font-mono">{eventCount}</span>
          <span>events</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <ShieldAlert className={clsx("h-3.5 w-3.5", detectionCount > 0 ? "text-orange-400" : "text-slate-600")} />
          <span className={clsx("tabular-nums font-mono", detectionCount > 0 ? "text-orange-400 font-semibold" : "text-slate-400")}>
            {detectionCount}
          </span>
          <span className="text-slate-400">threats</span>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────
// Main page
// ────────────────────────────────────────────────
export default function SocConsole() {
  const params = useParams<{ id: string }>();
  const simId = params.id;

  const [polledEvents, setPolledEvents] = useState<CanonicalEvent[]>([]);
  const [polledDetections, setPolledDetections] = useState<Detection[]>([]);
  const [scenarioTitle, setScenarioTitle] = useState("Simulation");
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<CanonicalEvent | null>(null);
  const [showBenign, setShowBenign] = useState(false);

  const live = useSimulationChannel(simId);
  const feedRef = useRef<HTMLDivElement>(null);

  // --- Initial load + polling ---
  // The simulation runs as a backend background task that often completes
  // before the WebSocket connects. So we poll the REST API every 1.5 s until
  // the sim is "completed" and we have events, then stop.
  useEffect(() => {
    if (!simId) return;
    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    async function fetchAll() {
      try {
        const [events, detections, simDetail] = await Promise.all([
          authedRequest(() => api.events(simId)),
          authedRequest(() => api.detections(simId)),
          authedRequest(() => api.simulation(simId)),
        ]);
        if (cancelled) return;
        setPolledEvents(events.items);
        setPolledDetections(detections);
        const raw = simDetail as unknown as Record<string, unknown>;
        const scenId = String(raw.scenario_id ?? "");
        if (scenId) setScenarioTitle(scenId.replace(/[._]/g, " "));
        setLoaded(true);

        // Keep polling while sim hasn't finished or we have no events yet
        const status = String(raw.status ?? "");
        const done = status === "completed" || status === "failed" || status === "stopped";
        if (!done || events.items.length === 0) {
          pollTimer = setTimeout(() => void fetchAll(), 1500);
        }
      } catch {
        if (!cancelled) setLoaded(true);
      }
    }

    void fetchAll();
    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [simId]);

  // Merge polled + live WS events, dedup
  const allEvents = useMemo(() => {
    const seen = new Set<string>();
    const merged = [...polledEvents, ...live.events];
    return merged.filter(e => {
      if (seen.has(e.event_id)) return false;
      seen.add(e.event_id);
      return true;
    });
  }, [polledEvents, live.events]);

  const allDetections = useMemo(() => {
    const seen = new Set<string>();
    const merged = [...polledDetections, ...live.detections];
    return merged.filter(d => {
      if (seen.has(d.detection_id)) return false;
      seen.add(d.detection_id);
      return true;
    }).sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
  }, [polledDetections, live.detections]);

  // Filter out benign unless toggled
  const visibleEvents = useMemo(() => {
    const filtered = showBenign
      ? allEvents
      : allEvents.filter(e => {
          const ctx = e.raw_context as Record<string, unknown>;
          return !ctx?.benign;
        });
    return [...filtered].reverse();
  }, [allEvents, showBenign]);

  const leftResize = useResize({ initialSize: 320, min: 180, max: 560 });
  const rightResize = useResize({ initialSize: 340, min: 200, max: 560 });

  if (!loaded) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <Radar className="h-10 w-10 animate-spin text-violet-500 opacity-60" style={{ animationDuration: "3s" }} />
        <p className="text-sm text-slate-500">Starting simulation…</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-[#0d0d10] text-slate-200">
      <StatusBar
        status={live.status}
        eventCount={allEvents.length}
        detectionCount={allDetections.length}
        scenarioTitle={scenarioTitle}
      />

      {/* Three-pane resizable layout */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* ── LEFT: Live event feed ── */}
        <section
          className="flex min-h-0 flex-col border-r border-white/8"
          style={{ width: leftResize.size, flexShrink: 0 }}
        >
          <div className="flex items-center justify-between border-b border-white/8 px-3 py-2">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Live Feed</h2>
            <button
              onClick={() => setShowBenign(v => !v)}
              className={clsx(
                "rounded px-2 py-0.5 text-xs transition-colors",
                showBenign ? "bg-white/8 text-slate-300" : "text-slate-600 hover:text-slate-400"
              )}
            >
              {showBenign ? "Hide benign" : "Show all"}
            </button>
          </div>

          <div ref={feedRef} className="min-h-0 flex-1 overflow-y-auto">
            {visibleEvents.length === 0 && (
              <div className="flex flex-col items-center justify-center gap-2 p-10 text-center">
                <Radar className="h-8 w-8 text-slate-700" />
                <p className="text-sm text-slate-500">
                  {allEvents.length === 0 && (live.status === "running" || live.status === "connecting")
                    ? "Simulation running — events will appear shortly…"
                    : "No attack events — simulation only generated benign traffic"}
                </p>
              </div>
            )}
            {visibleEvents.map(ev => (
              <EventFeedRow
                key={ev.event_id}
                ev={ev}
                selected={selected?.event_id === ev.event_id}
                onSelect={() => setSelected(ev)}
              />
            ))}
          </div>
        </section>

        {/* ── Drag handle ── */}
        <div
          {...leftResize.handleProps}
          className="group relative z-10 flex w-1 cursor-col-resize items-center justify-center bg-white/5 hover:bg-violet-500/60 active:bg-violet-400 transition-colors"
          title="Drag to resize"
        >
          <div className="h-8 w-0.5 rounded-full bg-white/20 group-hover:bg-white/60 transition-colors" />
        </div>

        {/* ── CENTER: AI Analyst ── */}
        <section className="flex min-h-0 flex-col overflow-y-auto flex-1">
          <div className="border-b border-white/8 px-5 py-2">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">AI Analyst</h2>
          </div>

          <div className="flex-1 space-y-3 p-4">
            {allDetections.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
                <div className="relative">
                  <ShieldCheck className="h-12 w-12 text-slate-700" />
                  {allEvents.length === 0 || live.status === "running" || live.status === "connecting" ? (
                    <span className="absolute -right-1 -top-1 flex h-3 w-3">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
                      <span className="relative inline-flex h-3 w-3 rounded-full bg-green-500" />
                    </span>
                  ) : null}
                </div>
                <p className="text-sm font-medium text-slate-400">
                  {live.status === "completed" && allEvents.length > 0 ? "No threats detected" : "Monitoring for threats…"}
                </p>
                <p className="max-w-xs text-xs text-slate-600">
                  The AI analyst correlates events across the attack graph to find malicious patterns.
                  Results appear here in real time.
                </p>
              </div>
            ) : (
              <>
                <div className="mb-1 flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-orange-400" />
                  <h3 className="text-sm font-semibold text-slate-200">
                    {allDetections.length} threat{allDetections.length !== 1 ? "s" : ""} detected
                  </h3>
                </div>
                {allDetections.map((d, i) => (
                  <DetectionCard key={d.detection_id} d={d} index={i} />
                ))}
              </>
            )}
          </div>
        </section>

        {/* ── Drag handle ── */}
        <div
          {...rightResize.handleProps}
          className="group relative z-10 flex w-1 cursor-col-resize items-center justify-center bg-white/5 hover:bg-violet-500/60 active:bg-violet-400 transition-colors"
          title="Drag to resize"
        >
          <div className="h-8 w-0.5 rounded-full bg-white/20 group-hover:bg-white/60 transition-colors" />
        </div>

        {/* ── RIGHT: Inspector ── */}
        <section
          className="flex min-h-0 flex-col border-l border-white/8"
          style={{ width: rightResize.size, flexShrink: 0 }}
        >
          <div className="border-b border-white/8 px-3 py-2">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">Inspector</h2>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {selected ? (
              <EventInspector ev={selected} />
            ) : (
              <div className="flex flex-col items-center justify-center gap-2 p-10 text-center">
                <ChevronRight className="h-6 w-6 text-slate-700" />
                <p className="text-xs text-slate-500">
                  Click any event in the feed to see a full explanation of what happened and how it was analyzed.
                </p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
