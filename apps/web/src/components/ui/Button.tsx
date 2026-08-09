/** Design-system button (docs/02 §4.9). */

import { forwardRef, type ButtonHTMLAttributes } from "react";
import { clsx } from "clsx";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-cs-accent text-cs-text-inverse hover:bg-[var(--cs-accent-fg-hover)]",
  secondary: "border border-cs-border-default hover:bg-cs-neutral-3",
  ghost: "hover:bg-cs-neutral-3",
  danger: "bg-cs-sev-critical-fg text-cs-text-inverse hover:opacity-90",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs",
  md: "h-9 px-4 text-sm",
  lg: "h-11 px-5 text-md",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { className, variant = "secondary", size = "md", ...props },
    ref,
  ) {
    return (
      <button
        ref={ref}
        className={clsx(
          "rounded-cs-md inline-flex items-center justify-center gap-2 font-medium",
          "transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-40",
          "focus-visible:shadow-[var(--cs-ring)]",
          VARIANTS[variant],
          SIZES[size],
          className,
        )}
        {...props}
      />
    );
  },
);
