import { describe, expect, it } from "vitest";

import {
  buildGrantComparison,
  type ComparisonGrant,
} from "./comparison";

function grant(
  id: string,
  overrides: Partial<ComparisonGrant> = {},
): ComparisonGrant {
  return {
    id,
    title: `Výzva ${id}`,
    provider: "Testovací poskytovatel",
    statusLabel: "Lze podat žádost",
    eligibility: "NEEDS_INFORMATION",
    eligibilityLabel: "Potřebujeme 1 údaj",
    deadlineLabel: "31. 12. 2026",
    supportLabel: "Až 80 %",
    ownFundsLabel: "Zatím neúplný výpočet",
    requiredItemsCount: 5,
    unknownItemsCount: 1,
    sourceLabel: "Oficiální zdroj",
    sourceVerifiedAtLabel: "23. 9. 2026",
    detailHref: `/dotace/${id}`,
    ...overrides,
  };
}

describe("buildGrantComparison", () => {
  it("porovnává 2–3 výzvy bez výběru vítěze", () => {
    const model = buildGrantComparison([grant("a"), grant("b"), grant("c")]);

    expect(model.grants).toHaveLength(3);
    expect(model.rows.map((row) => row.key)).toContain("eligibility");
    expect(model.rows.map((row) => row.key)).toContain("source");
    expect("winner" in model).toBe(false);
    expect("best" in model).toBe(false);
  });

  it("zachovává UNKNOWN/NEEDS_INFORMATION jako explicitní stav", () => {
    const model = buildGrantComparison([
      grant("a", {
        eligibility: "NEEDS_INFORMATION",
        eligibilityLabel: "Potřebujeme ověřit vlastnictví",
      }),
      grant("b", {
        eligibility: "ELIGIBLE",
        eligibilityLabel: "Známé podmínky splněny",
      }),
    ]);

    expect(model.grants[0]?.eligibility).toBe("NEEDS_INFORMATION");
    expect(model.rows.find((row) => row.key === "eligibility")?.values[0])
      .toBe("Potřebujeme ověřit vlastnictví");
  });

  it("nepřepisuje neověřený počet požadavků nulou", () => {
    const model = buildGrantComparison([
      grant("a", { requiredItemsCount: null }),
      grant("b", { requiredItemsCount: 4 }),
    ]);
    const row = model.rows.find((item) => item.key === "requirements");

    expect(row?.values).toEqual(["Zatím neověřeno", "4"]);
  });

  it("odmítne méně než dvě nebo více než tři výzvy", () => {
    expect(() => buildGrantComparison([grant("a")])).toThrow();
    expect(() =>
      buildGrantComparison([
        grant("a"),
        grant("b"),
        grant("c"),
        grant("d"),
      ]),
    ).toThrow();
  });

  it("odmítne duplicitní výzvu", () => {
    expect(() => buildGrantComparison([grant("a"), grant("a")])).toThrow();
  });
});
