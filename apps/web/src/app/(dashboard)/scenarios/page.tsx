/** Scenario picker (docs/02 §5.1 journey A entry). */

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Play } from "lucide-react";

import { api, authedRequest } from "@/lib/api/client";
import type { ScenarioSummary } from "@/lib/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";

const CATEGORY_LABELS: Record<string, string> = {
  web_application_attack: "Web application attack",
  api_abuse: "API abuse",
  credential_attack: "Credential attack",
  network_intrusion: "Network intrusion",
  supply_chain_compromise: "Supply-chain compromise",
  phishing_social_engineering: "Phishing / social engineering",
  cloud_misconfiguration: "Cloud misconfiguration",
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

  async function start(scenarioId: string) {
    setStarting(scenarioId);
    try {
      const created = await authedRequest(() =>
        api.createSimulation(scenarioId, {}),
      );
      router.push(`/simulations/${created.simulation_id}`);
    } catch (e) {
      setError((e as Error).message);
      setStarting(null);
    }
  }

  if (error) {
    return (
      <div className="text-cs-error-fg p-8 text-sm">
        Failed to load scenarios: {error}
      </div>
    );
  }
  if (!scenarios) {
    return (
      <div className="flex justify-center p-16">
        <Spinner size={20} />
      </div>
    );
  }

  const byCategory = scenarios.reduce<Record<string, ScenarioSummary[]>>(
    (acc, s) => {
      (acc[s.category] ??= []).push(s);
      return acc;
    },
    {},
  );

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h1 className="mb-1 text-2xl font-semibold">Scenario Library</h1>
      <p className="text-cs-text-secondary mb-6 text-sm">
        Pick a controlled attack scenario to simulate; the AI analyst will
        detect, explain, and recommend responses.
      </p>

      {Object.entries(byCategory).map(([category, items]) => (
        <section key={category} className="mb-8">
          <h2 className="text-cs-text-tertiary mb-2 text-sm font-medium tracking-wide uppercase">
            {CATEGORY_LABELS[category] ?? category}
          </h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {items.map((s) => (
              <Card key={s.id} className="p-4">
                <h3 className="text-md font-medium">{s.display.title}</h3>
                <p className="text-cs-text-secondary mt-1 text-sm">
                  {s.display.blurb}
                </p>
                <div className="mt-3 flex items-center justify-between">
                  <span className="text-cs-text-tertiary text-xs">
                    {s.display.difficulty} · {s.display.duration_sec}s
                  </span>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={starting !== null}
                    onClick={() => void start(s.id)}
                  >
                    {starting === s.id ? (
                      <Spinner size={10} />
                    ) : (
                      <Play className="h-3.5 w-3.5" />
                    )}
                    Start
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
