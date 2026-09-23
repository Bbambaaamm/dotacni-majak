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
}

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
    public readonly code: "INTENT_REQUIRED" | "INTENT_TOO_LONG",
    public readonly status: number,
  ) {
    super(code);
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
): Promise<SearchRow[]> {
  if (!query) return [];

  const sql = `
    SELECT
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
    ORDER BY rank ASC, d.grant_call_version_id ASC
    LIMIT ?
  `;

  const result = await db
    .prepare(sql)
    .bind(query, ...ACTIVE_STATUSES, limit)
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
): Promise<GrantSearchResponse> {
  const intent = normalizeSearchIntent(rawIntent);
  const boundedLimit = Math.min(Math.max(limit, 1), 50);

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
    };
  }

  const directQuery = buildDirectFtsQuery(intent);
  const directRows = await queryFts(db, directQuery, boundedLimit);

  const results = directRows.map((row) => toResult(row, "DIRECT"));
  const seen = new Set(results.map((result) => result.grantCallVersionId));

  const expandedTerms = expandIntentTerms(intent);
  if (results.length < boundedLimit && expandedTerms.length) {
    const expandedQuery = buildExpandedFtsQuery(expandedTerms);
    const expandedRows = await queryFts(db, expandedQuery, boundedLimit);
    for (const row of expandedRows) {
      if (seen.has(row.grant_call_version_id)) continue;
      results.push(toResult(row, "ONTOLOGY"));
      seen.add(row.grant_call_version_id);
      if (results.length >= boundedLimit) break;
    }
  }

  return { intent, results, expandedTerms, indexState };
}
