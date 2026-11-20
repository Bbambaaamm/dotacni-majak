import type { D1DatabaseLike } from "./env";

/** Provenance-only gate for #304. It does not evaluate applicant values or calculate money. */
export type FinanceProvenance = {
  status: "VERIFIED" | "NEEDS_INFORMATION" | "ERROR";
  reason: string;
  versionId: string | null;
  ruleSetId: string | null;
  scenarioIds: string[];
  conditionEvidenceIds: Record<string, string>;
};

type Version = { id: string; verification_status: string };
type SetRow = { id: string; completeness_status: string; verification_status: string };
type Group = { id: string; parent_group_id: string | null; group_operator: string };
type Condition = { id: string; rule_group_id: string; evidence_id: string | null; verification_status: string; trusted: number;
  attribute_key: string; scope: string; data_type: string; active: number; condition_operator: string;
  expected_value_json: string; blocking: number; unknown_policy: string };
type Scenario = { id: string; condition_group_id: string | null; trusted: number };

// Finance may use only the deterministic scalar applicant-rule subset supported by
// the eligibility evaluator. Unsupported operands are not proven by source evidence.
const scalarTypes = new Set(["STRING", "ENUM", "GEO_ID", "INTEGER", "NUMBER", "BOOLEAN", "MONEY_MINOR", "PERCENT_BPS"]);
const operators = new Set(["EQ", "NEQ", "IN", "NOT_IN", "LT", "LTE", "GT", "GTE", "EXISTS", "NOT_EXISTS"]);
function validOperand(value: unknown, type: string): boolean {
  if (["STRING", "ENUM", "GEO_ID"].includes(type)) return typeof value === "string";
  if (["INTEGER", "MONEY_MINOR", "PERCENT_BPS"].includes(type)) return typeof value === "number" && Number.isSafeInteger(value);
  if (type === "NUMBER") return typeof value === "number" && Number.isFinite(value);
  return type === "BOOLEAN" && typeof value === "boolean";
}
function supportedCondition(c: Condition): boolean {
  if (c.scope !== "APPLICANT" || c.active !== 1 || typeof c.attribute_key !== "string" || !c.attribute_key.startsWith("applicant.")
    || !scalarTypes.has(c.data_type) || !operators.has(c.condition_operator)
    || ![0, 1].includes(c.blocking) || !["PROPAGATE", "NOT_APPLICABLE"].includes(c.unknown_policy)
    || typeof c.expected_value_json !== "string" || c.expected_value_json.length > 4096
    || (["LT", "LTE", "GT", "GTE"].includes(c.condition_operator)
      && !["INTEGER", "NUMBER", "MONEY_MINOR", "PERCENT_BPS"].includes(c.data_type))) return false;
  try {
    const expected: unknown = JSON.parse(c.expected_value_json);
    if (["EXISTS", "NOT_EXISTS"].includes(c.condition_operator)) return expected === null;
    if (["IN", "NOT_IN"].includes(c.condition_operator))
      return Array.isArray(expected) && expected.length > 0 && expected.length <= 64
        && expected.every((value: unknown) => validOperand(value, c.data_type));
    return validOperand(expected, c.data_type);
  } catch { return false; }
}

