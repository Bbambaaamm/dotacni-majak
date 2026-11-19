import type { Env } from "./env";
import { ownerUserId } from "./applicantProfile";

type Result = "PASS" | "FAIL" | "UNKNOWN" | "ERROR" | "NOT_APPLICABLE";
type Status = "ELIGIBLE" | "LIKELY_ELIGIBLE" | "NEEDS_INFORMATION" | "INELIGIBLE" | "NEEDS_REVIEW";
type RuleSet = { id: string; completeness_status: string; verification_status: string };
type Group = { id: string; parent_group_id: string | null; group_operator: string; sort_order: number };
type Condition = { id: string; rule_group_id: string; attribute_key: string; scope: string; data_type: string; active: number;
  condition_operator: string; expected_value_json: string; blocking: number; unknown_policy: string;
  verification_status: string; evidence_id: string | null; sort_order: number };
type Value = { attribute_definition_id: string; attribute_key: string; data_type: string; value_type: string;
  value_json: string; source_kind: string; verification_status: string; evidence_id: string | null };
type Profile = { id: string; applicant_type: string; ico: string | null; legal_form_code: string | null;
  municipality_code: string | null; municipality_population: number | null; vat_status: string | null;
  organisation_size: string | null; cz_nace_json: string };
export type PublicCondition = { conditionId: string; attributeKey: string; result: Result; reason: string;
  blocking: boolean; evidenceId: string | null; inputSource: "PROFILE" | "ATTRIBUTE_VALUE" | null;
  inputVerification: string | null; inputEvidenceId: string | null };
export type EligibilityResponse = { grantCallId: string; versionId: string; ruleSetId: string | null;
  status: Status; rootResult: Result; reason: string; conditions: PublicCondition[];
  missingAttributes: string[]; blockers: string[] };

const columns: Record<string, keyof Profile> = {
  "applicant.type": "applicant_type", "applicant.ico": "ico", "applicant.legal_form": "legal_form_code",
  "applicant.municipality.code": "municipality_code", "applicant.municipality.population": "municipality_population",
  "applicant.vat_status": "vat_status", "applicant.organisation_size": "organisation_size",
  "applicant.cz_nace": "cz_nace_json",
};
const scalarTypes = new Set(["STRING", "ENUM", "GEO_ID", "INTEGER", "NUMBER", "BOOLEAN", "MONEY_MINOR", "PERCENT_BPS"]);
const operators = new Set(["EQ", "NEQ", "IN", "NOT_IN", "LT", "LTE", "GT", "GTE", "EXISTS", "NOT_EXISTS"]);

function parsed(raw: string): unknown {
  if (raw.length > 4096) throw new Error("OVERSIZE_VALUE");
  return JSON.parse(raw) as unknown;
}
function valid(value: unknown, type: string): boolean {
  if (["STRING", "ENUM", "GEO_ID"].includes(type)) return typeof value === "string";
  if (["INTEGER", "MONEY_MINOR", "PERCENT_BPS"].includes(type)) return typeof value === "number" && Number.isSafeInteger(value);
  if (type === "NUMBER") return typeof value === "number" && Number.isFinite(value);
  if (type === "BOOLEAN") return typeof value === "boolean";
  return false;
}
function aggregate(results: Result[], op: string): Result {
  const active = results.filter((r) => r !== "NOT_APPLICABLE");
  if (op === "NOT") return active[0] === "PASS" ? "FAIL" : active[0] === "FAIL" ? "PASS" : results[0];
  if (!active.length) return "NOT_APPLICABLE";
  if (op === "AND") {
    if (active.includes("FAIL")) return "FAIL";
    if (active.includes("ERROR")) return "ERROR";
    if (active.includes("UNKNOWN")) return "UNKNOWN";
    return "PASS";
  }
  if (active.includes("PASS")) return "PASS";
  if (active.includes("ERROR")) return "ERROR";
  if (active.includes("UNKNOWN")) return "UNKNOWN";
  return "FAIL";
}
function review(base: Pick<EligibilityResponse, "grantCallId" | "versionId" | "ruleSetId">, reason: string): EligibilityResponse {
  return { ...base, status: "NEEDS_REVIEW", rootResult: "ERROR", reason, conditions: [], missingAttributes: [], blockers: [] };
}

