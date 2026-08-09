/**
 * ExecuteActionDialog (docs/14 §3.1): action picker + impact summary + AI
 * recommendation. High-risk actions require a second click to confirm.
 */

"use client";

import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { AlertTriangle, X } from "lucide-react";
import { clsx } from "clsx";

import type { Detection } from "@/lib/api/types";
import { Button } from "@/components/ui/Button";
import { SeverityBadge } from "@/components/ui/SeverityBadge";

const HIGH_RISK_ACTIONS = new Set(["quarantine_host", "block_egress"]);

export function ExecuteActionDialog({
  detection,
  open,
  onOpenChange,
  onExecute,
}: {
  detection: Detection | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onExecute: (actionId: string, confirmed: boolean) => Promise<void>;
}) {
  const [selectedAction, setSelectedAction] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  function reset() {
    setConfirming(false);
    setBusy(false);
  }

  function close() {
    reset();
    onOpenChange(false);
  }

  const isHighRisk =
    detection !== null && HIGH_RISK_ACTIONS.has(selectedAction ?? "");
  const action =
    detection?.recommended_actions.find(
      (a) => a.action_id === selectedAction,
    ) ?? null;

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="bg-cs-overlay fixed inset-0 z-40" />
        <Dialog.Content className="border-cs-border-strong bg-cs-neutral-1 rounded-cs-md fixed top-1/2 left-1/2 z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 border p-4 shadow-[var(--cs-shadow-3)]">
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="text-base font-semibold">
              {detection ? (
                <span className="flex items-center gap-2">
                  <SeverityBadge severity={detection.severity} />
                  Execute response
                </span>
              ) : (
                "Execute response"
              )}
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                className="text-cs-text-tertiary hover:text-cs-text-primary"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {detection && (
            <>
              <p className="text-cs-text-tertiary mt-1 text-sm">
                {detection.title}
              </p>

              <Dialog.Description className="sr-only">
                Choose a response action for the selected detection.
              </Dialog.Description>

              {/* Action picker */}
              <div
                className="mt-4 space-y-2"
                role="radiogroup"
                aria-label="Response actions"
              >
                {detection.recommended_actions.map((a) => {
                  const selected = a.action_id === selectedAction;
                  return (
                    <button
                      key={a.action_id}
                      role="radio"
                      aria-checked={selected}
                      onClick={() => {
                        setSelectedAction(a.action_id);
                        setConfirming(false);
                      }}
                      className={clsx(
                        "rounded-cs-sm w-full border px-3 py-2 text-left transition-colors",
                        selected
                          ? "border-cs-accent-fg bg-cs-accent-bg"
                          : "border-cs-border-default hover:bg-cs-neutral-3",
                      )}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-sm">
                          {a.action_id.replace(/_/g, " ")}
                        </span>
                        {HIGH_RISK_ACTIONS.has(a.action_id) && (
                          <span className="text-cs-sev-critical-fg flex items-center gap-1 text-xs">
                            <AlertTriangle className="h-3 w-3" aria-hidden />
                            High risk
                          </span>
                        )}
                      </div>
                      <p className="text-cs-text-tertiary mt-0.5 text-xs">
                        {a.rationale}
                      </p>
                    </button>
                  );
                })}
              </div>

              {/* AI recommendation */}
              {detection.recommended_actions[0] && (
                <p className="text-cs-text-tertiary mt-3 text-xs italic">
                  AI recommendation:{" "}
                  <span className="text-cs-text-secondary">
                    {detection.recommended_actions[0].action_id.replace(
                      /_/g,
                      " ",
                    )}
                  </span>
                  {action &&
                  action.action_id !==
                    detection.recommended_actions[0].action_id
                    ? " — deviating from the recommended action."
                    : ""}
                </p>
              )}

              {isHighRisk && (
                <div className="rounded-cs-sm bg-cs-sev-critical-bg text-cs-sev-critical-fg mt-3 px-3 py-2 text-xs">
                  This action is high-risk. It may disrupt service or isolate
                  hosts. Confirm twice to proceed.
                </div>
              )}

              <div className="mt-4 flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={close}>
                  Cancel
                </Button>
                <Button
                  variant={isHighRisk ? "danger" : "primary"}
                  size="sm"
                  disabled={!selectedAction || busy}
                  onClick={() => {
                    if (isHighRisk && !confirming) {
                      setConfirming(true);
                      return;
                    }
                    if (!selectedAction) return;
                    setBusy(true);
                    void onExecute(selectedAction, isHighRisk).finally(() => {
                      setBusy(false);
                      close();
                    });
                  }}
                >
                  {busy
                    ? "Executing…"
                    : isHighRisk && !confirming
                      ? "Confirm execution"
                      : "Execute response"}
                </Button>
              </div>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
