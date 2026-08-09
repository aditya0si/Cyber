/** Auth pages (docs/13 §2). */

"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth, AuthProvider } from "@/lib/auth/AuthProvider";
import { Button } from "@/components/ui/Button";

export default function LoginPage() {
  return (
    <AuthProvider>
      <LoginForm />
    </AuthProvider>
  );
}

function LoginForm() {
  const { login, register } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
      router.push("/scenarios");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-cs-neutral-0 text-cs-text-primary flex min-h-screen flex-col items-center justify-center p-4">
      <form
        onSubmit={(e) => void submit(e)}
        className="rounded-cs-lg border-cs-border-default bg-cs-neutral-2 w-full max-w-sm space-y-4 border p-6 shadow-[var(--cs-shadow-2)]"
      >
        <div>
          <h1 className="font-mono text-xl font-semibold">
            CyberSim <span className="text-cs-accent-fg">AI</span>
          </h1>
          <p className="text-cs-text-secondary mt-1 text-sm">
            {mode === "login"
              ? "Sign in to the SOC console"
              : "Create your workspace"}
          </p>
        </div>

        <label className="block text-sm">
          <span className="text-cs-text-secondary">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="rounded-cs-sm border-cs-border-default bg-cs-neutral-1 focus:border-cs-border-focus mt-1 w-full border px-3 py-2 text-sm"
          />
        </label>

        <label className="block text-sm">
          <span className="text-cs-text-secondary">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={mode === "register" ? 12 : 1}
            className="rounded-cs-sm border-cs-border-default bg-cs-neutral-1 focus:border-cs-border-focus mt-1 w-full border px-3 py-2 text-sm"
          />
        </label>

        {error && <p className="text-cs-error-fg text-xs">{error}</p>}

        <Button
          type="submit"
          variant="primary"
          className="w-full"
          disabled={busy}
        >
          {mode === "login" ? "Sign in" : "Create account"}
        </Button>

        <button
          type="button"
          onClick={() => setMode((m) => (m === "login" ? "register" : "login"))}
          className="text-cs-text-tertiary hover:text-cs-text-secondary w-full text-center text-xs"
        >
          {mode === "login"
            ? "No account? Register"
            : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
