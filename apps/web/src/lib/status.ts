export type StatusKind =
  | "success"
  | "warning"
  | "error"
  | "info"
  | "unknown";

export interface StatusPresentation {
  label: string;
  symbol: string;
  className: string;
}

const presentations: Record<StatusKind, StatusPresentation> = {
  success: {
    label: "Splněno",
    symbol: "✓",
    className: "status status--success",
  },
  warning: {
    label: "Vyžaduje pozornost",
    symbol: "!",
    className: "status status--warning",
  },
  error: {
    label: "Nesplněno",
    symbol: "×",
    className: "status status--error",
  },
  info: {
    label: "Informace",
    symbol: "i",
    className: "status status--info",
  },
  unknown: {
    label: "Potřebujeme doplnit",
    symbol: "?",
    className: "status status--unknown",
  },
};

export function statusPresentation(kind: StatusKind): StatusPresentation {
  return presentations[kind];
}
