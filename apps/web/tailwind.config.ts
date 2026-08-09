import type { Config } from "tailwindcss";

/**
 * Tailwind v4 reads tokens via `@theme` from globals.css / tokens.css.
 * This file keeps the v3-compatible escape hatch for plugin/content discovery.
 * Every token family used in components is mapped here so JIT generates
 * `text-*`, `bg-*`, `border-*` utilities. See docs/02 §8.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        cs: {
          neutral: {
            0: "var(--cs-neutral-0)",
            1: "var(--cs-neutral-1)",
            2: "var(--cs-neutral-2)",
            3: "var(--cs-neutral-3)",
            4: "var(--cs-neutral-4)",
            5: "var(--cs-neutral-5)",
            6: "var(--cs-neutral-6)",
          },
          text: {
            primary: "var(--cs-text-primary)",
            secondary: "var(--cs-text-secondary)",
            tertiary: "var(--cs-text-tertiary)",
            quaternary: "var(--cs-text-quaternary)",
            inverse: "var(--cs-text-inverse)",
          },
          accent: {
            fg: "var(--cs-accent-fg)",
            "fg-hover": "var(--cs-accent-fg-hover)",
            bg: "var(--cs-accent-bg)",
            ring: "var(--cs-accent-ring)",
          },
          sev: {
            info: { fg: "var(--cs-sev-info-fg)", bg: "var(--cs-sev-info-bg)" },
            low: { fg: "var(--cs-sev-low-fg)", bg: "var(--cs-sev-low-bg)" },
            medium: { fg: "var(--cs-sev-medium-fg)", bg: "var(--cs-sev-medium-bg)" },
            high: { fg: "var(--cs-sev-high-fg)", bg: "var(--cs-sev-high-bg)" },
            critical: {
              fg: "var(--cs-sev-critical-fg)",
              bg: "var(--cs-sev-critical-bg)",
            },
          },
          ok: { fg: "var(--cs-ok-fg)", bg: "var(--cs-ok-bg)" },
          warn: { fg: "var(--cs-warn-fg)", bg: "var(--cs-warn-bg)" },
          error: { fg: "var(--cs-error-fg)", bg: "var(--cs-error-bg)" },
          border: {
            subtle: "var(--cs-border-subtle)",
            default: "var(--cs-border-default)",
            strong: "var(--cs-border-strong)",
            focus: "var(--cs-border-focus)",
          },
        },
      },
      borderRadius: {
        cs_xs: "4px",
        cs_sm: "6px",
        cs_md: "8px",
        cs_lg: "12px",
        cs_xl: "16px",
      },
    },
  },
};

export default config;
