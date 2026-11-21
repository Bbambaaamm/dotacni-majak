import type { D1DatabaseLike } from "./env";
import { expandIntentTerms } from "./ontology";

const TOKEN_RE = /[\p{L}\p{N}]+/gu;
const ACTIVE_STATUSES = ["OPEN", "PLANNED", "ANNOUNCED"] as const;
const INSTRUMENT_TYPES = ["GRANT", "LOAN", "GUARANTEE", "EQUITY", "MIXED", "OTHER"] as const;
type InstrumentType = typeof INSTRUMENT_TYPES[number];

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
  facets: SearchFacets | null;
}

export interface SearchFacets {
  status: Record<"OPEN" | "PLANNED" | "ANNOUNCED", number>;
  deadline: Record<"KNOWN" | "UNKNOWN", number>;
  providers: { name: string; count: number }[];
  providersTruncated: boolean;
}

const PROVIDER_FACET_LIMIT = 20;
export const FACET_MATCH_LIMIT = 500;

type Phase = "DIRECT" | "ONTOLOGY";
type SearchSort = "RELEVANCE" | "DEADLINE" | "DEADLINE_LATEST";
interface SearchCursor { v: 1; intent: string; limit: number; status: SearchStatus | null; deadline: SearchDeadline | null; provider: string | null; closesBy: string | null; closesFrom?: string | null; instrument?: InstrumentType | null; projectBudgetCzk?: number | null; phase: Phase; rank: number; id: string }
interface DateCursor { v: 2; intent: string; limit: number; status: SearchStatus | null; deadline: SearchDeadline | null; provider: string | null; closesBy: string | null; closesFrom?: string | null; instrument?: InstrumentType | null; projectBudgetCzk?: number | null; sort: Exclude<SearchSort, "RELEVANCE">; closeAt: number | null; phase: Phase; rank: number; id: string }
type SearchStatus = typeof ACTIVE_STATUSES[number];
type SearchDeadline = "KNOWN" | "UNKNOWN";

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
    public readonly code: "INTENT_REQUIRED" | "INTENT_TOO_LONG" | "INVALID_LIMIT" | "INVALID_CURSOR" | "INVALID_STATUS" | "INVALID_DEADLINE" | "INVALID_PROVIDER" | "INVALID_CLOSES_BY" | "INVALID_CLOSES_FROM" | "INVALID_DEADLINE_RANGE" | "INVALID_SORT" | "INVALID_INSTRUMENT" | "INVALID_PROJECT_BUDGET",
    public readonly status: number,
  ) {
    super(code);
  }
}

