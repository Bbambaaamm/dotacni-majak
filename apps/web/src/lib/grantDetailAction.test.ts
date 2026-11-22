import { describe, expect, test } from "vitest";

import { grantDetailAction } from "./grantDetailAction";

describe("detail next action follows canonical status and source presence", () => {
  test("open retains applicant comparison but unknown requirements are not eligibility", () => {
    expect(grantDetailAction("OPEN", true, 2)).toMatchObject({
      applicationCandidate: true,
      projectLabel: "Přidat k projektu",
      heading: "Porovnejte známé požadavky s vaším projektem.",
    });
    expect(grantDetailAction("OPEN", false, 0).explanation).toContain("způsobilost neoznačujeme");
  });

  test("OPEN with undocumented, missing or mixed source presence leads with verification and keeps project save secondary", () => {
    const action = grantDetailAction("OPEN", false, 0, true);
    expect(action).toMatchObject({
      heading: "Ověřte aktuální dostupnost výzvy u poskytovatele.",
      applicationCandidate: true,
      verificationFirst: true,
      projectLabel: "Přidat k projektu",
    });
    expect(action.explanation).toContain("neznamená zrušení");
    expect(action.explanation).toContain("Výskyt u zdroje není doložen");
    expect(action.explanation).toContain("způsobilost neoznačujeme jako splněnou ani nesplněnou");
    expect(grantDetailAction("OPEN", false, 0)).toMatchObject({ verificationFirst: false });
  });

  test("source disappearance never turns another canonical status into OPEN", () => {
    expect(grantDetailAction("CANCELLED", false, 0, true).applicationCandidate).toBe(false);
    expect(grantDetailAction("PLANNED", false, 0, true).projectLabel).toBeNull();
  });

  test.each(["PLANNED", "ANNOUNCED", "PAUSED", "CLOSED", "CANCELLED", "ARCHIVED", "UNRECOGNIZED"])(
    "%s never offers an active application CTA",
    (status) => {
      const action = grantDetailAction(status, true, 2);
      expect(action.applicationCandidate).toBe(false);
      expect(action.projectLabel).toBeNull();
      expect(action.explanation).not.toContain("Máme 2 strukturovaných požadavků");
    },
  );
  test("cancellation has explicit canonical-status caveat", () => {
    expect(grantDetailAction("CANCELLED", false, 0).explanation).toContain("ne závěr ze zmizení");
  });
});
