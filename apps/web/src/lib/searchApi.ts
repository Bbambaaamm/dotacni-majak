export type SearchMatchKind = "DIRECT" | "ONTOLOGY";

export interface GrantSearchResult {
  grantCallVersionId: string;
  grantCallId: string;
  title: string;
  summary: string;
  status: string;
  submissionCloseAt: string | null;
  providerName: string;
  officialDetailUrl: string | null;
  matchKind: SearchMatchKind;
}

export interface GrantSearchResponse {
  intent: string;
  results: GrantSearchResult[];
  expandedTerms: string[];
  indexState: "READY" | "EMPTY";
  nextCursor: string | null;
  facets: {
    status: Record<"OPEN" | "PLANNED" | "ANNOUNCED", number>;
    deadline: Record<"KNOWN" | "UNKNOWN", number>;
    providers: { name: string; count: number }[];
    providersTruncated: boolean;
  } | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSearchResponse(value: unknown, intent: string): value is GrantSearchResponse {
  if (!isRecord(value) || value.intent !== intent || !Array.isArray(value.results)
    || !Array.isArray(value.expandedTerms) || !value.expandedTerms.every((term) => typeof term === "string")
    || (value.indexState !== "READY" && value.indexState !== "EMPTY")
    || !(value.nextCursor === null || (typeof value.nextCursor === "string" && value.nextCursor.length > 0))) return false;
  // An empty index cannot contain search results or a continuation page.
  if (value.indexState === "EMPTY" && (value.results.length > 0 || value.nextCursor !== null)) return false;
  if (value.facets !== null) {
    const facets = value.facets;
    if (!isRecord(facets) || !isRecord(facets.status) || !isRecord(facets.deadline)
      || !Array.isArray(facets.providers) || typeof facets.providersTruncated !== "boolean") return false;
    const status = facets.status;
    const deadline = facets.deadline;
    if (!["OPEN", "PLANNED", "ANNOUNCED"].every((key) => Number.isSafeInteger(status[key]) && (status[key] as number) >= 0)
      || !["KNOWN", "UNKNOWN"].every((key) => Number.isSafeInteger(deadline[key]) && (deadline[key] as number) >= 0)
      || !facets.providers.every((provider: unknown) => isRecord(provider) && typeof provider.name === "string"
        && Number.isSafeInteger(provider.count) && (provider.count as number) >= 0)) return false;
  }
  return value.results.every((item: unknown) => isRecord(item)
    && typeof item.grantCallVersionId === "string" && item.grantCallVersionId.length > 0
    && typeof item.grantCallId === "string" && item.grantCallId.length > 0
    && typeof item.title === "string" && item.title.trim().length > 0
    && typeof item.summary === "string"
    && (item.status === "OPEN" || item.status === "PLANNED" || item.status === "ANNOUNCED")
    && typeof item.providerName === "string" && item.providerName.trim().length > 0
    && (item.submissionCloseAt === null || typeof item.submissionCloseAt === "string")
    && (item.officialDetailUrl === null || typeof item.officialDetailUrl === "string")
    && (item.matchKind === "DIRECT" || item.matchKind === "ONTOLOGY"));
}

export class SearchApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
  ) {
    super(code);
  }
}

export async function searchGrants(
  intent: string,
  signal?: AbortSignal,
  cursor?: string,
  status?: "OPEN" | "PLANNED" | "ANNOUNCED",
  deadline?: "KNOWN" | "UNKNOWN",
  provider?: string,
  closesBy?: string,
  sort?: "RELEVANCE" | "DEADLINE" | "DEADLINE_LATEST",
  closesFrom?: string,
  instrument?: "GRANT" | "LOAN" | "GUARANTEE" | "EQUITY" | "MIXED" | "OTHER",
  projectBudgetCzk?: string,
): Promise<GrantSearchResponse> {
  const params = new URLSearchParams({ intent });
  if (cursor) params.set("cursor", cursor);
  if (status) params.set("status", status);
  if (deadline) params.set("deadline", deadline);
  if (provider) params.set("provider", provider);
  if (closesBy) params.set("closesBy", closesBy);
  if (closesFrom) params.set("closesFrom", closesFrom);
  if (instrument) params.set("instrument", instrument);
  if (projectBudgetCzk) params.set("projectBudgetCzk", projectBudgetCzk);
  if (sort && sort !== "RELEVANCE") params.set("sort", sort);
  const response = await fetch(`/api/search?${params.toString()}`, {
    method: "GET",
    headers: { accept: "application/json" },
    signal,
  });

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new SearchApiError(
      isRecord(body) && typeof body.error === "string" && body.error ? body.error : "SEARCH_UNAVAILABLE",
      response.status,
    );
  }
  if (!isSearchResponse(body, intent) || (cursor && body.nextCursor === cursor)) {
    throw new SearchApiError("INVALID_SEARCH_RESPONSE", response.status);
  }
  return body;
}

export function searchErrorMessage(error: unknown): string {
  if (error instanceof SearchApiError) {
    if (error.code === "SEARCH_UNAVAILABLE") {
      return "Vyhledávací index není dostupný. Pokud aplikaci spouštíte lokálně, spusťte také API a připravte lokální databázi.";
    }
    if (error.code === "INTENT_REQUIRED") {
      return "Zadejte, co chcete uskutečnit.";
    }
  }
  return "Vyhledávání se teď nepodařilo dokončit.";
}
