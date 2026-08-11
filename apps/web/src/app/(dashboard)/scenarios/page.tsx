/** Scenario picker — rich cards with attack descriptions. */

"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Play, Zap, Globe, Server, Network, Package, ShieldAlert } from "lucide-react";
import { clsx } from "clsx";

import { api, authedRequest } from "@/lib/api/client";
import type { ScenarioSummary } from "@/lib/api/types";
import { Spinner } from "@/components/ui/Spinner";

const CATEGORY_META: Record<string, { label: string; icon: React.ElementType; color: string; desc: string }> = {
  api_abuse: {
    label: "API Abuse",
    icon: Server,
    color: "text-violet-400 bg-violet-500/10 border-violet-500/30",
    desc: "Attackers exploit API endpoints — enumeration, IDOR, and brute-force.",
  },
  web_application_attack: {
    label: "Web Application Attack",
    icon: Globe,
    color: "text-blue-400 bg-blue-500/10 border-blue-500/30",
    desc: "Classic web vulnerabilities — SQL injection, auth bypass.",
  },
  network_intrusion: {
    label: "Network Intrusion",
    icon: Network,
    color: "text-cyan-400 bg-cyan-500/10 border-cyan-500/30",
    desc: "Reconnaissance, lateral movement, and data exfiltration across the network.",
  },
  supply_chain_compromise: {
    label: "Supply Chain Compromise",
    icon: Package,
    color: "text-orange-400 bg-orange-500/10 border-orange-500/30",
    desc: "Malicious packages injected into the build pipeline to run rogue code.",
  },
};

const DIFFICULTY_COLOR: Record<string, string> = {
  beginner: "text-green-400 border-green-500/40 bg-green-500/10",
  intermediate: "text-yellow-400 border-yellow-500/40 bg-yellow-500/10",
  advanced: "text-red-400 border-red-500/40 bg-red-500/10",
};

const SCENARIO_BULLETS: Record<string, string[]> = {
  "api.idor_orders": [
    "Attacker cycles order IDs to access other users' data",
    "AI detects sequential enumeration pattern",
    "IDOR (Broken Access Control) — OWASP A01",
  ],
  "api.brute_force": [
    "Rapid failed login attempts from attacker IP",
    "Auth burst triggers brute-force detection",
    "MITRE T1110: Brute Force",
  ],
  "web.app.sqli_login": [
    "SQL injection payload injected into login form",
    "Database query manipulation detected",
    "OWASP A03: Injection / MITRE T1190",
  ],
  "net.recon_lateral": [
    "Port scan maps open services on target network",
    "Attacker pivots laterally between hosts",
    "Bulk data exfiltration as final step",
  ],
  "supply.malicious_package": [
    "Compromised npm-style package runs postinstall hook",
    "Shell commands executed in build environment",
    "Environment secrets exfiltrated to external sink",
  ],
};

export default function ScenariosPage() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<ScenarioSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);

  useEffect(() => {
    void authedRequest(() => api.scenarios())
      .then(setScenarios)
      .catch((e: Error) => setError(e.message));
  }, []);

  const startingRef = useRef(false);

  async function start(scenarioId: string) {
    if (startingRef.current) return;
    startingRef.current = true;
    setStarting(scenarioId);
    try {
      const created = await authedRequest(() => api.createSimulation(scenarioId, {}));
      router.push(`/simulations/${created.simulation_id}`);
    } catch (e) {
      setError((e as Error).message);
      setStarting(null);
      startingRef.current = false;
    }
  }

  if (error) {
    return <div className="p-8 text-sm text-red-400">Failed to load scenarios: {error}</div>;
  }
  if (!scenarios) {
    return <div className="flex justify-center p-16"><Spinner size={20} /></div>;
  }

  const byCategory = scenarios.reduce<Record<string, ScenarioSummary[]>>((acc, s) => {
    (acc[s.category] ??= []).push(s);
    return acc;
  }, {});

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-8">
        <h1 className="mb-2 text-2xl font-bold text-slate-100">Scenario Library</h1>
        <p className="text-slate-400 text-sm max-w-xl">
          Run a controlled cyberattack simulation. The AI analyst watches in real time,
          detects threats, explains what happened, and recommends how to respond.
        </p>
      </div>

      {Object.entries(byCategory).map(([category, items]) => {
        const meta = CATEGORY_META[category];
        const Icon = meta?.icon ?? ShieldAlert;
        return (
          <section key={category} className="mb-10">
            <div className="mb-3 flex items-center gap-2">
              <Icon className={clsx("h-4 w-4", meta?.color.split(" ")[0] ?? "text-slate-400")} />
              <h2 className="text-sm font-semibold text-slate-300">
                {meta?.label ?? category.replace(/_/g, " ")}
              </h2>
              {meta?.desc && (
                <p className="text-xs text-slate-500 hidden md:block">— {meta.desc}</p>
              )}
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {items.map((s) => {
                const bullets = SCENARIO_BULLETS[s.id] ?? [];
                const diffColor = DIFFICULTY_COLOR[s.display.difficulty] ?? "text-slate-400 border-slate-600";
                const isStarting = starting === s.id;
                return (
                  <div
                    key={s.id}
                    className="group flex flex-col rounded-xl border border-white/8 bg-[#111115] p-5 transition-all hover:border-white/15 hover:bg-[#14141a]"
                  >
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div className="flex-1 min-w-0">
                        <h3 className="text-base font-semibold text-slate-100 leading-tight">
                          {s.display.title}
                        </h3>
                        <p className="mt-1 text-sm text-slate-400 leading-relaxed">
                          {s.display.blurb}
                        </p>
                      </div>
                    </div>

                    {bullets.length > 0 && (
                      <ul className="mb-4 space-y-1">
                        {bullets.map((b, i) => (
                          <li key={i} className="flex items-start gap-2 text-xs text-slate-500">
                            <Zap className="mt-0.5 h-3 w-3 shrink-0 text-violet-500" />
                            <span>{b}</span>
                          </li>
                        ))}
                      </ul>
                    )}

                    <div className="mt-auto flex items-center gap-2">
                      <span className={clsx(
                        "rounded border px-2 py-0.5 text-xs font-medium capitalize",
                        diffColor
                      )}>
                        {s.display.difficulty}
                      </span>
                      <span className="text-xs text-slate-600">
                        ~{Math.round(s.display.duration_sec / 60)} min
                      </span>
                      <button
                        className={clsx(
                          "ml-auto flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition-all",
                          starting !== null && !isStarting
                            ? "cursor-not-allowed bg-white/5 text-slate-500"
                            : "bg-violet-600 text-white hover:bg-violet-500 shadow-[0_0_20px_rgba(139,92,246,0.3)] hover:shadow-[0_0_30px_rgba(139,92,246,0.5)]"
                        )}
                        disabled={starting !== null}
                        onClick={() => void start(s.id)}
                      >
                        {isStarting ? <Spinner size={14} /> : <Play className="h-3.5 w-3.5" />}
                        {isStarting ? "Starting…" : "Run simulation"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