export async function verifyFinanceRuleProvenance(db: D1DatabaseLike, grantCallId: string): Promise<FinanceProvenance> {
  const result = (status: FinanceProvenance["status"], reason: string, versionId: string | null = null,
    ruleSetId: string | null = null): FinanceProvenance =>
    ({ status, reason, versionId, ruleSetId, scenarioIds: [], conditionEvidenceIds: {} });
  if (!grantCallId || grantCallId.length > 256) return result("ERROR", "INVALID_GRANT_CALL_ID");
  const versionSql = `SELECT v.id, v.verification_status FROM grant_calls g JOIN grant_call_versions v
    ON v.id = g.current_version_id AND v.grant_call_id = g.id WHERE g.id = ? LIMIT 1`;
  const versionIdSql = `SELECT id FROM (${versionSql})`;
  const ruleSetSql = `SELECT id FROM eligibility_rule_sets
    WHERE grant_call_version_id = (${versionIdSql}) ORDER BY id LIMIT 1`;
  // All five reads are bound to the same current-version subquery in one D1 batch
  // (one consistent SQLite snapshot); never trust a caller-provided version/ID.
  const rows = await db.batch([
    db.prepare(versionSql).bind(grantCallId),
    db.prepare(`SELECT id, completeness_status, verification_status FROM eligibility_rule_sets
      WHERE grant_call_version_id = (${versionIdSql}) ORDER BY id LIMIT 2`).bind(grantCallId),
    db.prepare(`SELECT id, parent_group_id, group_operator FROM rule_groups
      WHERE rule_set_id = (${ruleSetSql}) ORDER BY id LIMIT 65`).bind(grantCallId),
    db.prepare(`SELECT c.id, c.rule_group_id, c.evidence_id, c.verification_status,
      a.attribute_key, a.scope, a.data_type, a.active, c.condition_operator,
      c.expected_value_json, c.blocking, c.unknown_policy,
      CASE WHEN EXISTS (SELECT 1 FROM field_evidence fe
        JOIN document_versions dv ON dv.id = fe.document_version_id
        JOIN source_documents sd ON sd.id = dv.source_document_id
        JOIN source_registry sr ON sr.id = sd.source_id
        WHERE fe.id = c.evidence_id AND fe.entity_type = 'GRANT_CALL_VERSION'
          AND fe.entity_id = (${versionIdSql}) AND fe.field_path = '/rule_conditions/' || c.id
          AND fe.verification_status = 'VERIFIED' AND dv.extraction_status = 'EXTRACTED'
          AND sd.grant_call_id = ? AND sr.authority IN ('OFFICIAL','OFFICIAL_OPEN_DATA'))
        THEN 1 ELSE 0 END AS trusted
      FROM rule_conditions c JOIN rule_groups g ON g.id = c.rule_group_id
      LEFT JOIN attribute_definitions a ON a.id = c.attribute_definition_id
      WHERE g.rule_set_id = (${ruleSetSql}) ORDER BY c.id LIMIT 129`)
      .bind(grantCallId, grantCallId, grantCallId),
    db.prepare(`SELECT fs.id, fs.condition_group_id,
      CASE WHEN EXISTS (SELECT 1 FROM field_evidence fe
        JOIN document_versions dv ON dv.id = fe.document_version_id
        JOIN source_documents sd ON sd.id = dv.source_document_id
        JOIN source_registry sr ON sr.id = sd.source_id
        WHERE fe.id = fs.evidence_id AND fe.entity_type = 'GRANT_CALL_VERSION'
          AND fe.entity_id = fs.grant_call_version_id
          AND fe.field_path = '/funding_scenarios/' || fs.id
          AND fe.verification_status = 'VERIFIED' AND dv.extraction_status = 'EXTRACTED'
          AND sd.grant_call_id = ? AND sr.authority IN ('OFFICIAL','OFFICIAL_OPEN_DATA'))
        THEN 1 ELSE 0 END AS trusted
      FROM funding_scenarios fs WHERE fs.grant_call_version_id = (${versionIdSql})
      ORDER BY fs.id LIMIT 65`).bind(grantCallId, grantCallId),
  ]);
  if (rows.some((row) => !row.success)) return result("ERROR", "SNAPSHOT_READ_FAILED");
  const version = (rows[0].results ?? []) as Version[];
  if (version.length !== 1) return result("NEEDS_INFORMATION", "NO_CURRENT_VERSION");
  const versionId = version[0].id;
  if (version[0].verification_status !== "VERIFIED")
    return result("NEEDS_INFORMATION", "GRANT_VERSION_UNVERIFIED", versionId);
  const sets = (rows[1].results ?? []) as SetRow[];
  if (sets.length !== 1) return result("NEEDS_INFORMATION", "RULE_SET_NOT_UNIQUE", versionId);
  const ruleSetId = sets[0].id;
  if (sets[0].completeness_status !== "COMPLETE" || sets[0].verification_status !== "VERIFIED")
    return result("NEEDS_INFORMATION", "RULE_SET_UNVERIFIED", versionId, ruleSetId);
  const groups = (rows[2].results ?? []) as Group[];
  const conditions = (rows[3].results ?? []) as Condition[];
  const scenarios = (rows[4].results ?? []) as Scenario[];
  if (groups.length > 64 || conditions.length > 128 || scenarios.length > 64)
    return result("ERROR", "SNAPSHOT_LIMIT_EXCEEDED", versionId, ruleSetId);
  const byGroup = new Map(groups.map((group) => [group.id, group]));
  if (!groups.length || byGroup.size !== groups.length || groups.filter((g) => g.parent_group_id === null).length !== 1
    || conditions.length === 0 || scenarios.length === 0 || scenarios.some((s) => !s.condition_group_id || !byGroup.has(s.condition_group_id)))
    return result("NEEDS_INFORMATION", "INCOMPLETE_RULE_GRAPH", versionId, ruleSetId);
  const seen = new Set<string>();
  const visit = (group: Group, stack: Set<string>): boolean => {
    if (stack.has(group.id)) return false;
    if (seen.has(group.id)) return true;
    seen.add(group.id);
    const next = new Set(stack); next.add(group.id);
    return groups.filter((g) => g.parent_group_id === group.id).every((child) => visit(child, next));
  };
  if (!visit(groups.find((g) => g.parent_group_id === null)!, new Set()) || seen.size !== groups.length)
    return result("ERROR", "INVALID_RULE_GRAPH", versionId, ruleSetId);
  const hasCondition = (groupId: string): boolean => conditions.some((c) => c.rule_group_id === groupId)
    || groups.some((g) => g.parent_group_id === groupId && hasCondition(g.id));
  if (scenarios.some((s) => !hasCondition(s.condition_group_id!)))
    return result("NEEDS_INFORMATION", "INCOMPLETE_RULE_GRAPH", versionId, ruleSetId);
  // Mirror the deterministic evaluator's structural constraints before certifying
  // a group as selectable. In particular, NOT must have exactly one direct child.
  const supportedGroup = (group: Group, depth: number): boolean => {
    if (depth > 16 || !["AND", "OR", "NOT"].includes(group.group_operator)) return false;
    const children = groups.filter((g) => g.parent_group_id === group.id);
    const count = children.length + conditions.filter((c) => c.rule_group_id === group.id).length;
    return count > 0 && (group.group_operator !== "NOT" || count === 1)
      && children.every((child) => supportedGroup(child, depth + 1));
  };
  if (!supportedGroup(groups.find((g) => g.parent_group_id === null)!, 0))
    return result("NEEDS_INFORMATION", "UNSUPPORTED_RULE_GRAPH", versionId, ruleSetId);
  if (conditions.some((c) => !byGroup.has(c.rule_group_id) || c.verification_status !== "VERIFIED" || c.trusted !== 1 || !c.evidence_id)
    || scenarios.some((s) => s.trusted !== 1))
    return result("NEEDS_INFORMATION", "UNVERIFIED_OFFICIAL_EVIDENCE", versionId, ruleSetId);
  if (conditions.some((c) => !supportedCondition(c)))
    return result("NEEDS_INFORMATION", "UNSUPPORTED_RULE_OPERAND", versionId, ruleSetId);
  return { status: "VERIFIED", reason: "VERSION_BOUND_OFFICIAL_EVIDENCE", versionId, ruleSetId,
    scenarioIds: scenarios.map((s) => s.id),
    conditionEvidenceIds: Object.fromEntries(conditions.map((c) => [c.id, c.evidence_id!])),
  };
}