/** Pure, bounded subset of packages/eligibility's evaluator. No actual or expected values leave this function. */
export function evaluateRules(base: Pick<EligibilityResponse, "grantCallId" | "versionId" | "ruleSetId">,
  ruleSet: RuleSet, groups: Group[], conditions: Condition[], profile: Profile | null, values: Value[]): EligibilityResponse {
  if (!groups.length || groups.length > 64 || conditions.length > 128 || values.length > 128) return review(base, "INVALID_RULE_DEFINITION");
  const roots = groups.filter((g) => g.parent_group_id === null);
  if (roots.length !== 1 || conditions.length === 0 || !["COMPLETE", "PARTIAL", "UNKNOWN"].includes(ruleSet.completeness_status)
    || !["VERIFIED", "PARTIALLY_VERIFIED", "AUTO_EXTRACTED", "NEEDS_REVIEW"].includes(ruleSet.verification_status)) return review(base, "INVALID_RULE_DEFINITION");
  const groupIds = new Set(groups.map((g) => g.id));
  if (groupIds.size !== groups.length || conditions.some((c) => !groupIds.has(c.rule_group_id))) return review(base, "INVALID_RULE_DEFINITION");
  const byKey = new Map(values.map((v) => [v.attribute_key, v]));
  const out: PublicCondition[] = [];
  const visited = new Set<string>();
  function visit(group: Group, depth: number): Result {
    if (depth > 16 || visited.has(group.id) || !["AND", "OR", "NOT"].includes(group.group_operator)) throw new Error("INVALID_TREE");
    visited.add(group.id);
    const children = [
      ...groups.filter((g) => g.parent_group_id === group.id).map((g) => ({ order: g.sort_order, id: g.id, group: g })),
      ...conditions.filter((c) => c.rule_group_id === group.id).map((c) => ({ order: c.sort_order, id: c.id, condition: c })),
    ].sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
    if (!children.length || (group.group_operator === "NOT" && children.length !== 1)) throw new Error("INVALID_TREE");
    const results = children.map((child): Result => {
      if ("group" in child && child.group) return visit(child.group, depth + 1);
      if (!("condition" in child)) throw new Error("INVALID_TREE");
      const c = child.condition;
      if (c.scope !== "APPLICANT" || c.active !== 1 || !scalarTypes.has(c.data_type) || !operators.has(c.condition_operator)
        || ![0, 1].includes(c.blocking) || !["PROPAGATE", "NOT_APPLICABLE"].includes(c.unknown_policy)
        || !["VERIFIED", "PARTIALLY_VERIFIED", "AUTO_EXTRACTED", "NEEDS_REVIEW"].includes(c.verification_status)) throw new Error("UNSUPPORTED_RULE");
      if (["LT", "LTE", "GT", "GTE"].includes(c.condition_operator) && !["INTEGER", "NUMBER", "MONEY_MINOR", "PERCENT_BPS"].includes(c.data_type)) throw new Error("UNSUPPORTED_RULE");
      const expected = parsed(c.expected_value_json);
      if (["IN", "NOT_IN"].includes(c.condition_operator)) {
        if (!Array.isArray(expected) || expected.length > 64 || !expected.every((x) => valid(x, c.data_type))) throw new Error("INVALID_EXPECTED");
      } else if (!["EXISTS", "NOT_EXISTS"].includes(c.condition_operator) && !valid(expected, c.data_type)) throw new Error("INVALID_EXPECTED");
      let actual: unknown = undefined;
      let source: PublicCondition["inputSource"] = null;
      let verification: string | null = null;
      let inputEvidenceId: string | null = null;
      const column = columns[c.attribute_key];
      if (column && profile) {
        actual = column === "cz_nace_json" ? parsed(profile.cz_nace_json) : profile[column];
        if (actual === "UNKNOWN") actual = undefined;
        source = "PROFILE";
        // Client profile provenance cannot turn a condition into a verified rule.
        verification = "USER_DECLARED";
      } else if (profile) {
        const v = byKey.get(c.attribute_key);
        if (v) {
          if (v.data_type !== c.data_type || v.value_type !== c.data_type) throw new Error("INVALID_INPUT_TYPE");
          actual = parsed(v.value_json);
          source = "ATTRIBUTE_VALUE";
          verification = v.verification_status;
          inputEvidenceId = v.evidence_id;
        }
      }
      let result: Result;
      let reason: string;
      if (actual === undefined || actual === null) {
        result = c.unknown_policy === "NOT_APPLICABLE" ? "NOT_APPLICABLE" : "UNKNOWN";
        reason = "MISSING_INPUT";
      } else {
        if (!valid(actual, c.data_type)) throw new Error("INVALID_INPUT_TYPE");
        let matches: boolean;
        if (c.condition_operator === "EXISTS") matches = true;
        else if (c.condition_operator === "NOT_EXISTS") matches = false;
        else if (["IN", "NOT_IN"].includes(c.condition_operator)) {
          matches = (expected as unknown[]).some((x) => x === actual);
          if (c.condition_operator === "NOT_IN") matches = !matches;
        } else {
          switch (c.condition_operator) {
            case "EQ": matches = actual === expected; break;
            case "NEQ": matches = actual !== expected; break;
            case "LT": matches = (actual as number) < (expected as number); break;
            case "LTE": matches = (actual as number) <= (expected as number); break;
            case "GT": matches = (actual as number) > (expected as number); break;
            case "GTE": matches = (actual as number) >= (expected as number); break;
            default: throw new Error("UNSUPPORTED_RULE");
          }
        }
        result = matches ? "PASS" : "FAIL";
        reason = "EVALUATED";
      }
      out.push({ conditionId: c.id, attributeKey: c.attribute_key, result, reason, blocking: c.blocking === 1,
        evidenceId: c.evidence_id, inputSource: source, inputVerification: verification, inputEvidenceId });
      return c.blocking === 1 ? result : "NOT_APPLICABLE";
    });
    return aggregate(results, group.group_operator);
  }
  let root: Result;
  try {
    root = visit(roots[0], 0);
    if (visited.size !== groups.length || out.length !== conditions.length) throw new Error("INVALID_TREE");
  } catch {
    return review(base, "INVALID_RULE_DEFINITION");
  }
  const blocking = out.filter((c) => c.blocking);
  let status: Status;
  if (root === "ERROR") status = "NEEDS_REVIEW";
  else if (root === "FAIL") status = blocking.some((c) => c.result === "FAIL" && conditions.find((r) => r.id === c.conditionId)?.verification_status !== "VERIFIED") ? "NEEDS_REVIEW" : "INELIGIBLE";
  else if (root === "UNKNOWN") status = "NEEDS_INFORMATION";
  else if (root === "NOT_APPLICABLE") status = "NEEDS_REVIEW";
  else status = ruleSet.completeness_status === "COMPLETE" && ruleSet.verification_status === "VERIFIED"
    && blocking.every((c) => c.result === "NOT_APPLICABLE" || conditions.find((r) => r.id === c.conditionId)?.verification_status === "VERIFIED")
    ? "ELIGIBLE" : "LIKELY_ELIGIBLE";
  return { ...base, status, rootResult: root, reason: "EVALUATED", conditions: out,
    missingAttributes: [...new Set(out.filter((c) => c.result === "UNKNOWN" && c.reason === "MISSING_INPUT").map((c) => c.attributeKey))],
    blockers: out.filter((c) => c.blocking && c.result === "FAIL").map((c) => c.conditionId) };
}

