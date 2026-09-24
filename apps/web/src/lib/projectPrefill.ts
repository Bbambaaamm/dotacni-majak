export interface ProjectPrefill {
  intent: string;
  autoWatch: boolean;
}

export function projectPrefillFromSearch(search: string): ProjectPrefill {
  const params = new URLSearchParams(search);
  const rawIntent = params.get("intent") ?? "";
  const intent = rawIntent.trim().replace(/\s+/g, " ").slice(0, 4000);
  return {
    intent,
    autoWatch: params.get("watch") === "1" && intent.length > 0,
  };
}
