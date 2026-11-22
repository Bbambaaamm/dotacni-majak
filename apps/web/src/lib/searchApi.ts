export type SearchMatchKind = "DIRECT" | "ONTOLOGY";

export interface GrantSearchResult {
  grantCallVersionId: string;
  grantCallId: string;
  title: string;
  summary: string;
  status: string;
  capturedAt: string;
  verificationStatus: "AUTO_EXTRACTED" | "PARTIALLY_VERIFIED" | "VERIFIED" | "NEEDS_REVIEW";
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

function isCaptureTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = /^\d{4}-\d{2}-\d{2}T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-](\d{2}):(\d{2}))$/.exec(value);
  if (!match || Number(match[1]) > 23 || Number(match[2]) > 59 || Number(match[3]) > 59
    || (match[4] !== undefined && (Number(match[4]) > 23 || Number(match[5]) > 59))
    || !Number.isFinite(Date.parse(value))) return false;
  const day = value.slice(0, 10);
  const calendarDay = new Date(`${day}T12:00:00Z`);
  return Number.isFinite(calendarDay.getTime()) && calendarDay.toISOString().slice(0, 10) === day;
}

function providerFacetsInOrder(providers: readonly { name: string; count: number }[]): boolean {
  // D1 uses SQLite's default BINARY collation (UTF-8 byte order), not localeCompare
  // or JavaScript's UTF-16 string order. This matters for equal-count names.
  const encoder = new TextEncoder();
  return providers.every((provider, index) => {
    if (!index) return true;
    const previous = providers[index - 1];
    if (previous.count !== provider.count) return previous.count > provider.count;
    const left = encoder.encode(previous.name);
    const right = encoder.encode(provider.name);
    for (let offset = 0; offset < Math.min(left.length, right.length); offset += 1) {
      if (left[offset] !== right[offset]) return left[offset] < right[offset];
    }
    return left.length < right.length;
  });
}

function isSearchResponse(value: unknown, intent: string): value is GrantSearchResponse {
  if (!isRecord(value) || value.intent !== intent || !Array.isArray(value.results)
    || !Array.isArray(value.expandedTerms) || !value.expandedTerms.every((term) => typeof term === "string" && term.trim().length > 0)
    || (value.indexState !== "READY" && value.indexState !== "EMPTY")
    || !(value.nextCursor === null || (typeof value.nextCursor === "string" && value.nextCursor.length > 0))) return false;
  // The initial empty-index API response includes explicit zero facets. Null
  // facets mean counts were unavailable, not proof that the index has no calls.
  if (value.indexState === "EMPTY" && (value.results.length > 0 || value.nextCursor !== null
    || value.facets === null)) return false;
  // A page cannot be empty while promising more results: the UI would hide
  // pagination on the first page or loop forever on a continuation.
  if (value.results.length === 0 && value.nextCursor !== null) return false;
  if (value.facets !== null) {
    const facets = value.facets;
    if (!isRecord(facets) || !isRecord(facets.status) || !isRecord(facets.deadline)
      || !Array.isArray(facets.providers) || typeof facets.providersTruncated !== "boolean") return false;
    const status = facets.status;
    const deadline = facets.deadline;
    if (!["OPEN", "PLANNED", "ANNOUNCED"].every((key) => Number.isSafeInteger(status[key]) && (status[key] as number) >= 0)
      || !["KNOWN", "UNKNOWN"].every((key) => Number.isSafeInteger(deadline[key]) && (deadline[key] as number) >= 0)
      || facets.providers.length > 20
      || !facets.providers.every((provider: unknown) => isRecord(provider) && typeof provider.name === "string"
        && provider.name.trim().length > 0 && provider.name === provider.name.trim()
        && Number.isSafeInteger(provider.count) && (provider.count as number) > 0)
      || new Set(facets.providers.map((provider: { name: string }) => provider.name)).size !== facets.providers.length
      || !providerFacetsInOrder(facets.providers as { name: string; count: number }[])) return false;
    // The API returns zero facets for an empty index. Positive counts or a
    // truncated list contradict the UI's "no indexed calls" conclusion.
    if (value.indexState === "EMPTY" && ([...Object.values(status), ...Object.values(deadline)].some((count) => count !== 0)
      || facets.providers.length > 0 || facets.providersTruncated)) return false;
  }
  const expandedTerms = value.expandedTerms as string[];
  return value.results.every((item: unknown) => isRecord(item)
    && (item.matchKind !== "ONTOLOGY" || expandedTerms.length > 0)
    && typeof item.grantCallVersionId === "string" && item.grantCallVersionId.trim().length > 0
    && typeof item.grantCallId === "string" && item.grantCallId.trim().length > 0
    && typeof item.title === "string" && item.title.trim().length > 0
    && typeof item.summary === "string"
    && (item.status === "OPEN" || item.status === "PLANNED" || item.status === "ANNOUNCED")
    && isCaptureTimestamp(item.capturedAt)
    && (item.verificationStatus === "AUTO_EXTRACTED" || item.verificationStatus === "PARTIALLY_VERIFIED"
      || item.verificationStatus === "VERIFIED" || item.verificationStatus === "NEEDS_REVIEW")
    && typeof item.providerName === "string" && item.providerName.trim().length > 0
    && (item.submissionCloseAt === null || typeof item.submissionCloseAt === "string")
    && (item.officialDetailUrl === null || typeof item.officialDetailUrl === "string")
    && (item.matchKind === "DIRECT" || item.matchKind === "ONTOLOGY"));
}

