/**
 * TerminalHero (docs/13 §11, docs/02 §4.7): live-trace sample frames rotated
 * by IntersectionObserver-driven CSS motion — starts animating only when
 * scrolled into view.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { clsx } from "clsx";

const FRAMES = [
  {
    kind: "event.upsert",
    event: {
      subtype: "auth.success",
      severity_hint: "high",
      source_node_id: "login_ep",
      correlation_key: "src_ip=203.0.113.42",
      payload: { account: "admin@finbank", scope: "admin" },
    },
  },
  {
    kind: "detection.created",
    detection: {
      threat_class: "credential_compromise",
      severity: "high",
      confidence: 0.91,
      evidence: [
        "repeated_failed_logins",
        "credential_state_compromised_account",
      ],
      attack_path: ["Internet", "/api/login", "users_db", "user_data"],
      source: "ai",
    },
  },
  {
    kind: "action.executed",
    execution_id: "exec-0c91a4",
    action_id: "block_source_ip",
    events_emitted: 3,
  },
  {
    kind: "sim.score",
    mission: "mission.finbank_breach",
    score: 67,
    max_score: 100,
    objectives_achieved: 3,
  },
];

export function TerminalHero() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [frameIdx, setFrameIdx] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.disconnect();
          }
        }
      },
      { threshold: 0.3 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    const timer = window.setInterval(() => {
      setFrameIdx((i) => (i + 1) % FRAMES.length);
    }, 2600);
    return () => window.clearInterval(timer);
  }, [visible]);

  const frame = FRAMES[frameIdx];

  return (
    <div
      ref={ref}
      className="rounded-cs-lg border-cs-border-default bg-cs-neutral-2 overflow-hidden border text-left shadow-[var(--cs-shadow-2)]"
      aria-label="Live analyst trace"
    >
      <div className="border-cs-border-subtle flex items-center gap-1.5 border-b px-3 py-2">
        <span
          className="bg-cs-sev-critical-fg h-2 w-2 rounded-full"
          aria-hidden
        />
        <span className="bg-cs-warn-fg h-2 w-2 rounded-full" aria-hidden />
        <span className="bg-cs-ok-fg h-2 w-2 rounded-full" aria-hidden />
        <span className="text-cs-text-tertiary ml-2 font-mono text-xs">
          cyber analyst — live trace
        </span>
      </div>
      <pre
        key={frameIdx}
        className={clsx(
          "text-cs-text-secondary overflow-x-auto p-4 font-mono text-xs leading-relaxed",
          visible
            ? "animate-[cs-fade-in_320ms_var(--cs-ease-out)]"
            : "opacity-0",
        )}
      >
        {JSON.stringify(frame, null, 2)}
        <span className="text-cs-accent-fg animate-pulse">▍</span>
      </pre>
    </div>
  );
}
