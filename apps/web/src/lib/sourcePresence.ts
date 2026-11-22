import type { GrantSourceRef } from "./grantDetailApi";
import { safeOfficialUrl } from "./safeOfficialUrl";

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

export function mixedSourcePresence(sources: GrantSourceRef[]): boolean {
  return sources.some((source) => source.presenceState === "SEEN")
    && sources.some((source) => source.presenceState === "MISSING_CANDIDATE"
      || source.presenceState === "CONFIRMED_MISSING");
}

export function verificationSourceUrl(officialDetailUrl: string | null, sources: GrantSourceRef[]): string | null {
  if (mixedSourcePresence(sources)) {
    return sources.filter((source) => source.presenceState === "SEEN")
      .map((source) => safeOfficialUrl(source.canonicalUrl)).find(Boolean) ?? null;
  }
  return safeOfficialUrl(officialDetailUrl)
    ?? sources.map((source) => safeOfficialUrl(source.canonicalUrl)).find(Boolean)
    ?? null;
}
