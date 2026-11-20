import type { D1DatabaseLike } from "./env";

/** Internal reference check only. It cannot certify source text, freshness, or finance applicability. */
export type FinanceApplicantPreflight = {
  status: "STRUCTURE_ONLY" | "NEEDS_INFORMATION" | "ERROR";
  reason: string;
  profileId: string | null;
  attributeValueIds: string[];
  evidenceIds: string[];
};

type ValueRow = {
  id: string; attribute_key: string; scope: string; data_type: string; active: number;
  value_type: string; value_json: string; value_length: number; nul_offset: number;
  source_kind: string; verification_status: string;
  evidence_id: string | null; observed_at: string; verified_at: string | null;
  evidence_created_at: string | null; document_retrieved_at: string | null;
  document_first_seen_at: string | null; trusted: number;
};

const scalarTypes = new Set(["STRING", "ENUM", "GEO_ID", "INTEGER", "NUMBER", "BOOLEAN", "MONEY_MINOR", "PERCENT_BPS"]);
const officialKinds = new Set(["ARES", "CZSO", "OTHER_OFFICIAL"]);

function instant(value: string | null): number | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value)) return null;
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return null;
  const canonical = new Date(time).toISOString();
  return canonical === (value.includes(".") ? value : value.replace(/Z$/, ".000Z")) ? time : null;
}

function validValue(row: ValueRow): boolean {
  if (!scalarTypes.has(row.data_type) || row.value_type !== row.data_type
    || typeof row.value_json !== "string" || typeof row.value_length !== "number"
    || row.nul_offset !== 0 || row.value_length > 4096 || row.value_length < 1 || row.value_json.length === 0) return false;
  try {
    const value: unknown = JSON.parse(row.value_json);
    if (["STRING", "ENUM", "GEO_ID"].includes(row.data_type)) return typeof value === "string" && value.length <= 4096;
    if (["INTEGER", "MONEY_MINOR", "PERCENT_BPS"].includes(row.data_type))
      return typeof value === "number" && Number.isSafeInteger(value);
    if (row.data_type === "NUMBER") return typeof value === "number" && Number.isFinite(value);
    return typeof value === "boolean";
  } catch { return false; }
}

/** principal must already be authenticated by the caller; profile ownership is rechecked in this snapshot. */
export async function preflightFinanceApplicantValues(
  db: D1DatabaseLike, principal: string, profileId: string, asOf: string,
): Promise<FinanceApplicantPreflight> {
  const result = (status: FinanceApplicantPreflight["status"], reason: string): FinanceApplicantPreflight =>
    ({ status, reason, profileId: null, attributeValueIds: [], evidenceIds: [] });
  const cutoff = instant(asOf);
  if (!principal || principal.length > 256 || !profileId || profileId.length > 256 || cutoff === null)
    return result("ERROR", "INVALID_PREFLIGHT_INPUT");
  let rows;
  try { rows = await db.batch([
    db.prepare("SELECT id, created_at FROM applicant_profiles WHERE id = ? AND user_id = ? LIMIT 1").bind(profileId, principal),
    db.prepare(`SELECT av.id, a.attribute_key, a.scope, a.data_type, a.active, av.value_type,
        substr(av.value_json, 1, 4097) AS value_json,
        length(CAST(av.value_json AS BLOB)) AS value_length,
        instr(CAST(av.value_json AS BLOB), x'00') AS nul_offset,
        av.source_kind, av.verification_status, av.evidence_id,
        av.observed_at, av.verified_at, fe.created_at AS evidence_created_at,
        dv.retrieved_at AS document_retrieved_at, sd.first_seen_at AS document_first_seen_at,
        CASE WHEN fe.entity_type = 'APPLICANT_ATTRIBUTE_VALUE' AND fe.entity_id = av.id
          AND fe.field_path = a.attribute_key AND fe.verification_status = 'VERIFIED'
          AND dv.extraction_status = 'EXTRACTED'
          AND sr.authority IN ('OFFICIAL', 'OFFICIAL_OPEN_DATA')
          AND (av.source_kind = 'OTHER_OFFICIAL'
            OR (av.source_kind = 'ARES' AND sr.code = 'ARES_PROFILE')
            OR (av.source_kind = 'CZSO' AND sr.code = 'CZSO_POPULATION')) THEN 1 ELSE 0 END AS trusted
      FROM applicant_attribute_values av
      JOIN applicant_profiles p ON p.id = av.applicant_profile_id AND p.user_id = ?
      LEFT JOIN attribute_definitions a ON a.id = av.attribute_definition_id
      LEFT JOIN field_evidence fe ON fe.id = av.evidence_id
      LEFT JOIN document_versions dv ON dv.id = fe.document_version_id
      LEFT JOIN source_documents sd ON sd.id = dv.source_document_id
      LEFT JOIN source_registry sr ON sr.id = sd.source_id
      WHERE av.applicant_profile_id = ? ORDER BY av.id LIMIT 129`).bind(principal, profileId),
  ]); } catch { return result("ERROR", "SNAPSHOT_READ_FAILED"); }
  if (rows.length !== 2 || rows.some((row) => !row.success)) return result("ERROR", "SNAPSHOT_READ_FAILED");
  const profiles = (rows[0].results ?? []) as { id: string; created_at: string }[];
  if (profiles.length !== 1) return result("NEEDS_INFORMATION", "PROFILE_NOT_OWNED");
  const profileCreated = instant(profiles[0].created_at);
  const values = (rows[1].results ?? []) as ValueRow[];
  if (values.length > 128) return result("ERROR", "ATTRIBUTE_LIMIT_EXCEEDED");
  if (!values.length) return result("NEEDS_INFORMATION", "NO_ATTRIBUTE_VALUES");
  for (const row of values) {
    if (!row.id || !row.attribute_key?.startsWith("applicant.") || row.scope !== "APPLICANT"
      || row.active !== 1 || !validValue(row)) return result("NEEDS_INFORMATION", "UNSUPPORTED_ATTRIBUTE_VALUE");
    if (row.verification_status !== "VERIFIED" || !officialKinds.has(row.source_kind)
      || !row.evidence_id || row.trusted !== 1)
      return result("NEEDS_INFORMATION", "UNVERIFIED_OFFICIAL_ATTRIBUTE_EVIDENCE");
    const observed = instant(row.observed_at);
    const verified = instant(row.verified_at);
    const created = instant(row.evidence_created_at);
    const retrieved = instant(row.document_retrieved_at);
    const firstSeen = instant(row.document_first_seen_at);
    // A source fact's effective observation date can precede its retrieval.
    if (profileCreated === null || observed === null || verified === null || created === null
      || retrieved === null || firstSeen === null || profileCreated > created || profileCreated > verified
      || firstSeen > retrieved || retrieved > created || retrieved > verified
      || observed > created || observed > verified || created > verified || verified > cutoff)
      return result("NEEDS_INFORMATION", "INCONSISTENT_ATTRIBUTE_TIMESTAMPS");
  }
  return { status: "STRUCTURE_ONLY", reason: "OWNED_OFFICIAL_ATTRIBUTE_REFERENCES_ONLY",
    profileId, attributeValueIds: values.map((row) => row.id), evidenceIds: values.map((row) => row.evidence_id!) };
}
