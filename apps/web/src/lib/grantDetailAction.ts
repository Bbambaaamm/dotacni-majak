// A canonical status describes the captured call, not a live guarantee that applications are open.
// Source-record disappearance must never be interpreted as cancellation.
export function grantDetailAction(status: string, requirementsKnown: boolean, requirementCount: number) {
  switch (status) {
    case "OPEN":
      return {
        heading: requirementsKnown
          ? "Porovnejte známé požadavky s vaším projektem."
          : "Uložte výzvu k projektu a ověřte kompletní podmínky v oficiálním zdroji.",
        explanation: requirementsKnown
          ? `Máme ${requirementCount} strukturovaných požadavků. Konkrétní způsobilost se vyhodnotí proti profilu žadatele a projektu.`
          : "Maják zatím nemá všechny podmínky této výzvy normalizované. Proto způsobilost neoznačujeme jako splněnou ani nesplněnou.",
        projectLabel: "Přidat k projektu",
        applicationCandidate: true,
      };
    case "PLANNED":
    case "ANNOUNCED":
      return {
        heading: "Ověřte u poskytovatele, kdy začne příjem žádostí.",
        explanation: "Výzva je plánovaná nebo vyhlášená, nikoli označená jako otevřená. Termín a úplné podmínky ověřte v oficiálním zdroji; způsobilost tím není potvrzena.",
        projectLabel: null,
        applicationCandidate: false,
      };
    case "PAUSED":
      return {
        heading: "Příjem je pozastaven. Ověřte, zda a kdy se obnoví.",
        explanation: "Podle zachycené verze nelze předpokládat, že lze právě podat žádost. Aktuální stav a podmínky ověřte u poskytovatele.",
        projectLabel: null,
        applicationCandidate: false,
      };
    case "CLOSED":
      return {
        heading: "Příjem skončil. Ověřte případné další kolo u poskytovatele.",
        explanation: "Zachycená výzva není otevřená pro nové žádosti. Další kolo ani možnost podání nepředpokládáme bez oficiálního potvrzení.",
        projectLabel: null,
        applicationCandidate: false,
      };
    case "CANCELLED":
      return {
        heading: "Výzva byla zrušena. Ověřte rozhodnutí u poskytovatele.",
        explanation: "Zrušení je stav zachycené verze, ne závěr ze zmizení z výpisu. Nepokračujte v přípravě žádosti bez nové oficiální výzvy.",
        projectLabel: null,
        applicationCandidate: false,
      };
    default:
      return {
        heading: "Stav výzvy není potvrzen. Ověřte jej u poskytovatele.",
        explanation: "Neznámý nebo archivní stav není potvrzení možnosti podat žádost ani posouzení způsobilosti.",
        projectLabel: null,
        applicationCandidate: false,
      };
  }
}
