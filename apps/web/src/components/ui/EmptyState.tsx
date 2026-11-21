import type { ReactNode } from "react";

export interface EmptyStateProps {
  /** Heading shown to the user. */
  title: string;
  /** Optional descriptive text. */
  description?: string;
  /** Optional primary action (e.g. "Přidat první projekt"). */
  action?: ReactNode;
}

/**
 * Accessible empty state.
 *
 * - Uses `role="status"` so screen readers announce the state change.
 * - An icon is present but `aria-hidden` — the meaning is conveyed by
 *   visible text, never by color/icon alone.
 * - Optional primary action follows the "Co mám udělat teď?" principle.
 */
export function EmptyState({
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      <span aria-hidden="true" className="empty-state__icon">
        ○
      </span>
      <h3 className="empty-state__title">{title}</h3>
      {description && (
        <p className="empty-state__description">{description}</p>
      )}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}
