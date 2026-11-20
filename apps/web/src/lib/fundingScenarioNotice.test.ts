import { describe, expect, it } from "vitest";
import { fundingScenarioNotice } from "./fundingScenarioNotice";

describe("finance scenario applicability notice", () => {
  it("leaves a linked condition UNKNOWN until evaluated", () => {
    const notice = fundingScenarioNotice({ conditionGroupId: "group:nsa:loan" });
    expect(notice).toContain("UNKNOWN");
    expect(notice).toContain("není vyhodnoceno");
    expect(notice).not.toContain("splněny");
  });

  it("does not treat an unlinked scenario as proven applicable", () => {
    const notice = fundingScenarioNotice({ conditionGroupId: null });
    expect(notice).toContain("nemáme vazbu");
    expect(notice).toContain("nejsou potvrzením nároku");
  });
});
