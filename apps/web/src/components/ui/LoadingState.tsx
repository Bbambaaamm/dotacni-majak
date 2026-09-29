export interface LoadingStateProps {
  /** Visible label announced to screen readers and shown visually. */
  label?: string;
  /** Size variant: "sm" | "md" | "lg" (default: "md"). */
  size?: "sm" | "md" | "lg";
}

/**
 * Accessible loading indicator.
 *
 * - `role="status"` for screen readers that support it.
 * - `aria-live="polite"` so screen readers announce when loading starts.
 * - Visible text label (not just a spinner) — status is NOT communicated by
 *   color/spin alone.
 * - `prefers-reduced-motion` honoured in styles.css.
 */
export function LoadingState({
  label = "Načítám…",
  size = "md",
}: LoadingStateProps) {
  const sizeClass = {
    sm: "loading-state loading-state--sm",
    md: "loading-state",
    lg: "loading-state loading-state--lg",
  }[size];

  return (
    <div
      className={sizeClass}
      role="status"
      aria-live="polite"
      aria-label={label || "Načítám…"}
    >
      <span aria-hidden="true" className="loading-state__spinner" />
      {label && <span className="loading-state__label">{label}</span>}
    </div>
  );
}
