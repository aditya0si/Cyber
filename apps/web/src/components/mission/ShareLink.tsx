/** ShareLink (docs/14 §5): copy-to-clipboard for the judge share URL. */

"use client";

import { useState } from "react";
import { Check, Link2 } from "lucide-react";

import { Button } from "@/components/ui/Button";

export function ShareLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(window.location.origin + url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — ignore */
    }
  }

  return (
    <Button size="sm" variant="secondary" onClick={() => void copy()}>
      {copied ? (
        <Check className="text-cs-ok-fg h-3.5 w-3.5" aria-hidden />
      ) : (
        <Link2 className="h-3.5 w-3.5" aria-hidden />
      )}
      {copied ? "Link copied" : "Copy judge link"}
    </Button>
  );
}
