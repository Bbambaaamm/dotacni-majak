import type { D1DatabaseLike } from "./env";

export interface GrantProviderDetail {
  id: string;
  name: string;
  type: string;
  officialUrl: string | null;
}

export interface GrantProgrammeDetail {
  id: string;
  name: string;
  fundingOrigin: string;
  officialUrl: string | null;
}

export interface GrantSourceRef {
  sourceCode: string;
  sourceName: string;
  canonicalUrl: string;
  lastSeenAt: string;
  presenceState: string;
}

export interface GrantDeadlineDetail {
  id: string;
  type: string;
  startsAt: string | null;
  endsAt: string | null;
  timezone: string | null;
  description: string | null;
  evidenceId: string | null;
}

export interface GrantFundingScenarioDetail {
  id: string;
  name: string;
  currencyCode: string;
  supportRateMinBps: number | null;
  supportRateMaxBps: number | null;
  grantAmountMinMinor: number | null;
  grantAmountMaxMinor: number | null;
  projectCostMinMinor: number | null;
  projectCostMaxMinor: number | null;
  paymentMode: string | null;
  vatRule: string | null;
  advancePaymentAllowed: boolean | null;
  evidenceId: string | null;
}

export interface GrantRequirementDetail {
  id: string;
  type: string;
  title: string;
  description: string | null;
  necessity: string;
  phase: string | null;
  evidenceId: string | null;
}

export interface GrantEvidenceDetail {
  id: string;
  fieldPath: string;
  pageFrom: number | null;
  pageTo: number | null;
  evidenceText: string | null;
  verificationStatus: string;
  documentTitle: string | null;
  sourceUrl: string;
  retrievedAt: string;
}

export interface GrantChangeDetail {
  id: string;
  changeType: string;
  severity: string;
  fieldPath: string | null;
  oldValue: unknown;
  newValue: unknown;
  createdAt: string;
}

export interface GrantVersionSummary {
  id: string;
  versionNumber: number;
  capturedAt: string;
  status: string;
  verificationStatus: string;
  submissionCloseAt: string | null;
  isCurrent: boolean;
}

export interface GrantDetailResponse {
  grantCallId: string;
  canonicalCode: string | null;
  canonicalSlug: string;
  versionId: string;
  versionNumber: number;
  capturedAt: string;
  title: string;
  summary: string;
  status: string;
  verificationStatus: string;
  publishedAt: string | null;
  submissionOpenAt: string | null;
  submissionCloseAt: string | null;
  applicationUrl: string | null;
  officialDetailUrl: string | null;
  currencyCode: string | null;
  provider: GrantProviderDetail;
  programme: GrantProgrammeDetail;
  sources: GrantSourceRef[];
  deadlines: GrantDeadlineDetail[];
  fundingScenarios: GrantFundingScenarioDetail[];
  requirements: GrantRequirementDetail[];
  evidence: GrantEvidenceDetail[];
  changes: GrantChangeDetail[];
  versions: GrantVersionSummary[];
  availability: {
    funding: "AVAILABLE" | "UNKNOWN";
    requirements: "AVAILABLE" | "UNKNOWN";
    evidence: "AVAILABLE" | "SOURCE_ONLY";
  };
}

interface BaseRow {
  grant_call_id: string;
  canonical_code: string | null;
  canonical_slug: string;
  version_id: string;
  version_number: number;
  captured_at: string;
  title: string;
  summary: string | null;
  status: string;
  verification_status: string;
  published_at: string | null;
  submission_open_at: string | null;
  submission_close_at: string | null;
  application_url: string | null;
  official_detail_url: string | null;
  currency_code: string | null;
  programme_id: string;
  programme_name: string;
  funding_origin: string;
  programme_official_url: string | null;
  provider_id: string;
  provider_name: string;
  provider_type: string;
  provider_official_url: string | null;
}

interface SourceRow {
  source_code: string;
  source_name: string;
  canonical_url: string;
  last_seen_at: string;
  presence_state: string;
}

interface DeadlineRow {
  id: string;
  deadline_type: string;
  starts_at: string | null;
  ends_at: string | null;
  timezone: string | null;
  description: string | null;
  evidence_id: string | null;
}

interface FundingRow {
  id: string;
  name: string;
  currency_code: string;
  support_rate_min_bps: number | null;
  support_rate_max_bps: number | null;
  grant_amount_min_minor: number | null;
  grant_amount_max_minor: number | null;
  project_cost_min_minor: number | null;
  project_cost_max_minor: number | null;
  payment_mode: string | null;
  vat_rule: string | null;
  advance_payment_allowed: number | null;
  evidence_id: string | null;
}

interface RequirementRow {
  id: string;
  requirement_type: string;
  title: string;
  description: string | null;
  necessity: string;
  phase: string | null;
  evidence_id: string | null;
}

