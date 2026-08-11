/**
 * SOC Console (docs/02 §5.1): three-pane — live feed | analyst+graph | inspector.
 * Client component fed by REST initial load + WS live updates.
 */

"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { clsx } from "clsx";

import { api, authedRequest } from "@/lib/api/client";
import type { CanonicalEvent, Detection, GraphView } from "@/lib/api/types";
import { useSimulationChannel } from "@/lib/ws/useSimulationChannel";
import { EventRow } from "@/components/dashboard/EventRow";
import { DetectionCard } from "@/components/dashboard/DetectionCard";
import { Card, CardHeader } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { StatusDot } from "@/components/ui/SeverityBadge";

export default function SocConsole() {
  const params = useParams<{ id: string }>();
  const simId = params.id;

  const [initialEvents, setInitialEvents] = useState<CanonicalEvent[]>([]);
  const [initialDetections, setInitialDetections] = useState<Detection[]>([]);
  const [graph, setGraph] = useState<GraphView | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<CanonicalEvent | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const live = useSimulationChannel(simId);

  useEffect(() => {
    if (!simId) return;
    void (async () => {
      try {
        const [events, detections, graph] = await Promise.all([
          authedRequest(() => api.events(simId)),
          authedRequest(() => api.detections(simId)),
          authedRequest(() => api.graph(simId)),
        ]);
        setInitialEvents(events.items);
        setInitialDetections(detections);
        setGraph(graph);
      } catch (e) {
        setNotice((e as Error).message);
      } finally {
        setLoaded(true);
      }
    })();
  }, [simId]);

  const allEvents = useMemo(
    () => [...live.events, ...initialEvents],
    [live.events, initialEvents],
  );
  const allDetections = useMemo(
    () => [...live.detections, ...initialDetections],
    [live.detections, initialDetections],
  );

  async function executeResponse(detection: Detection, actionId: string) {
    try {
      await authedRequest(() =>
        api.execute(simId, detection.detection_id, actionId, {}, true),
      );
      setNotice(`Executed ${actionId}`);
    } catch (e) {
      setNotice((e as Error).message);
    }
  }

  if (!loaded) {
    return (
      <div className="flex justify-center p-16">
        <Spinner size={20} />
      </div>
    );
  }

  return (
    <div className="grid h-full grid-cols-[minmax(280px,340px)_1fr_320px]">
      {/* LEFT: live event feed */}
      <section className="border-cs-border-subtle flex min-h-0 flex-col border-r">
        <CardHeader
          title="Live events"
          right={
            <StatusDot
              color={live.status === "completed" ? "ok" : "accent"}
              label={live.status}
            />
          }
        />
        <div className="min-h-0 flex-1 overflow-y-auto">
          {[...allEvents]
            .reverse()
            .slice(0, 300)
            .map((ev) => (
              <EventRow
                key={ev.event_id}
                event={ev}
                onSelect={setSelected}
                highlighted={selected?.event_id === ev.event_id}
              />
            ))}
          {allEvents.length === 0 && (
            <p className="text-cs-text-tertiary p-4 text-sm">
              No events yet — the simulation is starting…
            </p>
          )}
        </div>
      </section>

      {/* CENTER: analyst stream + graph */}
      <section className="flex min-h-0 flex-col overflow-y-auto p-3">
        {notice && (
          <div className="rounded-cs-sm bg-cs-warn-bg text-cs-warn-fg mb-2 px-2 py-1 text-xs">
            {notice}
          </div>
        )}

        <h2 className="text-cs-text-tertiary mb-2 text-sm font-medium tracking-wide uppercase">
          AI Analyst
        </h2>
        {allDetections.length === 0 ? (
          <p className="text-cs-text-tertiary text-sm">Watching for threats…</p>
        ) : (
          allDetections
            .slice()
            .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))
            .map((d) => (
              <DetectionCard
                key={d.detection_id}
                detection={d}
                onExecute={executeResponse}
              />
            ))
        )}

        {/* Attack graph (static layout view) */}
        {graph && (
          <>
            <h2 className="text-cs-text-tertiary mt-6 mb-2 text-sm font-medium tracking-wide uppercase">
              Attack graph
            </h2>
            <Card className="p-3">
              <div className="flex flex-wrap gap-1">
                {graph.nodes.map((n) => (
                  <span
                    key={n.id}
                    className={clsx(
                      "rounded-cs-xs border px-2 py-0.5 font-mono text-xs",
                      n.foothold_state === "compromised" ||
                        n.foothold_state === "foothold"
                        ? "border-cs-sev-critical-fg text-cs-sev-critical-fg"
                        : n.kind === "DATA"
                          ? "border-cs-sev-medium-fg text-cs-sev-medium-fg"
                          : "border-cs-border-default text-cs-text-secondary",
                    )}
                  >
                    {n.label}
                  </span>
                ))}
              </div>
              <p className="text-cs-text-tertiary mt-2 text-xs">
                {graph.nodes.length} nodes · {graph.edges.length} edges · seq{" "}
                {graph.seq}
              </p>
            </Card>
          </>
        )}
      </section>

      {/* RIGHT: inspector */}
      <section className="border-cs-border-subtle flex min-h-0 flex-col border-l">
        <CardHeader title="Inspector" />
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {selected ? (
            <div className="space-y-3">
              <h3 className="text-sm font-medium">{selected.event_type}</h3>
              <p className="text-cs-text-tertiary font-mono text-xs">
                {selected.event_id}
              </p>
              <dl className="space-y-1 text-xs">
                <div className="flex justify-between">
                  <dt className="text-cs-text-tertiary">Timestamp</dt>
                  <dd>{new Date(selected.timestamp).toLocaleString()}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-cs-text-tertiary">Source IP</dt>
                  <dd>{selected.source_ip}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-cs-text-tertiary">Target Asset</dt>
                  <dd>{selected.target_asset}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-cs-text-tertiary">Actor</dt>
                  <dd className="font-mono">{selected.actor}</dd>
                </div>
              </dl>
              <pre className="rounded-cs-sm bg-cs-neutral-1 text-cs-text-secondary overflow-x-auto p-2 font-mono text-xs">
                {JSON.stringify(selected.raw_context, null, 2)}
              </pre>
            </div>
          ) : (
            <p className="text-cs-text-tertiary text-sm">
              Select an event to inspect its structured payload.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
