/** Account settings (docs/19 Phase 12): profile from /v1/me + session actions. */

"use client";

import { useEffect, useState } from "react";
import { UserRound } from "lucide-react";

import { api, authedRequest } from "@/lib/api/client";
import type { BillingPlan, MeResponse } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { PlanBadge } from "@/components/billing/PlanBadge";

export default function SettingsPage() {
  const { logout } = useAuth();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [billing, setBilling] = useState<BillingPlan | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void authedRequest(() => api.me())
      .then(setMe)
      .catch((e: Error) => setNotice(e.message));
    void authedRequest(() => api.billingPlan())
      .then(setBilling)
      .catch(() => undefined);
  }, []);

  if (!me) {
    return (
      <div className="flex justify-center p-16">
        <Spinner size={20} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4 p-6">
      <header className="flex items-center gap-2">
        <UserRound className="text-cs-accent-fg h-5 w-5" aria-hidden />
        <h1 className="text-2xl font-semibold">Account</h1>
      </header>

      {notice && (
        <div className="rounded-cs-sm bg-cs-warn-bg text-cs-warn-fg px-2 py-1 text-xs">
          {notice}
        </div>
      )}

      <Card>
        <CardHeader title="Profile" />
        <dl className="space-y-2 p-3 text-sm">
          <div className="flex items-center justify-between">
            <dt className="text-cs-text-tertiary">Email</dt>
            <dd className="font-mono">{me.email}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-cs-text-tertiary">Role</dt>
            <dd className="font-mono">{me.role}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-cs-text-tertiary">Organization</dt>
            <dd className="font-mono">{me.org.name}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-cs-text-tertiary">Plan</dt>
            <dd>
              <PlanBadge plan={billing?.plan ?? "free"} />
            </dd>
          </div>
        </dl>
      </Card>

      <Card>
        <CardHeader title="Session" />
        <div className="p-3">
          <Button variant="danger" onClick={logout}>
            Sign out
          </Button>
        </div>
      </Card>
    </div>
  );
}
