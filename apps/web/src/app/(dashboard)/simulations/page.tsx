/** Simulations list (docs/08 §4.4). */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { api, authedRequest } from "@/lib/api/client";
import type { SimulationSummary } from "@/lib/api/types";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";

export default function SimulationsPage() {
  const [sims, setSims] = useState<SimulationSummary[] | null>(null);

  useEffect(() => {
    void authedRequest(() => api.simulations()).then(setSims);
  }, []);

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h1 className="mb-6 text-2xl font-semibold">Simulations</h1>
      {!sims ? (
        <div className="flex justify-center p-16">
          <Spinner size={20} />
        </div>
      ) : sims.length === 0 ? (
        <p className="text-cs-text-secondary text-sm">
          No simulations yet — start one from the Scenario Library.
        </p>
      ) : (
        <div className="space-y-2">
          {sims.map((s) => (
            <Link key={s.id} href={`/simulations/${s.id}`}>
              <Card className="hover:bg-cs-neutral-3 flex items-center justify-between p-3">
                <div>
                  <p className="text-sm font-medium">{s.scenario_id}</p>
                  <p className="text-cs-text-tertiary text-xs">
                    {s.status} · {s.events_count} events · {s.detections_count}{" "}
                    detections
                  </p>
                </div>
                <span className="text-cs-text-tertiary text-xs">
                  {s.created_at}
                </span>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
