/** Marketing layout (docs/13 §8): public nav + footer, no auth gate. */

import Link from "next/link";
import type { ReactNode } from "react";
import { Network } from "lucide-react";

export default function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className="bg-cs-neutral-0 text-cs-text-primary min-h-screen">
      <header className="border-cs-border-subtle sticky top-0 z-20 border-b bg-[var(--cs-neutral-0)]/90 backdrop-blur">
        <nav className="mx-auto flex h-12 max-w-6xl items-center justify-between px-6">
          <Link
            href="/"
            className="flex items-center gap-2 font-mono text-sm font-semibold"
          >
            <Network className="text-cs-accent-fg h-4 w-4" aria-hidden />
            CyberSim <span className="text-cs-accent-fg">AI</span>
          </Link>
          <div className="flex items-center gap-5 text-sm">
            <Link
              href="/#features"
              className="text-cs-text-secondary hover:text-cs-text-primary"
            >
              Features
            </Link>
            <Link
              href="/pricing"
              className="text-cs-text-secondary hover:text-cs-text-primary"
            >
              Pricing
            </Link>
            <Link
              href="/login"
              className="rounded-cs-md border-cs-border-default hover:bg-cs-neutral-3 border px-3 py-1.5"
            >
              Sign in
            </Link>
            <Link
              href="/login"
              className="rounded-cs-md bg-cs-accent-fg text-cs-text-inverse px-3 py-1.5 font-medium hover:bg-[var(--cs-accent-fg-hover)]"
            >
              Get started
            </Link>
          </div>
        </nav>
      </header>

      {children}

      <footer className="border-cs-border-subtle border-t">
        <div className="text-cs-text-tertiary mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-6 py-6 text-xs">
          <span className="font-mono">
            CyberSim <span className="text-cs-accent-fg">AI</span> — © 2026
          </span>
          <span>
            Controlled scenarios · evidence-grounded analyst · mission mode
          </span>
        </div>
      </footer>
    </div>
  );
}
