/**
 * Billing & plan page (docs/16 §6): current plan, entitlements, usage meters,
 * upgrade + customer-portal actions.
 */

"use client";

import { useEffect, useState } from "react";
import { CreditCard, ExternalLink } from "lucide-react";

import { api, authedRequest, ApiError } from "@/lib/api/client";
import type { BillingPlan } from "@/lib/api/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { PlanBadge } from "@/components/billing/PlanBadge";
import { UsageMeter } from "@/components/billing/UsageMeter";

function fmtMinutes(v: number): string {
  return `${v} min`;
}

function fmtTokens(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}k`;
  return String(v);
}

export default function BillingPage() {
  const [plan, setPlan] = useState<BillingPlan | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    void authedRequest(() => api.billingPlan())
      .then(setPlan)
      .catch((e: Error) => setNotice(e.message));
  }, []);

  async function runAction(kind: "checkout" | "portal"): Promise<void> {
    setBusy(kind);
    setNotice(null);
    try {
      const res =
        kind === "checkout"
          ? await authedRequest(() => api.billingCheckout())
          : await authedRequest(() => api.billingPortal());
      window.location.href = res.url;
    } catch (e) {
      if (e instanceof ApiError && e.code === "GENERAL.NOT_IMPLEMENTED") {
        setNotice("Stripe checkout lands with the Phase 10 backend wiring.");
      } else {
        setNotice((e as Error).message);
      }
    } finally {
      setBusy(null);
    }
  }

  if (!plan) {
    return (
      <div className="flex justify-center p-16">
        <Spinner size={20} />
      </div>
    );
  }

  const { entitlements: ent, current_period_usage: usage } = plan;
  const meters: Array<{
    label: string;
    used: number;
    cap: number | undefined;
    format?: (v: number) => string;
  }> = [
    {
      label: "Simulation minutes",
      used: usage.sim_minutes ?? 0,
      cap: ent.sim_minutes_month,
      format: fmtMinutes,
    },
    {
      label: "LLM tokens",
      used: usage.llm_tokens ?? 0,
      cap: undefined,
      format: fmtTokens,
    },
    {
      label: "Missions started",
      used: usage.missions_started ?? 0,
      cap: ent.missions_month,
    },
    {
      label: "Exports",
      used: usage.exports ?? 0,
      cap: undefined,
    },
  ];

  const entitlementsRows: Array<[string, string]> = [
    ["Concurrent simulations", String(ent.max_concurrent_sims)],
    ["AI tier", ent.ai_tier],
    ["Retention", ent.retention_days ? `${ent.retention_days} days` : "—"],
    [
      "Public mission links / day",
      ent.public_mission_links_per_day
        ? String(ent.public_mission_links_per_day)
        : "—",
    ],
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
      <header className="flex items-center gap-2">
        <CreditCard className="text-cs-accent-fg h-5 w-5" aria-hidden />
        <h1 className="text-2xl font-semibold">Billing & plan</h1>
        <span className="ml-2">
          <PlanBadge plan={plan.plan} />
        </span>
      </header>

      {notice && (
        <div className="rounded-cs-sm bg-cs-warn-bg text-cs-warn-fg px-2 py-1 text-xs">
          {notice}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader title="Plan entitlements" />
          <dl className="space-y-2 p-3 text-sm">
            {entitlementsRows.map(([label, value]) => (
              <div key={label} className="flex items-center justify-between">
                <dt className="text-cs-text-tertiary">{label}</dt>
                <dd className="font-mono">{value}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card>
          <CardHeader title="Usage this period" />
          <div className="space-y-4 p-3">
            {meters.map((m) => (
              <UsageMeter
                key={m.label}
                label={m.label}
                used={m.used}
                cap={m.cap ?? 0}
                {...(m.format ? { format: m.format } : {})}
              />
            ))}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Manage subscription" />
        <div className="flex flex-wrap items-center gap-3 p-3">
          <Button
            variant="primary"
            size="lg"
            disabled={busy !== null}
            onClick={() => void runAction("checkout")}
          >
            {busy === "checkout" ? <Spinner size={16} /> : "Upgrade to Pro"}
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
          </Button>
          <Button
            variant="secondary"
            disabled={busy !== null}
            onClick={() => void runAction("portal")}
          >
            {busy === "portal" ? <Spinner size={16} /> : "Billing portal"}
          </Button>
          <p className="text-cs-text-tertiary text-xs">
            Pro: 5 concurrent sims · 1,000 sim minutes/mo · 90-day retention
            (docs/16 §1).
          </p>
        </div>
      </Card>
    </div>
  );
}
