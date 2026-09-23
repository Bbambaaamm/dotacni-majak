export type PublicSourceHealth =
  | "HEALTHY"
  | "DEGRADED"
  | "UNAVAILABLE";

export interface SourceCoverageEntry {
  code: string;
  name: string;
  category: string;
  status: PublicSourceHealth;
  statusLabel: string;
  lastCheckedLabel: string;
  lastSuccessLabel: string;
  limitation: string | null;
  servesLastKnownGood: boolean;
}

export interface SourceHealthInput {
  code: string;
  name: string;
  category: string;
  status: PublicSourceHealth;
  lastCheckedLabel: string;
  lastSuccessLabel: string | null;
  limitation?: string | null;
}

export function toPublicSourceCoverage(
  input: SourceHealthInput,
): SourceCoverageEntry {
  const lastSuccessLabel = input.lastSuccessLabel ?? "Zatím bez úspěšné kontroly";
  const servesLastKnownGood = input.status !== "HEALTHY";

  return {
    code: input.code,
    name: input.name,
    category: input.category,
    status: input.status,
    statusLabel: statusLabel(input.status),
    lastCheckedLabel: input.lastCheckedLabel,
    lastSuccessLabel,
    limitation: input.limitation ?? null,
    servesLastKnownGood,
  };
}

function statusLabel(status: PublicSourceHealth): string {
  switch (status) {
    case "HEALTHY":
      return "Aktivní";
    case "DEGRADED":
      return "Omezené";
    case "UNAVAILABLE":
      return "Dočasně nedostupné";
  }
}
