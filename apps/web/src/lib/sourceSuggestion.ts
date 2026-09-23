export type SourceSuggestionStatus =
  | "PENDING_REVIEW"
  | "APPROVED"
  | "REJECTED";

export interface SourceSuggestion {
  id: string;
  name: string;
  url: string;
  providerName: string | null;
  note: string | null;
  status: SourceSuggestionStatus;
  createdAt: string;
  reviewedAt: string | null;
  reviewNote: string | null;
}

export interface SuggestionStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export function createSourceSuggestion(input: {
  id: string;
  name: string;
  url: string;
  providerName?: string | null;
  note?: string | null;
  createdAt: string;
}): SourceSuggestion {
  const name = input.name.trim();
  if (name.length < 2 || name.length > 160) {
    throw new Error("Název zdroje musí mít 2–160 znaků.");
  }

  const parsed = new URL(input.url.trim());
  if (parsed.protocol !== "https:") {
    throw new Error("Navrhovaný zdroj musí používat HTTPS.");
  }
  if (parsed.username || parsed.password) {
    throw new Error("URL nesmí obsahovat přihlašovací údaje.");
  }
  if (!parsed.hostname) {
    throw new Error("URL musí obsahovat hostname.");
  }

  const note = input.note?.trim() || null;
  if (note && note.length > 1000) {
    throw new Error("Poznámka může mít maximálně 1000 znaků.");
  }

  const providerName = input.providerName?.trim() || null;
  if (providerName && providerName.length > 160) {
    throw new Error("Název poskytovatele je příliš dlouhý.");
  }

  return {
    id: input.id,
    name,
    url: parsed.toString(),
    providerName,
    note,
    status: "PENDING_REVIEW",
    createdAt: input.createdAt,
    reviewedAt: null,
    reviewNote: null,
  };
}

export function reviewSourceSuggestion(
  suggestion: SourceSuggestion,
  input: {
    decision: "APPROVED" | "REJECTED";
    reviewedAt: string;
    reviewNote?: string | null;
  },
): SourceSuggestion {
  if (suggestion.status !== "PENDING_REVIEW") {
    throw new Error("Návrh už byl zkontrolován.");
  }

  return {
    ...suggestion,
    status: input.decision,
    reviewedAt: input.reviewedAt,
    reviewNote: input.reviewNote?.trim() || null,
  };
}

export class LocalSourceSuggestionStore {
  constructor(
    private readonly storage: SuggestionStorage,
    private readonly key = "dotacni-majak:source-suggestions:v1",
  ) {}

  all(): readonly SourceSuggestion[] {
    const raw = this.storage.getItem(this.key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isSuggestion);
  }

  save(suggestion: SourceSuggestion): void {
    const current = this.all().filter((item) => item.id !== suggestion.id);
    this.storage.setItem(this.key, JSON.stringify([...current, suggestion]));
  }
}

function isSuggestion(value: unknown): value is SourceSuggestion {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<SourceSuggestion>;
  return (
    typeof item.id === "string" &&
    typeof item.name === "string" &&
    typeof item.url === "string" &&
    (item.status === "PENDING_REVIEW" ||
      item.status === "APPROVED" ||
      item.status === "REJECTED") &&
    typeof item.createdAt === "string"
  );
}
