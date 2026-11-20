import { describe, expect, test } from "vitest";

import { grantDetailAction } from "./grantDetailAction";

describe("detail next action follows canonical status, not source presence", () => {
  test("open retains applicant comparison but unknown requirements are not eligibility", () => {
    expect(grantDetailAction("OPEN", true, 2)).toMatchObject({
      applicationCandidate: true,
      projectLabel: "Přidat k projektu",
      heading: "Porovnejte známé požadavky s vaším projektem.",
    });
    expect(grantDetailAction("OPEN", false, 0).explanation).toContain("způsobilost neoznačujeme");
  });

  test.each(["PLANNED", "ANNOUNCED", "PAUSED", "CLOSED", "CANCELLED", "ARCHIVED", "UNRECOGNIZED"])(
    "%s never offers an active application CTA",
    (status) => {
      const action = grantDetailAction(status, true, 2);
      expect(action.applicationCandidate).toBe(false);
      expect(action.projectLabel).toBe("Uložit k projektu pro sledování");
      expect(action.explanation).not.toContain("Máme 2 strukturovaných požadavků");
    },
  );
  test("cancellation has explicit canonical-status caveat", () => {
    expect(grantDetailAction("CANCELLED", false, 0).explanation).toContain("ne závěr ze zmizení");
  });
});
