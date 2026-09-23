export type EligibilityState =
  | "ELIGIBLE"
  | "LIKELY_ELIGIBLE"
  | "NEEDS_INFORMATION"
  | "INELIGIBLE"
  | "NEEDS_REVIEW";

export interface ComparisonGrant {
  id: string;
  title: string;
  provider: string;
  statusLabel: string;
  eligibility: EligibilityState;
  eligibilityLabel: string;
  deadlineLabel: string;
  supportLabel: string;
  ownFundsLabel: string;
  requiredItemsCount: number | null;
  unknownItemsCount: number;
  sourceLabel: string;
  sourceVerifiedAtLabel: string;
  detailHref: string;
}

export interface ComparisonRow {
  key:
    | "status"
    | "eligibility"
    | "support"
    | "ownFunds"
    | "deadline"
    | "requirements"
    | "unknowns"
    | "source";
  label: string;
  values: readonly string[];
}

export interface GrantComparisonModel {
  grants: readonly ComparisonGrant[];
  rows: readonly ComparisonRow[];
}

export function buildGrantComparison(
  grants: readonly ComparisonGrant[],
): GrantComparisonModel {
  if (grants.length < 2) {
    throw new Error("Porovnání vyžaduje alespoň 2 výzvy.");
  }
  if (grants.length > 3) {
    throw new Error("Porovnat lze maximálně 3 výzvy.");
  }

  const ids = new Set(grants.map((grant) => grant.id));
  if (ids.size !== grants.length) {
    throw new Error("Porovnání nesmí obsahovat stejnou výzvu vícekrát.");
  }

  return {
    grants: [...grants],
    rows: [
      {
        key: "status",
        label: "Stav",
        values: grants.map((grant) => grant.statusLabel),
      },
      {
        key: "eligibility",
        label: "Způsobilost",
        values: grants.map((grant) => grant.eligibilityLabel),
      },
      {
        key: "support",
        label: "Podpora",
        values: grants.map((grant) => grant.supportLabel),
      },
      {
        key: "ownFunds",
        label: "Vlastní prostředky",
        values: grants.map((grant) => grant.ownFundsLabel),
      },
      {
        key: "deadline",
        label: "Termín",
        values: grants.map((grant) => grant.deadlineLabel),
      },
      {
        key: "requirements",
        label: "Známé povinné položky",
        values: grants.map((grant) =>
          grant.requiredItemsCount === null
            ? "Zatím neověřeno"
            : String(grant.requiredItemsCount),
        ),
      },
      {
        key: "unknowns",
        label: "Chybějící informace",
        values: grants.map((grant) => String(grant.unknownItemsCount)),
      },
      {
        key: "source",
        label: "Zdroj",
        values: grants.map(
          (grant) =>
            `${grant.sourceLabel} · ověřeno ${grant.sourceVerifiedAtLabel}`,
        ),
      },
    ],
  };
}
