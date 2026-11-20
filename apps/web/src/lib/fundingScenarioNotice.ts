import type { GrantFundingScenarioDetail } from "./grantDetailApi";

export function fundingScenarioNotice(scenario: Pick<GrantFundingScenarioDetail, "conditionGroupId">): string {
  return scenario.conditionGroupId
    ? "Tento scénář je v pravidlech navázán na podmínky. Jejich splnění pro váš projekt zde není vyhodnoceno (UNKNOWN); uvedené meze podpory nejsou potvrzením nároku. Ověřte podmínky u poskytovatele."
    : "U tohoto scénáře nemáme vazbu na vyhodnocenou skupinu podmínek. Zobrazené meze podpory nejsou potvrzením nároku; ověřte podmínky u poskytovatele.";
}
