export interface ProjectPrefill {
  intent: string;
  autoWatch: boolean;
  grantCallId: string | null;
}

export function projectPrefillFromSearch(search: string): ProjectPrefill {
  const params = new URLSearchParams(search);
  const rawIntent = params.get("intent") ?? "";
  const intent = rawIntent.trim().replace(/\s+/g, " ").slice(0, 4000);
  return {
    intent,
    autoWatch: params.get("watch") === "1" && intent.length > 0,
    grantCallId: (params.get("grantCallId") ?? "").length > 0 && (params.get("grantCallId") ?? "").length <= 256
      ? params.get("grantCallId") : null,
  };
}
