export const intentExamples = [
  "rekonstrukce sportoviště",
  "zateplení školy",
  "dětské hřiště",
  "digitalizace malé firmy",
] as const;

export function normalizeIntent(intent: string): string {
  return intent.trim().replace(/\s+/g, " ");
}

export function readIntentFromSearch(search: string): string {
  return normalizeIntent(new URLSearchParams(search).get("intent") ?? "");
}

export function buildIntentSearchUrl(intent: string): string {
  const normalized = normalizeIntent(intent);
  if (!normalized) {
    return "/hledat";
  }
  const params = new URLSearchParams({ intent: normalized });
  return `/hledat?${params.toString()}`;
}