function encodeCursor(cursor: SearchCursor | DateCursor): string {
  const bytes = new TextEncoder().encode(JSON.stringify(cursor));
  return btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function decodeCursor(raw: string | null, intent: string, limit: number, status: SearchStatus | null, deadline: SearchDeadline | null, provider: string | null, closesBy: string | null, closesFrom: string | null, sort: SearchSort, instrument: InstrumentType | null, projectBudgetCzk: number | null): SearchCursor | DateCursor | null {
  if (raw === null) return null;
  try {
    if (!raw || raw.length > 8192 || !/^[A-Za-z0-9_-]+$/.test(raw)) throw new Error();
    const bytes = Uint8Array.from(atob(raw.replaceAll("-", "+").replaceAll("_", "/")), (c) => c.charCodeAt(0));
    const value: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (!value || typeof value !== "object") throw new Error();
    const c = value as SearchCursor | DateCursor;
    if (c.intent !== intent || c.limit !== limit || c.status !== status || c.deadline !== deadline || c.provider !== provider || (c.closesBy ?? null) !== closesBy || (c.closesFrom ?? null) !== closesFrom || (c.instrument ?? null) !== instrument || (c.projectBudgetCzk ?? null) !== projectBudgetCzk ||
      (c.phase !== "DIRECT" && c.phase !== "ONTOLOGY") ||
      typeof c.rank !== "number" || !Number.isFinite(c.rank) ||
      typeof c.id !== "string" || !c.id || c.id.length > 512 || encodeCursor(c) !== raw) throw new Error();
    if (sort === "RELEVANCE") {
      if (c.v !== 1) throw new Error();
    } else if (c.v !== 2 || c.sort !== sort ||
      (c.closeAt !== null && (typeof c.closeAt !== "number" || !Number.isFinite(c.closeAt)))) {
      throw new Error();
    }
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

function parseStatus(value: string | null): SearchStatus | null {
  if (value === null) return null;
  if (ACTIVE_STATUSES.some((status) => status === value)) return value as SearchStatus;
  throw new SearchInputError("INVALID_STATUS", 400);
}

function parseDeadline(value: string | null): SearchDeadline | null {
  if (value === null) return null;
  if (value === "KNOWN" || value === "UNKNOWN") return value;
  throw new SearchInputError("INVALID_DEADLINE", 400);
}

function parseProvider(value: string | null): string | null {
  if (value === null) return null;
  if (!value || value !== value.trim() || value.length > 200 || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new SearchInputError("INVALID_PROVIDER", 400);
  }
  return value;
}

function parseInstrument(value: string | null): InstrumentType | null {
  if (value === null) return null;
  if (INSTRUMENT_TYPES.some((type) => type === value)) return value as InstrumentType;
  throw new SearchInputError("INVALID_INSTRUMENT", 400);
}

function parseProjectBudget(value: string | null): number | null {
  if (value === null) return null;
  if (!/^(0|[1-9][0-9]*)$/.test(value) || value.length > 13) {
    throw new SearchInputError("INVALID_PROJECT_BUDGET", 400);
  }
  const amount = Number(value);
  if (!Number.isSafeInteger(amount) || amount > Math.floor(Number.MAX_SAFE_INTEGER / 100)) {
    throw new SearchInputError("INVALID_PROJECT_BUDGET", 400);
  }
  return amount;
}

// Budget is a catalog project-cost interval, never personal eligibility or own cash.
// Only a verified, scenario-specific document claim with BOTH bounds participates.
function budgetFilter(projectBudgetCzk: number | null): string {
  if (projectBudgetCzk === null) return "";
  return `AND v.funding_instrument_type = 'GRANT' AND EXISTS (
    SELECT 1 FROM funding_scenarios fs
    JOIN field_evidence fe ON fe.id = fs.evidence_id
      AND fe.entity_type = 'GRANT_CALL_VERSION' AND fe.entity_id = v.id
      AND fe.field_path = '/funding_scenarios/' || fs.id
      AND fe.verification_status = 'VERIFIED'
    JOIN document_versions dv ON dv.id = fe.document_version_id
    JOIN source_documents sd ON sd.id = dv.source_document_id AND sd.grant_call_id = g.id
    WHERE fs.grant_call_version_id = v.id AND fs.instrument_type = 'GRANT'
      AND fs.currency_code = 'CZK'
      AND fs.project_cost_min_minor IS NOT NULL AND fs.project_cost_max_minor IS NOT NULL
      AND fs.project_cost_min_minor <= ? AND fs.project_cost_max_minor >= ?
  )`;
}
function budgetBindings(projectBudgetCzk: number | null): number[] {
  return projectBudgetCzk === null ? [] : [projectBudgetCzk * 100, projectBudgetCzk * 100];
}

function parseDate(value: string | null, code: "INVALID_CLOSES_BY" | "INVALID_CLOSES_FROM"): string | null {
  if (value === null) return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) ||
      !Number.isFinite(Date.parse(`${value}T00:00:00Z`)) ||
      new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) !== value) {
    throw new SearchInputError(code, 400);
  }
  return value;
}

// Only well-formed source calendar dates can participate in a bounded UTC interval.
const BOUNDED_DATE = `(d.submission_close_at GLOB '????-??-??' OR d.submission_close_at GLOB '????-??-??T??:??:??*')
  AND strftime('%Y-%m-%d', substr(d.submission_close_at, 1, 10) || 'T00:00:00Z', '+0 days') = substr(d.submission_close_at, 1, 10)`;
