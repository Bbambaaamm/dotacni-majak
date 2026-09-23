export const intentExamples = [
  "rekonstrukce sportoviště",
  "zateplení školy",
  "dětské hřiště",
  "digitalizace malé firmy",
] as const;

export function buildIntentSearchUrl(intent: string): string {
  const normalized = intent.trim().replace(/\s+/g, " ");
  if (!normalized) {
    return "/hledat";
  }
  const params = new URLSearchParams({ intent: normalized });
  return `/hledat?${params.toString()}`;
}
