/** Pricing page (docs/16 §1): Free / Pro / Enterprise tiers. */

import Link from "next/link";
import { Check, Sparkles } from "lucide-react";
import { clsx } from "clsx";

const TIERS = [
  {
    name: "Free",
    price: "$0",
    cadence: "forever",
    cta: "Start free",
    highlight: false,
    features: [
      "1 concurrent simulation",
      "60 sim minutes / month",
      "3 missions / month",
      "3 public mission links / day",
      "7-day retention",
      "Global knowledge base",
    ],
  },
  {
    name: "Pro",
    price: "$49",
    cadence: "/ month",
    cta: "Upgrade to Pro",
    highlight: true,
    features: [
      "5 concurrent simulations",
      "1,000 sim minutes / month",
      "50 missions / month",
      "Unlimited public mission links",
      "90-day retention",
      "Priority AI tier (gpt-4o on risk/response)",
      "Email support",
    ],
  },
  {
    name: "Enterprise",
    price: "Quote",
    cadence: "per contract",
    cta: "Contact sales",
    highlight: false,
    features: [
      "Per-contract concurrency & usage",
      "365+ day retention",
      "Private knowledge upload",
      "Slack + named support",
    ],
  },
];

export default function PricingPage() {
  return (
    <main>
      <section className="mx-auto max-w-5xl px-6 pt-16 pb-20">
        <div className="text-center">
          <h1 className="text-3xl font-bold">Simple, usage-fair pricing</h1>
          <p className="text-cs-text-secondary mx-auto mt-3 max-w-2xl text-base">
            Metered sim minutes and LLM tokens keep heavy workloads honest — no
            flat-credit surprise. Start free, no card required.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-3">
          {TIERS.map((tier) => (
            <div
              key={tier.name}
              className={clsx(
                "rounded-cs-lg border p-5",
                tier.highlight
                  ? "border-cs-accent-fg bg-cs-accent-bg shadow-[0_0_32px_var(--cs-accent-ring)]"
                  : "border-cs-border-default bg-cs-neutral-2 shadow-[var(--cs-shadow-1)]",
              )}
            >
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold">{tier.name}</h2>
                {tier.highlight && (
                  <Sparkles className="text-cs-accent-fg h-4 w-4" aria-hidden />
                )}
              </div>
              <p className="mt-3">
                <span className="text-3xl font-bold">{tier.price}</span>
                <span className="text-cs-text-tertiary ml-1 text-sm">
                  {tier.cadence}
                </span>
              </p>
              <ul className="mt-4 space-y-2 text-sm">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <Check
                      className="text-cs-ok-fg mt-0.5 h-3.5 w-3.5 shrink-0"
                      aria-hidden
                    />
                    <span className="text-cs-text-secondary">{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                href="/login"
                className={clsx(
                  "rounded-cs-md mt-6 inline-flex h-10 w-full items-center justify-center text-sm font-medium",
                  tier.highlight
                    ? "bg-cs-accent-fg text-cs-text-inverse hover:bg-[var(--cs-accent-fg-hover)]"
                    : "border-cs-border-default hover:bg-cs-neutral-3 border",
                )}
              >
                {tier.cta}
              </Link>
            </div>
          ))}
        </div>

        <p className="text-cs-text-tertiary mt-10 text-center text-sm">
          All prices illustrative (docs/16 §1) — final numbers are
          configuration, not code.
        </p>
      </section>
    </main>
  );
}