// Older SQLite builds normalize 24:00:00Z to the next day (or reject it),
// while newer builds retain the written calendar day. Keep bounded queries
// consistent with the source-day policy on all supported runtimes.
const BOUNDED_CALENDAR_DAY = `CASE WHEN d.submission_close_at GLOB '????-??-??T24:00:00[Zz]'
  THEN substr(d.submission_close_at, 1, 10) ELSE date(d.submission_close_at) END`;
function dateFilters(closesFrom: string | null, closesBy: string | null): string {
  if (!closesFrom && !closesBy) return "";
  return `AND ${BOUNDED_DATE}
    ${closesFrom ? `AND ${BOUNDED_CALENDAR_DAY} >= ?` : ""}
    ${closesBy ? `AND ${BOUNDED_CALENDAR_DAY} <= ?` : ""}`;
}

function parseSort(value: string | null): SearchSort {
  if (value === null || value === "RELEVANCE") return "RELEVANCE";
  if (value === "DEADLINE" || value === "DEADLINE_LATEST") return value;
  throw new SearchInputError("INVALID_SORT", 400);
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
  status: SearchStatus | null,
  deadline: SearchDeadline | null,
  provider: string | null,
  closesFrom: string | null,
  closesBy: string | null,
  instrument: InstrumentType | null,
  projectBudgetCzk: number | null,
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
      ${status ? "AND d.status = ?" : ""}
      ${provider ? "AND p.name = ?" : ""}
      ${instrument ? "AND v.funding_instrument_type = ?" : ""}
      ${budgetFilter(projectBudgetCzk)}
      ${deadline ? `AND d.submission_close_at IS ${deadline === "KNOWN" ? "NOT " : ""}NULL` : ""}
      ${dateFilters(closesFrom, closesBy)}
      ${excludeDirectQuery ? "AND d.grant_call_version_id NOT IN (SELECT grant_call_version_id FROM grant_search_fts WHERE grant_search_fts MATCH ?)" : ""}
    ) SELECT * FROM ranked
    ${after ? "WHERE rank > ? OR (rank = ? AND grant_call_version_id > ?)" : ""}
    ORDER BY rank ASC, grant_call_version_id ASC
    LIMIT ?
  `;

  const result = await db
    .prepare(sql)
    .bind(query, ...ACTIVE_STATUSES, ...(status ? [status] : []), ...(provider ? [provider] : []), ...(instrument ? [instrument] : []), ...budgetBindings(projectBudgetCzk), ...(closesFrom ? [closesFrom] : []), ...(closesBy ? [closesBy] : []), ...(excludeDirectQuery ? [excludeDirectQuery] : []),
      ...(after ? [after.rank, after.rank, after.id] : []), limit)
    .all<SearchRow>();

  return result.results ?? [];
}

async function queryDateSorted(
  db: D1DatabaseLike, directQuery: string, expandedQuery: string, limit: number,
  after: DateCursor | null, status: SearchStatus | null, deadline: SearchDeadline | null,
  provider: string | null, closesFrom: string | null, closesBy: string | null, sort: DateCursor["sort"],
  instrument: InstrumentType | null, projectBudgetCzk: number | null,
): Promise<(SearchRow & { match_phase: number; close_sort: number | null })[]> {
  if (!directQuery && !expandedQuery) return [];
  const filters = `AND d.status IN (?, ?, ?)
    ${status ? "AND d.status = ?" : ""}
    ${provider ? "AND p.name = ?" : ""}
    ${instrument ? "AND v.funding_instrument_type = ?" : ""}
    ${budgetFilter(projectBudgetCzk)}
    ${deadline ? `AND d.submission_close_at IS ${deadline === "KNOWN" ? "NOT " : ""}NULL` : ""}
    ${dateFilters(closesFrom, closesBy)}`;
  const select = (phase: number, exclude: boolean) => `SELECT
      d.grant_call_version_id, g.id AS grant_call_id, d.title, d.summary, d.status,
      d.submission_close_at, julianday(d.submission_close_at) AS close_sort,
      p.name AS provider_name, v.official_detail_url,
      bm25(grant_search_fts, 0.0, 4.0, 1.5, 3.0, 1.5, 2.5) AS rank,
      ${phase} AS match_phase
    FROM grant_search_fts
    JOIN grant_search_documents d ON d.grant_call_version_id = grant_search_fts.grant_call_version_id
    JOIN grant_call_versions v ON v.id = d.grant_call_version_id
    JOIN grant_calls g ON g.id = v.grant_call_id
    JOIN programmes pr ON pr.id = g.programme_id
    JOIN providers p ON p.id = pr.provider_id
    WHERE grant_search_fts MATCH ? ${filters}
    ${exclude ? "AND d.grant_call_version_id NOT IN (SELECT grant_call_version_id FROM grant_search_fts WHERE grant_search_fts MATCH ?)" : ""}`;
  const binding = (query: string, exclude: boolean): unknown[] => [
    query, ...ACTIVE_STATUSES, ...(status ? [status] : []), ...(provider ? [provider] : []), ...(instrument ? [instrument] : []), ...budgetBindings(projectBudgetCzk),
    ...(closesFrom ? [closesFrom] : []), ...(closesBy ? [closesBy] : []), ...(exclude ? [directQuery] : []),
  ];
  const clauses = [directQuery && select(0, false),
    expandedQuery && select(1, Boolean(directQuery))].filter(Boolean);
  const direction = sort === "DEADLINE" ? "ASC" : "DESC";
  const comparator = sort === "DEADLINE" ? ">" : "<";
  const ties = `(match_phase > ? OR (match_phase = ? AND
    (rank > ? OR (rank = ? AND grant_call_version_id > ?))))`;
  const sql = `WITH matches AS (${clauses.join(" UNION ALL ")})
    SELECT * FROM matches
    ${after ? `WHERE (close_sort IS NULL) > ? OR
      ((close_sort IS NULL) = ? AND
        (close_sort ${comparator} ? OR
          (COALESCE(close_sort, -1) = ? AND ${ties})))` : ""}
    ORDER BY (close_sort IS NULL) ASC, close_sort ${direction},
      match_phase ASC, rank ASC, grant_call_version_id ASC LIMIT ?`;
  const values = [
    ...(directQuery ? binding(directQuery, false) : []),
    ...(expandedQuery ? binding(expandedQuery, Boolean(directQuery)) : []),
    ...(after ? [Number(after.closeAt === null), Number(after.closeAt === null), after.closeAt,
      after.closeAt ?? -1, after.phase === "DIRECT" ? 0 : 1, after.phase === "DIRECT" ? 0 : 1,
      after.rank, after.rank, after.id] : []), limit,
  ];
  const result = await db.prepare(sql).bind(...values).all<SearchRow & { match_phase: number; close_sort: number | null }>();
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

// Bound each FTS phase before any metadata join. A phase over budget, or a union
// over budget after removing overlap, makes all counts unavailable.
async function queryFacets(db: D1DatabaseLike, direct: string, expanded: string,
  status: SearchStatus | null, deadline: SearchDeadline | null, provider: string | null,
  closesFrom: string | null, closesBy: string | null, instrument: InstrumentType | null,
  projectBudgetCzk: number | null): Promise<SearchFacets | null> {
  const facets: SearchFacets = { status: { OPEN: 0, PLANNED: 0, ANNOUNCED: 0 },
    deadline: { KNOWN: 0, UNKNOWN: 0 }, providers: [], providersTruncated: false };
  if (!direct && !expanded) return facets;
  const ids = new Set<string>();
  for (const query of [direct, expanded]) {
    if (!query) continue;
    const matches = await db.prepare(`SELECT grant_call_version_id FROM grant_search_fts
      WHERE grant_search_fts MATCH ? LIMIT ?`).bind(query, FACET_MATCH_LIMIT + 1)
      .all<{ grant_call_version_id: string }>();
    const phase = matches.results ?? [];
    if (phase.length > FACET_MATCH_LIMIT) return null;
    for (const match of phase) ids.add(match.grant_call_version_id);
    if (ids.size > FACET_MATCH_LIMIT) return null;
  }
  if (!ids.size) return facets;
  const shared = `WITH matched AS MATERIALIZED (
    SELECT value AS grant_call_version_id FROM json_each(?)
  ), eligible AS MATERIALIZED (
    SELECT d.status, d.submission_close_at, p.name AS provider_name
    FROM matched m JOIN grant_search_documents d ON d.grant_call_version_id = m.grant_call_version_id
    JOIN grant_call_versions v ON v.id = d.grant_call_version_id
    JOIN grant_calls g ON g.id = v.grant_call_id
    JOIN programmes pr ON pr.id = g.programme_id
    JOIN providers p ON p.id = pr.provider_id
    WHERE d.status IN (?, ?, ?) ${instrument ? "AND v.funding_instrument_type = ?" : ""} ${budgetFilter(projectBudgetCzk)} ${dateFilters(closesFrom, closesBy)}
  )`;
  const bindings = [JSON.stringify([...ids]), ...ACTIVE_STATUSES, ...(instrument ? [instrument] : []),
    ...budgetBindings(projectBudgetCzk), ...(closesFrom ? [closesFrom] : []), ...(closesBy ? [closesBy] : []) ];
  const aggregate = `${shared} SELECT 'status' AS kind, status AS value, COUNT(*) AS count FROM eligible
      WHERE 1=1 ${provider ? "AND provider_name = ?" : ""}
      ${deadline ? `AND submission_close_at IS ${deadline === "KNOWN" ? "NOT " : ""}NULL` : ""}
      GROUP BY status
    UNION ALL SELECT 'deadline', CASE WHEN submission_close_at IS NULL THEN 'UNKNOWN' ELSE 'KNOWN' END, COUNT(*)
      FROM eligible WHERE 1=1 ${status ? "AND status = ?" : ""} ${provider ? "AND provider_name = ?" : ""}
      GROUP BY CASE WHEN submission_close_at IS NULL THEN 'UNKNOWN' ELSE 'KNOWN' END`;
  const rows = await db.prepare(aggregate).bind(...bindings, ...(provider ? [provider] : []),
    ...(status ? [status] : []), ...(provider ? [provider] : [])).all<{ kind: string; value: string; count: number }>();
  for (const row of rows.results ?? []) {
    if (row.kind === "status" && row.value in facets.status) facets.status[row.value as SearchStatus] = row.count;
    if (row.kind === "deadline" && row.value in facets.deadline) facets.deadline[row.value as SearchDeadline] = row.count;
  }
  const providerSql = `${shared} SELECT provider_name AS name, COUNT(*) AS count FROM eligible
    WHERE 1=1 ${status ? "AND status = ?" : ""}
    ${deadline ? `AND submission_close_at IS ${deadline === "KNOWN" ? "NOT " : ""}NULL` : ""}
    GROUP BY provider_name ORDER BY count DESC, provider_name ASC LIMIT ?`;
  const providerRows = await db.prepare(providerSql).bind(...bindings, ...(status ? [status] : []),
    PROVIDER_FACET_LIMIT + 1).all<{ name: string; count: number }>();
  const allProviders = providerRows.results ?? [];
  facets.providersTruncated = allProviders.length > PROVIDER_FACET_LIMIT;
  facets.providers = allProviders.slice(0, PROVIDER_FACET_LIMIT) as { name: string; count: number }[];
  return facets;
}

export async function searchGrants(
  db: D1DatabaseLike,
  rawIntent: string | null,
  limit = 20,
  rawCursor: string | null = null,
  rawStatus: string | null = null,
  rawDeadline: string | null = null,
  rawProvider: string | null = null,
  rawClosesBy: string | null = null,
  rawSort: string | null = null,
  rawClosesFrom: string | null = null,
  rawInstrument: string | null = null,
  rawProjectBudgetCzk: string | null = null,
): Promise<GrantSearchResponse> {
  const intent = normalizeSearchIntent(rawIntent);
  if (!Number.isInteger(limit) || limit < 1 || limit > 50) throw new SearchInputError("INVALID_LIMIT", 400);
  const status = parseStatus(rawStatus);
  const deadline = parseDeadline(rawDeadline);
  const provider = parseProvider(rawProvider);
  const closesBy = parseDate(rawClosesBy, "INVALID_CLOSES_BY");
  const closesFrom = parseDate(rawClosesFrom, "INVALID_CLOSES_FROM");
  if (closesFrom && closesBy && closesFrom > closesBy) throw new SearchInputError("INVALID_DEADLINE_RANGE", 400);
  const sort = parseSort(rawSort);
  const instrument = parseInstrument(rawInstrument);
  const projectBudgetCzk = parseProjectBudget(rawProjectBudgetCzk);
  const cursor = decodeCursor(rawCursor, intent, limit, status, deadline, provider, closesBy, closesFrom, sort, instrument, projectBudgetCzk);

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
      facets: cursor ? null : { status: { OPEN: 0, PLANNED: 0, ANNOUNCED: 0 },
        deadline: { KNOWN: 0, UNKNOWN: 0 }, providers: [], providersTruncated: false },
    };
  }

  const expandedTerms = expandIntentTerms(intent);
  const directQuery = buildDirectFtsQuery(intent);
  const expandedQuery = buildExpandedFtsQuery(expandedTerms);
  const facets = cursor ? null : await queryFacets(db, directQuery, expandedQuery,
    status, deadline, provider, closesFrom, closesBy, instrument, projectBudgetCzk);
  if (sort !== "RELEVANCE") {
    const rows = await queryDateSorted(db, directQuery, expandedQuery, limit + 1,
      cursor as DateCursor | null, status, deadline, provider, closesFrom, closesBy, sort, instrument, projectBudgetCzk);
    const selected = rows.slice(0, limit);
    const last = selected.at(-1);
    return { intent, results: selected.map((row) => toResult(row,
      row.match_phase === 0 ? "DIRECT" : "ONTOLOGY")),
      expandedTerms, indexState, facets,
      nextCursor: rows.length > limit && last ? encodeCursor({ v: 2, intent, limit, status, deadline,
        provider, closesBy, closesFrom, instrument, projectBudgetCzk, sort, closeAt: last.close_sort,
        phase: last.match_phase === 0 ? "DIRECT" : "ONTOLOGY", rank: last.rank,
        id: last.grant_call_version_id }) : null };
  }

  const relevanceCursor = cursor as SearchCursor | null;
  const directRows = relevanceCursor?.phase === "ONTOLOGY" ? [] :
    await queryFts(db, directQuery, limit + 1, relevanceCursor, status, deadline, provider, closesFrom, closesBy, instrument, projectBudgetCzk);
  const selectedDirect = directRows.slice(0, limit);
  const results = selectedDirect.map((row) => toResult(row, "DIRECT"));
  let lastRow = selectedDirect.at(-1);
  let lastPhase: Phase = "DIRECT";
  let hasMore = directRows.length > limit;

  if (!hasMore && expandedTerms.length) {
    const remaining = limit - results.length;
    const expandedRows = await queryFts(db, expandedQuery, remaining + 1,
      relevanceCursor?.phase === "ONTOLOGY" ? relevanceCursor : null, status, deadline, provider, closesFrom, closesBy, instrument, projectBudgetCzk, directQuery || undefined);
    for (const row of expandedRows.slice(0, remaining)) {
      results.push(toResult(row, "ONTOLOGY"));
      lastRow = row;
      lastPhase = "ONTOLOGY";
    }
    hasMore = expandedRows.length > remaining;
    // A full direct page followed by an ontology match resumes from its last direct row.
    if (remaining === 0 && hasMore) lastPhase = "DIRECT";
  }

  return { intent, results, expandedTerms, indexState, facets,
    nextCursor: hasMore && lastRow ? encodeCursor({ v: 1, intent, limit, status, deadline, provider, closesBy, closesFrom, instrument, projectBudgetCzk, phase: lastPhase,
      rank: lastRow.rank, id: lastRow.grant_call_version_id }) : null };
}
