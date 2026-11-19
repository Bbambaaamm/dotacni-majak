import type { D1DatabaseLike } from "./env";
import { expandIntentTerms } from "./ontology";

const TOKEN_RE = /[\p{L}\p{N}]+/gu;
const ACTIVE_STATUSES = ["OPEN", "PLANNED", "ANNOUNCED"] as const;

export interface GrantSearchResult {
  grantCallVersionId: string;
  grantCallId: string;
  title: string;
  summary: string;
  status: string;
  submissionCloseAt: string | null;
  providerName: string;
  officialDetailUrl: string | null;
  matchKind: "DIRECT" | "ONTOLOGY";
}

export interface GrantSearchResponse {
  intent: string;
  results: GrantSearchResult[];
  expandedTerms: string[];
  indexState: "READY" | "EMPTY";
  nextCursor: string | null;
}

type Phase = "DIRECT" | "ONTOLOGY";
interface SearchCursor { v: 1; intent: string; limit: number; phase: Phase; rank: number; id: string }

interface SearchRow {
  grant_call_version_id: string;
  grant_call_id: string;
  title: string;
  summary: string;
  status: string;
  submission_close_at: string | null;
  provider_name: string;
  official_detail_url: string | null;
  rank: number;
}

export class SearchInputError extends Error {
  constructor(
    public readonly code: "INTENT_REQUIRED" | "INTENT_TOO_LONG" | "INVALID_LIMIT" | "INVALID_CURSOR",
    public readonly status: number,
  ) {
    super(code);
  }
}