export function eligibilityPath(pathname: string): string | null {
  const match = /^\/grants\/([^/]+)\/eligibility$/.exec(pathname);
  if (!match || match[1].length > 256) return null;
  try { const id = decodeURIComponent(match[1]); return id && id.length <= 256 ? id : null; } catch { return null; }
}

export async function evaluateGrant(env: Env, token: string, grantCallId: string): Promise<EligibilityResponse | null> {
  const principal = await ownerUserId(token, env);
  const version = await env.DB.prepare(`SELECT v.id FROM grant_calls g JOIN grant_call_versions v ON v.id = g.current_version_id
    WHERE g.id = ? AND v.grant_call_id = g.id LIMIT 1`).bind(grantCallId).first<{ id: string }>();
  if (!version) return null;
  const base = { grantCallId, versionId: version.id, ruleSetId: null as string | null };
  const sets = (await env.DB.prepare(`SELECT id, completeness_status, verification_status FROM eligibility_rule_sets
    WHERE grant_call_version_id = ? ORDER BY id LIMIT 2`).bind(version.id).all<RuleSet>()).results ?? [];
  if (!sets.length) return { ...base, status: "NEEDS_REVIEW", rootResult: "UNKNOWN", reason: "NO_RULE_SET",
    conditions: [], missingAttributes: [], blockers: [] };
  if (sets.length !== 1) return review(base, "MULTIPLE_RULE_SETS");
  base.ruleSetId = sets[0].id;
  const [groupRows, conditionRows, profile] = await Promise.all([
    env.DB.prepare(`SELECT id, parent_group_id, group_operator, sort_order FROM rule_groups WHERE rule_set_id = ? ORDER BY sort_order, id LIMIT 65`).bind(sets[0].id).all<Group>(),
    env.DB.prepare(`SELECT c.id, c.rule_group_id, a.attribute_key, a.scope, a.data_type, a.active, c.condition_operator,
      c.expected_value_json, c.blocking, c.unknown_policy, c.verification_status, c.evidence_id, c.sort_order
      FROM rule_conditions c JOIN rule_groups g ON g.id = c.rule_group_id JOIN attribute_definitions a ON a.id = c.attribute_definition_id
      WHERE g.rule_set_id = ? ORDER BY c.sort_order, c.id LIMIT 129`).bind(sets[0].id).all<Condition>(),
    env.DB.prepare(`SELECT id, applicant_type, ico, legal_form_code, municipality_code, municipality_population,
      vat_status, organisation_size, cz_nace_json FROM applicant_profiles WHERE user_id = ? LIMIT 1`).bind(principal).first<Profile>(),
  ]);
  const groups = (groupRows.results ?? []) as Group[];
  const conditions = (conditionRows.results ?? []) as Condition[];
  if (groups.length > 64 || conditions.length > 128) return review(base, "RULE_LIMIT_EXCEEDED");
  if (!profile) {
    const checked = evaluateRules(base, sets[0], groups, conditions, null, []);
    if (checked.status === "NEEDS_REVIEW") return checked;
    return { ...base, status: "NEEDS_INFORMATION", rootResult: "UNKNOWN", reason: "NO_PROFILE",
      conditions: checked.conditions, missingAttributes: checked.missingAttributes, blockers: [] };
  }
  const values = (await env.DB.prepare(`SELECT av.attribute_definition_id, a.attribute_key, a.data_type, av.value_type,
    av.value_json, av.source_kind, av.verification_status, av.evidence_id FROM applicant_attribute_values av
    JOIN attribute_definitions a ON a.id = av.attribute_definition_id WHERE av.applicant_profile_id = ? LIMIT 129`).bind(profile.id).all<Value>()).results ?? [];
  if (values.length > 128) return review(base, "INPUT_LIMIT_EXCEEDED");
  return evaluateRules(base, sets[0], groups, conditions, profile, values);
}