interface EvidenceRow {
  id: string;
  field_path: string;
  page_from: number | null;
  page_to: number | null;
  evidence_text: string | null;
  verification_status: string;
  document_title: string | null;
  source_url: string;
  retrieved_at: string;
}

interface ChangeRow {
  id: string;
  change_type: string;
  severity: string;
  field_path: string | null;
  old_value_json: string | null;
  new_value_json: string | null;
  created_at: string;
}

interface VersionRow {
  id: string;
  version_number: number;
  captured_at: string;
  status: string;
  verification_status: string;
  submission_close_at: string | null;
}

async function allRows<T>(
  db: D1DatabaseLike,
  sql: string,
  ...values: unknown[]
): Promise<T[]> {
  const result = await db.prepare(sql).bind(...values).all<T>();
  return result.results ?? [];
}

function parseJson(value: string | null): unknown {
  if (value === null) return null;
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return value;
  }
}

export function grantCallIdFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/grants\/([^/]+)$/);
  if (!match?.[1]) return null;
  try {
    const decoded = decodeURIComponent(match[1]);
    if (!decoded || decoded.length > 256) return null;
    return decoded;
  } catch {
    return null;
  }
}

export async function getGrantDetail(
  db: D1DatabaseLike,
  grantCallId: string,
): Promise<GrantDetailResponse | null> {
  const base = await db
    .prepare(`
      SELECT
        g.id AS grant_call_id,
        g.canonical_code,
        g.canonical_slug,
        v.id AS version_id,
        v.version_number,
        v.captured_at,
        v.title,
        v.summary,
        v.status,
        v.verification_status,
        v.published_at,
        v.submission_open_at,
        v.submission_close_at,
        v.application_url,
        v.official_detail_url,
        v.currency_code,
        pr.id AS programme_id,
        pr.name AS programme_name,
        pr.funding_origin,
        pr.official_url AS programme_official_url,
        p.id AS provider_id,
        p.name AS provider_name,
        p.provider_type,
        p.official_url AS provider_official_url
      FROM grant_calls g
      JOIN grant_call_versions v
        ON v.id = g.current_version_id
      JOIN programmes pr
        ON pr.id = g.programme_id
      JOIN providers p
        ON p.id = pr.provider_id
      WHERE g.id = ?
      LIMIT 1
    `)
    .bind(grantCallId)
    .first<BaseRow>();

  if (!base) return null;

  const [
    sourceRows,
    deadlineRows,
    fundingRows,
    requirementRows,
    evidenceRows,
    changeRows,
    versionRows,
  ] = await Promise.all([
    allRows<SourceRow>(
      db,
      `
        SELECT
          s.code AS source_code,
          s.name AS source_name,
          sr.canonical_url,
          sr.last_seen_at,
          sr.presence_state
        FROM source_records sr
        JOIN source_registry s ON s.id = sr.source_id
        WHERE sr.grant_call_id = ?
        ORDER BY sr.last_seen_at DESC, s.code ASC
        LIMIT 20
      `,
      grantCallId,
    ),
    allRows<DeadlineRow>(
      db,
      `
        SELECT
          id, deadline_type, starts_at, ends_at, timezone, description, evidence_id
        FROM grant_deadlines
        WHERE grant_call_version_id = ?
        ORDER BY COALESCE(ends_at, starts_at) ASC, id ASC
      `,
      base.version_id,
    ),
    allRows<FundingRow>(
      db,
      `
        SELECT
          id, name, currency_code,
          support_rate_min_bps, support_rate_max_bps,
          grant_amount_min_minor, grant_amount_max_minor,
          project_cost_min_minor, project_cost_max_minor,
          payment_mode, vat_rule, advance_payment_allowed, evidence_id
        FROM funding_scenarios
        WHERE grant_call_version_id = ?
        ORDER BY id ASC
      `,
      base.version_id,
    ),
    allRows<RequirementRow>(
      db,
      `
        SELECT
          id, requirement_type, title, description, necessity, phase, evidence_id
        FROM grant_requirements
        WHERE grant_call_version_id = ?
        ORDER BY
          CASE necessity
            WHEN 'REQUIRED' THEN 1
            WHEN 'CONDITIONAL' THEN 2
            ELSE 3
          END,
          id ASC
      `,
      base.version_id,
    ),
    allRows<EvidenceRow>(
      db,
      `
        SELECT
          fe.id,
          fe.field_path,
          fe.page_from,
          fe.page_to,
          fe.evidence_text,
          fe.verification_status,
          sd.title AS document_title,
          sd.source_url,
          dv.retrieved_at
        FROM field_evidence fe
        JOIN document_versions dv
          ON dv.id = fe.document_version_id
        JOIN source_documents sd
          ON sd.id = dv.source_document_id
        WHERE fe.entity_id IN (?, ?)
        ORDER BY fe.created_at DESC, fe.id ASC
        LIMIT 100
      `,
      base.version_id,
      grantCallId,
    ),
    allRows<ChangeRow>(
      db,
      `
        SELECT
          id, change_type, severity, field_path,
          old_value_json, new_value_json, created_at
        FROM change_events
        WHERE grant_call_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 20
      `,
      grantCallId,
    ),
    allRows<VersionRow>(
      db,
      `
        SELECT
          id, version_number, captured_at, status,
          verification_status, submission_close_at
        FROM grant_call_versions
        WHERE grant_call_id = ?
        ORDER BY version_number DESC
        LIMIT 20
      `,
      grantCallId,
    ),
  ]);

  const deadlines: GrantDeadlineDetail[] = deadlineRows.map((row) => ({
    id: row.id,
    type: row.deadline_type,
    startsAt: row.starts_at,
    endsAt: row.ends_at,
    timezone: row.timezone,
    description: row.description,
    evidenceId: row.evidence_id,
  }));

  // GrantCallVersion carries submission dates even when a source connector has
  // not yet normalized them into grant_deadlines. Expose them explicitly
  // instead of hiding known source data.
  if (
    deadlines.length === 0
    && (base.submission_open_at !== null || base.submission_close_at !== null)
  ) {
    deadlines.push({
      id: `${base.version_id}:submission-window`,
      type: "APPLICATION_WINDOW",
      startsAt: base.submission_open_at,
      endsAt: base.submission_close_at,
      timezone: "UTC",
      description: null,
      evidenceId: null,
    });
  }

  return {
    grantCallId: base.grant_call_id,
    canonicalCode: base.canonical_code,
    canonicalSlug: base.canonical_slug,
    versionId: base.version_id,
    versionNumber: base.version_number,
    capturedAt: base.captured_at,
    title: base.title,
    summary: base.summary ?? "",
    status: base.status,
    verificationStatus: base.verification_status,
    publishedAt: base.published_at,
    submissionOpenAt: base.submission_open_at,
    submissionCloseAt: base.submission_close_at,
    applicationUrl: base.application_url,
    officialDetailUrl: base.official_detail_url,
    currencyCode: base.currency_code,
    provider: {
      id: base.provider_id,
      name: base.provider_name,
      type: base.provider_type,
      officialUrl: base.provider_official_url,
    },
    programme: {
      id: base.programme_id,
      name: base.programme_name,
      fundingOrigin: base.funding_origin,
      officialUrl: base.programme_official_url,
    },
    sources: sourceRows.map((row) => ({
      sourceCode: row.source_code,
      sourceName: row.source_name,
      canonicalUrl: row.canonical_url,
      lastSeenAt: row.last_seen_at,
      presenceState: row.presence_state,
    })),
    deadlines,
    fundingScenarios: fundingRows.map((row) => ({
      id: row.id,
      name: row.name,
      currencyCode: row.currency_code,
      supportRateMinBps: row.support_rate_min_bps,
      supportRateMaxBps: row.support_rate_max_bps,
      grantAmountMinMinor: row.grant_amount_min_minor,
      grantAmountMaxMinor: row.grant_amount_max_minor,
      projectCostMinMinor: row.project_cost_min_minor,
      projectCostMaxMinor: row.project_cost_max_minor,
      paymentMode: row.payment_mode,
      vatRule: row.vat_rule,
      advancePaymentAllowed:
        row.advance_payment_allowed === null
          ? null
          : row.advance_payment_allowed === 1,
      evidenceId: row.evidence_id,
    })),
    requirements: requirementRows.map((row) => ({
      id: row.id,
      type: row.requirement_type,
      title: row.title,
      description: row.description,
      necessity: row.necessity,
      phase: row.phase,
      evidenceId: row.evidence_id,
    })),
    evidence: evidenceRows.map((row) => ({
      id: row.id,
      fieldPath: row.field_path,
      pageFrom: row.page_from,
      pageTo: row.page_to,
      evidenceText: row.evidence_text,
      verificationStatus: row.verification_status,
      documentTitle: row.document_title,
      sourceUrl: row.source_url,
      retrievedAt: row.retrieved_at,
    })),
    changes: changeRows.map((row) => ({
      id: row.id,
      changeType: row.change_type,
      severity: row.severity,
      fieldPath: row.field_path,
      oldValue: parseJson(row.old_value_json),
      newValue: parseJson(row.new_value_json),
      createdAt: row.created_at,
    })),
    versions: versionRows.map((row) => ({
      id: row.id,
      versionNumber: row.version_number,
      capturedAt: row.captured_at,
      status: row.status,
      verificationStatus: row.verification_status,
      submissionCloseAt: row.submission_close_at,
      isCurrent: row.id === base.version_id,
    })),
    availability: {
      funding: fundingRows.length ? "AVAILABLE" : "UNKNOWN",
      requirements: requirementRows.length ? "AVAILABLE" : "UNKNOWN",
      evidence: evidenceRows.length ? "AVAILABLE" : "SOURCE_ONLY",
    },
  };
}