function resultDateInWindow(value: string | null, closesFrom?: string, closesBy?: string): boolean {
  if (!closesFrom && !closesBy) return true;
  if (value === null) return false;
  // SQLite accepts surrounding and pre-timezone whitespace in bounded dates;
  // compare a normalized copy, never rewrite the source text shown to users.
  const dateText = value.trim().replace(/\s+(?=[Zz]|[+-]\d{2}:\d{2}$)/, "");
  if (!/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})?)?$/.test(dateText)) return false;
  const sourceDate = dateText.slice(0, 10);
  if (!Number.isFinite(Date.parse(`${sourceDate}T00:00:00Z`))
    || new Date(`${sourceDate}T00:00:00Z`).toISOString().slice(0, 10) !== sourceDate) return false;
  // SQLite keeps hour 24 on the written day at zero offset, while a nonzero
  // offset can move its UTC day. Date.parse instead normalizes or rejects it.
  const hour24 = dateText.includes("T24:");
  const normalized = dateText.length > 10 && !/(?:[Zz]|[+-]\d{2}:\d{2})$/.test(dateText)
    ? `${dateText}Z` : dateText.replace(/z$/, "Z");
  const offset = normalized.match(/([+-]\d{2}:\d{2})$/)?.[1];
  const comparable = hour24 ? normalized.replace("T24:", "T00:") : normalized;
  const timestamp = Date.parse(dateText.length === 10 ? `${dateText}T00:00:00Z` : comparable);
  if (!Number.isFinite(timestamp)) return false;
  const date = hour24 && (!offset || offset === "+00:00" || offset === "-00:00")
    ? sourceDate
    : new Date(timestamp + (hour24 ? 86_400_000 : 0)).toISOString().slice(0, 10);
  return (!closesFrom || date >= closesFrom) && (!closesBy || date <= closesBy);
}

function resultsMatchFilters(
  response: GrantSearchResponse,
  status?: "OPEN" | "PLANNED" | "ANNOUNCED",
  deadline?: "KNOWN" | "UNKNOWN",
  provider?: string,
  closesFrom?: string,
  closesBy?: string,
): boolean {
  return response.results.every((result) =>
    (!status || result.status === status)
    && (!deadline || (result.submissionCloseAt === null ? "UNKNOWN" : "KNOWN") === deadline)
    && (!provider || result.providerName === provider)
    && resultDateInWindow(result.submissionCloseAt, closesFrom, closesBy));
}

function facetsCoverResults(response: GrantSearchResponse,
  status?: "OPEN" | "PLANNED" | "ANNOUNCED", deadline?: "KNOWN" | "UNKNOWN"): boolean {
  if (response.facets === null) return true; // Counts above the facet cap are unavailable, not zero.
  // Without either filter, both facets count the same matched calls. A mismatch
  // must not become two contradictory filter totals in the results UI.
  if (!status && !deadline &&
    response.facets.status.OPEN + response.facets.status.PLANNED + response.facets.status.ANNOUNCED !==
    response.facets.deadline.KNOWN + response.facets.deadline.UNKNOWN) return false;
  const statuses = new Map<string, number>();
  const deadlines = new Map<"KNOWN" | "UNKNOWN", number>();
  const providers = new Map<string, number>();
  for (const result of response.results) {
    statuses.set(result.status, (statuses.get(result.status) ?? 0) + 1);
    const deadline = result.submissionCloseAt === null ? "UNKNOWN" : "KNOWN";
    deadlines.set(deadline, (deadlines.get(deadline) ?? 0) + 1);
    providers.set(result.providerName, (providers.get(result.providerName) ?? 0) + 1);
  }
  const facets = response.facets;
  if ([...statuses].some(([status, count]) => facets.status[status as keyof typeof facets.status] < count)
    || [...deadlines].some(([deadline, count]) => facets.deadline[deadline] < count)) return false;
  return [...providers].every(([name, count]) => {
    const provider = facets.providers.find((item) => item.name === name);
    return provider ? provider.count >= count : facets.providersTruncated;
  });
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
  seenVersionIds?: ReadonlySet<string>,
  seenCallIds?: ReadonlySet<string>,
  seenCursors?: ReadonlySet<string>,
  expectedExpandedTerms?: readonly string[],
  previousMatchKind?: SearchMatchKind,
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
  // The web client omits limit, so the API contract caps each page at 20.
  // Never render an oversized success response as a trustworthy page.
  if (!isSearchResponse(body, intent) || body.results.length > 20 || !facetsCoverResults(body, status, deadline)
    || (cursor && body.facets !== null)
    || (expectedExpandedTerms && (body.expandedTerms.length !== expectedExpandedTerms.length
      || body.expandedTerms.some((term, index) => term !== expectedExpandedTerms[index])))
    || !resultsMatchFilters(body, status, deadline, provider, closesFrom, closesBy)
    || (cursor && (body.nextCursor === cursor || body.indexState === "EMPTY"))
    || (body.nextCursor !== null && seenCursors?.has(body.nextCursor))) {
    throw new SearchApiError("INVALID_SEARCH_RESPONSE", response.status);
  }
  // Relevance is phase-ordered across pages; deadline sorts interleave phases.
  // Do not promote a direct match after any ontology result was already shown.
  if ((!sort || sort === "RELEVANCE") && body.results.some((item, index) =>
    item.matchKind === "DIRECT" && (previousMatchKind === "ONTOLOGY"
      || body.results.slice(0, index).some((prior) => prior.matchKind === "ONTOLOGY")))) {
    throw new SearchApiError("INVALID_SEARCH_RESPONSE", response.status);
  }
  const pageIds = new Set(body.results.map((item) => item.grantCallVersionId));
  const callIds = new Set(body.results.map((item) => item.grantCallId));
  if (pageIds.size !== body.results.length || callIds.size !== body.results.length
    || body.results.some((item) => seenVersionIds?.has(item.grantCallVersionId)
      || seenCallIds?.has(item.grantCallId))) {
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
