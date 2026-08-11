/** Marketing root (docs/02 §5.2, docs/13 §11): hero + live-trace + features. */

import Link from "next/link";
import {
  ArrowRight,
  Braces,
  GitBranch,
  ShieldCheck,
  BrainCircuit,
  Target,
} from "lucide-react";

import { TerminalHero } from "@/components/marketing/TerminalHero";

const FEATURES = [
  {
    icon: GitBranch,
    title: "Attack-graph reasoning",
    body: "Events become chains. The analyst reasons about progression — not isolated alerts.",
  },
  {
    icon: BrainCircuit,
    title: "Evidence-grounded AI",
    body: "Every detection carries its evidence, its attack path, and its citations. Nothing unsupported.",
  },
  {
    icon: ShieldCheck,
    title: "Controlled cyber range",
    body: "Reproducible, sandboxed scenarios. Safe to demo, safe to train on, safe to replay.",
  },
  {
    icon: Target,
    title: "Mission mode",
    body: "Scored, interactive attack/defense runs with public judge links — no signup for visitors.",
  },
];

const PIPELINE = [
  [
    "Simulator",
    "Deterministic event streams (web · API · network · supply chain)",
  ],
  ["Normalizer", "Raw events → canonical schema with MITRE + OWASP mapping"],
  [
    "AI analyst",
    "LangGraph pipeline: triage → evidence → risk → response plan",
  ],
  ["Executor", "Whitelisted, validated response actions with audit trail"],
];

export default function HomePage() {
  return (
    <main>
      {/* Hero */}
      <section className="mx-auto max-w-4xl px-6 pt-20 pb-12 text-center">
        <h1 className="text-4xl leading-tight font-bold">
          Controlled cyberattack scenarios.
          <br />
          <span className="text-cs-accent-fg">Evidence-grounded</span> AI
          analyst.
        </h1>
        <p className="text-cs-text-secondary mx-auto mt-4 max-w-2xl text-base">
          CyberSim AI models attacks as graph progressions and uses an AI
          analyst that detects, explains, and recommends responses — with every
          decision backed by evidence.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link
            href="/login"
            className="rounded-cs-md bg-cs-accent-fg text-md text-cs-text-inverse inline-flex h-11 items-center gap-2 px-5 font-medium hover:bg-[var(--cs-accent-fg-hover)]"
          >
            Open the SOC console <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* Live trace */}
      <section className="mx-auto max-w-3xl px-6 pb-16">
        <TerminalHero />
      </section>

      {/* Features */}
      <section
        id="features"
        className="mx-auto grid max-w-5xl grid-cols-1 gap-4 px-6 pb-16 md:grid-cols-2"
      >
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <div
            key={title}
            className="rounded-cs-lg border-cs-border-default bg-cs-neutral-2 border p-5 shadow-[var(--cs-shadow-1)]"
          >
            <Icon className="text-cs-accent-fg mb-3 h-5 w-5" aria-hidden />
            <h2 className="text-md font-semibold">{title}</h2>
            <p className="text-cs-text-secondary mt-1 text-sm">{body}</p>
          </div>
        ))}
      </section>

      {/* Pipeline — the architecture as a live artifact (docs/03) */}
      <section className="mx-auto max-w-4xl px-6 pb-20">
        <p className="text-cs-text-tertiary mb-3 text-center text-sm tracking-wide uppercase">
          The pipeline, end to end
        </p>
        <div className="rounded-cs-lg border-cs-border-default bg-cs-neutral-2 divide-y divide-[var(--cs-border-subtle)] border shadow-[var(--cs-shadow-1)]">
          {PIPELINE.map(([step, detail], i) => (
            <div key={step} className="flex items-center gap-3 px-4 py-3">
              <span className="rounded-cs-xs bg-cs-accent-bg text-cs-accent-fg flex h-6 w-6 shrink-0 items-center justify-center font-mono text-xs">
                {i + 1}
              </span>
              <span className="w-36 shrink-0 text-sm font-semibold">
                {step}
              </span>
              <span className="text-cs-text-secondary flex items-center gap-2 text-sm">
                <Braces
                  className="text-cs-text-quaternary h-3.5 w-3.5"
                  aria-hidden
                />
                {detail}
              </span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
