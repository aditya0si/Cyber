/** AppShell: sidebar + topbar + content (docs/02 §4.1). */

"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  CreditCard,
  FlaskConical,
  LogOut,
  Network,
  Shield,
  UserRound,
} from "lucide-react";
import { clsx } from "clsx";

import { useAuth } from "@/lib/auth/AuthProvider";
import { api, authedRequest } from "@/lib/api/client";
import type { BillingPlan } from "@/lib/api/types";
import { Button } from "@/components/ui/Button";
import { PlanBadge } from "@/components/billing/PlanBadge";
import { UsageMeter } from "@/components/billing/UsageMeter";

const NAV = [
  { href: "/scenarios", label: "Scenario Library", icon: FlaskConical },
  { href: "/simulations", label: "Simulations", icon: Activity },
  { href: "/missions", label: "Missions", icon: Shield },
  { href: "/billing", label: "Billing", icon: CreditCard },
  { href: "/settings", label: "Account", icon: UserRound },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { me, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [billing, setBilling] = useState<BillingPlan | null>(null);

  useEffect(() => {
    void authedRequest(() => api.billingPlan())
      .then(setBilling)
      .catch(() => undefined);
  }, []);

  return (
    <div className="bg-cs-neutral-0 text-cs-text-primary flex h-screen">
      <aside
        className={clsx(
          "border-cs-border-subtle bg-cs-neutral-1 flex shrink-0 flex-col border-r transition-all",
          collapsed ? "w-14" : "w-56",
        )}
      >
        <div className="border-cs-border-subtle flex h-11 items-center gap-2 border-b px-3">
          <Network className="text-cs-accent-fg h-4 w-4" aria-hidden />
          {!collapsed && (
            <Link href="/scenarios" className="font-mono text-sm font-semibold">
              CyberSim <span className="text-cs-accent-fg">AI</span>
            </Link>
          )}
        </div>

        <nav className="flex-1 space-y-1 p-2">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={clsx(
                  "rounded-cs-sm flex items-center gap-2 px-2 py-1.5 text-sm",
                  active
                    ? "bg-cs-accent-bg text-cs-accent-fg"
                    : "text-cs-text-secondary hover:bg-cs-neutral-3",
                )}
                title={collapsed ? label : undefined}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden />
                {!collapsed && label}
              </Link>
            );
          })}
        </nav>

        <div className="border-cs-border-subtle border-t p-2">
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="rounded-cs-sm text-cs-text-tertiary hover:bg-cs-neutral-3 mb-2 w-full px-2 py-1 text-left text-xs"
          >
            {collapsed ? "»" : "Collapse"}
          </button>
          {!collapsed && billing && (
            <div className="mb-2 space-y-2 px-1">
              <div className="flex items-center justify-between">
                <PlanBadge plan={billing.plan} />
                <Link
                  href="/billing"
                  className="text-cs-text-tertiary hover:text-cs-text-primary text-[11px]"
                >
                  usage
                </Link>
              </div>
              <UsageMeter
                label="Sim minutes"
                used={billing.current_period_usage.sim_minutes ?? 0}
                cap={billing.entitlements.sim_minutes_month ?? 0}
                format={(v) => `${v} min`}
              />
            </div>
          )}
          {!collapsed && me && (
            <div className="flex items-center justify-between px-1 text-xs">
              <span className="text-cs-text-tertiary truncate">{me.email}</span>
              <Button
                size="sm"
                variant="ghost"
                onClick={logout}
                aria-label="Log out"
              >
                <LogOut className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