function encodeCursor(cursor: SearchCursor): string {
  const bytes = new TextEncoder().encode(JSON.stringify(cursor));
  return btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function decodeCursor(raw: string | null, intent: string, limit: number): SearchCursor | null {
  if (raw === null) return null;
  try {
    if (!raw || raw.length > 8192 || !/^[A-Za-z0-9_-]+$/.test(raw)) throw new Error();
    const bytes = Uint8Array.from(atob(raw.replaceAll("-", "+").replaceAll("_", "/")), (c) => c.charCodeAt(0));
    const value: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (!value || typeof value !== "object") throw new Error();
    const c = value as SearchCursor;
    if (c.v !== 1 || c.intent !== intent || c.limit !== limit ||
      (c.phase !== "DIRECT" && c.phase !== "ONTOLOGY") ||
      typeof c.rank !== "number" || !Number.isFinite(c.rank) ||
      typeof c.id !== "string" || !c.id || c.id.length > 512 || encodeCursor(c) !== raw) throw new Error();
    return c;
  } catch {
    throw new SearchInputError("INVALID_CURSOR", 400);
  }
}

export function normalizeSearchIntent(value: string | null): string {
  const normalized = (value ?? "").trim().replace(/\s+/g, " ");
  if (!normalized) throw new SearchInputError("INTENT_REQUIRED", 400);
  if (normalized.length > 500) throw new SearchInputError("INTENT_TOO_LONG", 400);
  return normalized;
}

function ftsToken(token: string, prefix = true): string {
  const escaped = token.replaceAll('"', '""');
  return `"${escaped}"${prefix && token.length >= 3 ? "*" : ""}`;
}

export function buildDirectFtsQuery(intent: string): string {
  const tokens = Array.from(intent.matchAll(TOKEN_RE), (match) =>
    match[0].toLocaleLowerCase("cs-CZ"),
  );
  return tokens.map((token) => ftsToken(token)).join(" ");
}

export function buildExpandedFtsQuery(terms: readonly string[]): string {
  const clauses: string[] = [];
  for (const term of terms) {
    const tokens = Array.from(term.matchAll(TOKEN_RE), (match) =>
      match[0].toLocaleLowerCase("cs-CZ"),
    );
    if (!tokens.length) continue;
    clauses.push(tokens.map((token) => ftsToken(token)).join(" "));
  }
  return [...new Set(clauses)].slice(0, 16).join(" OR ");
}

async function queryFts(
  db: D1DatabaseLike,
  query: string,
  limit: number,
  after: SearchCursor | null,
  excludeDirectQuery?: string,
): Promise<SearchRow[]> {
  if (!query) return [];

  const sql = `WITH ranked AS (SELECT
      d.grant_call_version_id,
      g.id AS grant_call_id,
      d.title,
      d.summary,
      d.status,
      d.submission_close_at,
      p.name AS provider_name,
      v.official_detail_url,
      bm25(grant_search_fts, 0.0, 4.0, 1.5, 3.0, 1.5, 2.5) AS rank
    FROM grant_search_fts
    JOIN grant_search_documents d
      ON d.grant_call_version_id = grant_search_fts.grant_call_version_id
    JOIN grant_call_versions v
      ON v.id = d.grant_call_version_id
    JOIN grant_calls g
      ON g.id = v.grant_call_id
    JOIN programmes pr
      ON pr.id = g.programme_id
    JOIN providers p
      ON p.id = pr.provider_id
    WHERE grant_search_fts MATCH ?
      AND d.status IN (?, ?, ?)
      ${excludeDirectQuery ? "AND d.grant_call_version_id NOT IN (SELECT grant_call_version_id FROM grant_search_fts WHERE grant_search_fts MATCH ?)" : ""}
    ) SELECT * FROM ranked
    ${after ? "WHERE rank > ? OR (rank = ? AND grant_call_version_id > ?)" : ""}
    ORDER BY rank ASC, grant_call_version_id ASC
    LIMIT ?
  `;

  const result = await db
    .prepare(sql)
    .bind(query, ...ACTIVE_STATUSES, ...(excludeDirectQuery ? [excludeDirectQuery] : []),
      ...(after ? [after.rank, after.rank, after.id] : []), limit)
    .all<SearchRow>();

  return result.results ?? [];
}

function toResult(row: SearchRow, matchKind: "DIRECT" | "ONTOLOGY"): GrantSearchResult {
  return {
    grantCallVersionId: row.grant_call_version_id,
    grantCallId: row.grant_call_id,
    title: row.title,
    summary: row.summary,
    status: row.status,
    submissionCloseAt: row.submission_close_at,
    providerName: row.provider_name,
    officialDetailUrl: row.official_detail_url,
    matchKind,
  };
}

export async function searchGrants(
  db: D1DatabaseLike,
  rawIntent: string | null,
  limit = 20,
  rawCursor: string | null = null,
): Promise<GrantSearchResponse> {
  const intent = normalizeSearchIntent(rawIntent);
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) throw new SearchInputError("INVALID_LIMIT", 400);
  const cursor = decodeCursor(rawCursor, intent, limit);

  const countRow = await db
    .prepare("SELECT COUNT(*) AS count FROM grant_search_documents")
    .first<{ count: number }>();
  const indexState = (countRow?.count ?? 0) > 0 ? "READY" : "EMPTY";
  if (indexState === "EMPTY") {
    return {
      intent,
      results: [],
      expandedTerms: expandIntentTerms(intent),
      indexState,
      nextCursor: null,
    };
  }

  const directQuery = buildDirectFtsQuery(intent);
  const directRows = cursor?.phase === "ONTOLOGY" ? [] :
    await queryFts(db, directQuery, limit + 1, cursor);
  const selectedDirect = directRows.slice(0, limit);
  const results = selectedDirect.map((row) => toResult(row, "DIRECT"));
  let lastRow = selectedDirect.at(-1);
  let lastPhase: Phase = "DIRECT";
  let hasMore = directRows.length > limit;

  const expandedTerms = expandIntentTerms(intent);
  if (!hasMore && expandedTerms.length) {
    const expandedQuery = buildExpandedFtsQuery(expandedTerms);
    const remaining = limit - results.length;
    const expandedRows = await queryFts(db, expandedQuery, remaining + 1,
      cursor?.phase === "ONTOLOGY" ? cursor : null, directQuery || undefined);
    for (const row of expandedRows.slice(0, remaining)) {
      results.push(toResult(row, "ONTOLOGY"));
      lastRow = row;
      lastPhase = "ONTOLOGY";
    }
    hasMore = expandedRows.length > remaining;
    // A full direct page followed by an ontology match resumes from its last direct row.
    if (remaining === 0 && hasMore) lastPhase = "DIRECT";
  }

  return { intent, results, expandedTerms, indexState,
    nextCursor: hasMore && lastRow ? encodeCursor({ v: 1, intent, limit, phase: lastPhase,
      rank: lastRow.rank, id: lastRow.grant_call_version_id }) : null };
}
