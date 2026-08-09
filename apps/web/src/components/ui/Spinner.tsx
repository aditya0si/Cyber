/** Inline spinner (docs/02 §4.9 loading state). */

export function Spinner({ size = 12 }: { size?: number }) {
  return (
    <span
      className="border-cs-border-strong border-t-cs-accent-fg inline-block animate-spin rounded-full border-2"
      style={{ width: size, height: size }}
      aria-label="loading"
    />
  );
}
