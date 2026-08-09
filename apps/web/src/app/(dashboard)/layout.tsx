/** Dashboard layout: shell + auth gate (docs/13 §8). */

"use client";

import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { AuthProvider, useAuth } from "@/lib/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";

function Gate({ children }: { children: ReactNode }) {
  const { loggedIn, loading } = useAuth();
  if (loading) {
    return (
      <div className="bg-cs-neutral-0 flex h-screen items-center justify-center">
        <Spinner size={20} />
      </div>
    );
  }
  if (!loggedIn) {
    return (
      <div className="bg-cs-neutral-0 text-cs-text-primary flex h-screen flex-col items-center justify-center gap-4">
        <p className="font-mono text-lg">CyberSim AI</p>
        <p className="text-cs-text-secondary text-sm">
          Sign in to open the SOC console.
        </p>
        <div className="flex gap-2">
          <Button
            onClick={() => {
              window.location.href = "/login";
            }}
          >
            Log in
          </Button>
        </div>
      </div>
    );
  }
  return <AppShell>{children}</AppShell>;
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <Gate>{children}</Gate>
    </AuthProvider>
  );
}
