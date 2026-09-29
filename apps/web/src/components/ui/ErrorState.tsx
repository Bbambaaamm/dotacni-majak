import type { ReactNode } from "react";

export type ErrorStateVariant = "error" | "unknown";

export interface ErrorStateProps {
  /** Heading describing the error state. */
  title: string;
  /** Optional descriptive text with more detail. */
  description?: string;
  /** Optional retry / recovery action (primary call-to-action). */
  action?: ReactNode;
  /**
   * "error" = a definite failure with guidance.
   * "unknown" = the system cannot determine the outcome (UNKNOWN != FAIL
   *   invariant — the UI must distinguish ambiguity from failure).
   * @default "error"
   */
  variant?: ErrorStateVariant;
}

/**
 * Accessible error / unknown-state indicator.
 *
 * - Visible text always present (not color alone).
 * - `role="alert"` so screen readers announce immediately.
 * - The "unknown" variant explicitly surfaces ambiguity — per the Dotační
 *   maják invariant: `UNKNOWN != FAIL`. The user is told data is missing
 *   and what to do next, rather than being shown a generic error.
 * - Primary action follows the "Co mám udělat teď?" principle.
 */
export function ErrorState({
  title,
  description,
  action,
  variant = "error",
}: ErrorStateProps) {
  const className =
    variant === "unknown"
      ? "error-state error-state--unknown"
      : "error-state";

  const icon = variant === "unknown" ? "⁇" : "×";

  return (
    <div className={className} role="alert">
      <span aria-hidden="true" className="error-state__icon">
        {icon}
      </span>
      <h3 className="error-state__title">{title}</h3>
      {description && (
        <p className="error-state__description">{description}</p>
      )}
      {action && <div className="error-state__action">{action}</div>}
    </div>
  );
}
