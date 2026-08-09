/** Missions list (docs/14 §3). */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Swords } from "lucide-react";

import { api, authedRequest } from "@/lib/api/client";
import type { BillingPlan } from "@/lib/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";

interface MissionSummary {
  id: string;
  title: string;
  subtitle: string;
  simulator: string;
  scenario_id: string;
  duration_sec: number;
  objectives: Array<{
    id: string;
    title: string;
    kind: string;
    points: number;
  }>;
  max_score: number;
  shareable: boolean;
}

export default function MissionsPage() {
  const [missions, setMissions] = useState<MissionSummary[] | null>(null);
  const [billing, setBilling] = useState<BillingPlan | null>(null);

  useEffect(() => {
    void authedRequest(() => api.get("/missions") as Promise<MissionSummary[]>)
      .then(setMissions)
      .catch(() => setMissions([]));
    void authedRequest(() => api.billingPlan())
      .then(setBilling)
      .catch(() => undefined);
  }, []);

  const missionsUsed = billing?.current_period_usage.missions_started ?? 0;
  const missionsCap = billing?.entitlements.missions_month;

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-1 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Missions</h1>
        {missionsCap !== undefined && (
          <span className="rounded-cs-xs border-cs-border-default bg-cs-neutral-2 text-cs-text-tertiary border px-2 py-1 font-mono text-xs">
            {missionsUsed} of {missionsCap} missions this month
          </span>
        )}
      </div>
      <p className="text-cs-text-secondary mb-6 text-sm">
        Interactive, scored attack/defense scenarios — protect the environment
        and earn points (docs/14).
      </p>

      {!missions ? (
        <div className="flex justify-center p-16">
          <Spinner size={20} />
        </div>
      ) : missions.length === 0 ? (
        <Card className="p-4">
          <p className="text-cs-text-secondary text-sm">
            No missions available yet.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {missions.map((m) => (
            <Card key={m.id} className="p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <Swords className="text-cs-accent-fg h-4 w-4" aria-hidden />
                  <h3 className="text-md font-medium">{m.title}</h3>
                </div>
                <span className="rounded-cs-xs bg-cs-accent-bg text-cs-accent-fg px-1.5 py-0.5 font-mono text-xs">
                  {m.simulator}
                </span>
              </div>
              <p className="text-cs-text-secondary mt-1 text-sm">
                {m.subtitle}
              </p>
              <p className="text-cs-text-tertiary mt-2 text-xs">
                {m.objectives.length} objectives · max {m.max_score} pts ·{" "}
                {m.duration_sec}s
              </p>
              <div className="mt-3">
                <Link href={`/missions/${m.id}`}>
                  <Button variant="primary" size="sm">
                    Play
                  </Button>
                </Link>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
