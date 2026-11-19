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
): Promise<GrantSearchResponse> {
  const params = new URLSearchParams({ intent });
  if (cursor) params.set("cursor", cursor);
  if (status) params.set("status", status);
  if (deadline) params.set("deadline", deadline);
  if (provider) params.set("provider", provider);
  if (closesBy) params.set("closesBy", closesBy);
  if (closesFrom) params.set("closesFrom", closesFrom);
  if (instrument) params.set("instrument", instrument);
  if (sort && sort !== "RELEVANCE") params.set("sort", sort);
  const response = await fetch(`/api/search?${params.toString()}`, {
    method: "GET",
    headers: { accept: "application/json" },
    signal,
  });

  const body = await response.json().catch(() => ({})) as
    | GrantSearchResponse
    | { error?: string };

  if (!response.ok) {
    throw new SearchApiError(
      "error" in body && body.error ? body.error : "SEARCH_UNAVAILABLE",
      response.status,
    );
  }

  return body as GrantSearchResponse;
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
