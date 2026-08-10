/**
 * Stage 04 demo dashboard (04-dashboard-frontend.md): four-panel layout —
 * top bar with scenario + Start/Reset, event stream (left), attack graph
 * (right), AI analyst card (bottom). Polls the Stage 01–03 demo endpoints
 * on a 1s cadence while the simulation runs.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { demoApi } from "@/lib/demo/api";
import type { AnalysisResponse, DemoEvent, GraphSnapshot } from "@/lib/demo/types";
import { EventStream } from "@/components/demo/EventStream";
import { AttackGraph } from "@/components/demo/AttackGraph";
import { AnalystPanel } from "@/components/demo/AnalystPanel";
import { Button } from "@/components/ui/Button";
import { StatusDot } from "@/components/ui/SeverityBadge";

const POLL_MS = 1000;

type Phase = "idle" | "running" | "done";
type AnalystStatus = "idle" | "analyzing" | "awaiting_approval" | "contained" | "none";

export default function DemoDashboard() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [events, setEvents] = useState<DemoEvent[]>([]);
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [analystStatus, setAnalystStatus] = useState<AnalystStatus>("idle");
  const [starting, setStarting] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lastCountRef = useRef(0);
  const sameCountRef = useRef(0);
  const phaseRef = useRef<Phase>("idle");
  phaseRef.current = phase;

  const poll = useCallback(async () => {
    try {
      const [evs, snap] = await Promise.all([demoApi.events(), demoApi.graph()]);
      setEvents(evs);
      setGraph(snap);
      if (phaseRef.current === "running") {
        if (evs.length === lastCountRef.current) {
          sameCountRef.current += 1;
        } else {
          sameCountRef.current = 0;
        }
        lastCountRef.current = evs.length;
        if (sameCountRef.current >= 2) setPhase("done");
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  // Poll while a simulation is running or waiting for human approval.
  useEffect(() => {
    if (phase === "idle") return;
    void poll();
    const t = setInterval(poll, POLL_MS);
    return () => clearInterval(t);
  }, [phase, poll]);

  // Auto-run the analyst once the scenario finishes (no manual click needed).
  useEffect(() => {
    if (phase !== "done" || analystStatus !== "idle") return;
    let cancelled = false;
    setAnalystStatus("analyzing");
    demoApi
      .analyze()
      .then((a) => {
        if (cancelled) return;
        setAnalysis(a);
        setAnalystStatus(a.threat_card ? "awaiting_approval" : "none");
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
        setAnalystStatus("none");
      });
    return () => {
      cancelled = true;
    };
  }, [phase, analystStatus]);

  async function handleStart() {
    setError(null);
    setEvents([]);
    setGraph(null);
    setAnalysis(null);
    setAnalystStatus("idle");
    lastCountRef.current = 0;
    sameCountRef.current = 0;
    setPhase("running");
    setStarting(true);
    try {
      await demoApi.start(0.8);
    } catch (e) {
      setError((e as Error).message);
      setPhase("idle");
    } finally {
      setStarting(false);
    }
  }

  async function handleReset() {
    setError(null);
    try {
      await demoApi.reset();
    } catch {
      // the dashboard still clears local state below
    }
    setEvents([]);
    setGraph(null);
    setAnalysis(null);
    setAnalystStatus("idle");
    setPhase("idle");
  }

  async function handleExecute() {
    setError(null);
    setExecuting(true);
    try {
      await demoApi.approve();
      setAnalystStatus("contained");
      await poll();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setExecuting(false);
    }
  }

  const running = phase === "running";
  const statusLabel = phase === "idle" ? "idle" : phase === "running" ? "running" : "complete";

  return (
    <main className="bg-cs-neutral-0 text-cs-text-primary flex h-screen flex-col overflow-hidden font-sans">
      {/* Top bar */}
      <header className="border-b border-cs-border-subtle flex items-center gap-3 px-4 py-2.5">
        <h1 className="text-cs-accent-fg font-mono text-lg font-bold tracking-tight">
          CYBERSIM AI
        </h1>
        <span className="text-cs-text-tertiary text-sm">
          Scenario: <span className="text-cs-text-secondary">Credential Attack</span>
        </span>
        <div className="ml-auto flex items-center gap-3">
          <StatusDot
            color={running ? "critical" : phase === "done" ? "ok" : "accent"}
            label={statusLabel}
          />
          {error && <span className="text-cs-error-fg text-xs">{error}</span>}
          <Button size="sm" variant="primary" onClick={handleStart} disabled={running || starting}>
            {starting ? "Starting…" : "Start Simulation"}
          </Button>
          <Button size="sm" variant="secondary" onClick={handleReset} disabled={starting || executing}>
            Reset
          </Button>
        </div>
      </header>

      {/* Event stream + attack graph */}
      <div className="grid min-h-0 flex-[3] grid-cols-[minmax(280px,35%)_1fr]">
        <section className="border-cs-border-subtle flex min-h-0 flex-col border-r">
          <div className="border-b border-cs-border-subtle px-3 py-1.5">
            <h2 className="text-cs-text-secondary text-xs font-semibold uppercase tracking-wide">
              Event stream
            </h2>
          </div>
          <EventStream events={events} />
        </section>
        <section className="flex min-h-0 flex-col">
          <div className="border-b border-cs-border-subtle px-3 py-1.5">
            <h2 className="text-cs-text-secondary text-xs font-semibold uppercase tracking-wide">
              Attack graph
            </h2>
          </div>
          <AttackGraph snap={graph} />
        </section>
      </div>

      {/* AI analyst */}
      <section className="flex min-h-0 flex-[2] flex-col border-t border-cs-border-subtle">
        <div className="border-b border-cs-border-subtle px-3 py-1.5">
          <h2 className="text-cs-text-secondary text-xs font-semibold uppercase tracking-wide">
            AI security analyst
          </h2>
        </div>
        <AnalystPanel
          analysis={analysis}
          status={analystStatus}
          executing={executing}
          onExecute={handleExecute}
          onReset={handleReset}
        />
      </section>
    </main>
  );
}
