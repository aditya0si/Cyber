/** Design-system card (docs/02 §3.7 — borders over shadows in dark). */

import type { HTMLAttributes, ReactNode } from "react";
import { clsx } from "clsx";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function Card({ className, children, ...props }: CardProps) {
  return (
    <div
      className={clsx(
        "rounded-cs-md border-cs-border-default bg-cs-neutral-2 border",
        "shadow-[var(--cs-shadow-1)]",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  right,
}: {
  title: string;
  right?: ReactNode;
}) {
  return (
    <div className="border-cs-border-subtle flex items-center justify-between border-b px-3 py-2">
      <h3 className="text-cs-text-secondary text-sm font-medium">{title}</h3>
      {right}
    </div>
  );
}
