import { statusPresentation, type StatusKind } from "../lib/status";

interface StatusBadgeProps {
  kind: StatusKind;
  label?: string;
}

export function StatusBadge({ kind, label }: StatusBadgeProps) {
  const presentation = statusPresentation(kind);
  return (
    <span className={presentation.className}>
      <span aria-hidden="true" className="status__symbol">
        {presentation.symbol}
      </span>
      <span>{label ?? presentation.label}</span>
    </span>
  );
}
