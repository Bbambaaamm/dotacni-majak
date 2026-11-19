import type { GrantSourceRef } from "./grantDetailApi";

export function sourcePresenceLabel(state: string): string {
  switch (state) {
    case "SEEN": return "Viděn u zdroje";
    case "MISSING_CANDIDATE": return "Možná chybí u zdroje (předběžné)";
    case "CONFIRMED_MISSING": return "Potvrzeně chybí u zdroje (neznamená zrušení výzvy)";
    default: return "Výskyt u zdroje není známý";
  }
}

export function allSourcesMissing(sources: GrantSourceRef[]): boolean {
  return sources.length > 0 && sources.every(
    (source) => source.presenceState === "MISSING_CANDIDATE"
      || source.presenceState === "CONFIRMED_MISSING",
  );
}
