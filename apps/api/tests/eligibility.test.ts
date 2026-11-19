import { describe, expect, it } from "vitest";
import { evaluateGrant, evaluateRules } from "../src/eligibility";
import type { Env } from "../src/env";

const base = { grantCallId: "g", versionId: "v", ruleSetId: "rs" };
const set = { id: "rs", completeness_status: "COMPLETE", verification_status: "VERIFIED" };
const groups = [{ id: "root", parent_group_id: null, group_operator: "AND", sort_order: 0 }];
const condition = { id: "c", rule_group_id: "root", attribute_key: "applicant.type", scope: "APPLICANT",
  data_type: "ENUM", active: 1, condition_operator: "EQ", expected_value_json: '"MUNICIPALITY"',
  blocking: 1, unknown_policy: "PROPAGATE", verification_status: "VERIFIED", evidence_id: "evidence-1", sort_order: 0 };
const profile = { id: "p", applicant_type: "MUNICIPALITY", ico: null, legal_form_code: null,
  municipality_code: null, municipality_population: null, vat_status: null, organisation_size: null,
  cz_nace_json: "[]", field_sources_json: "{}" };

describe("eligibility evaluator parity subset", () => {
  it("preserves Python's missing, pass, fail and verification status", () => {
    expect(evaluateRules(base, set, groups, [condition], null, [])).toMatchObject({
      rootResult: "UNKNOWN", status: "NEEDS_INFORMATION", missingAttributes: ["applicant.type"],
    });
    const pass = evaluateRules(base, set, groups, [condition], profile, []);
    expect(pass).toMatchObject({ status: "ELIGIBLE", rootResult: "PASS", conditions: [{
      conditionId: "c", evidenceId: "evidence-1", inputSource: "PROFILE", result: "PASS",
    }] });
    expect(JSON.stringify(pass)).not.toContain("MUNICIPALITY");
    expect(evaluateRules(base, set, groups, [condition], { ...profile, applicant_type: "BUSINESS" }, []))
      .toMatchObject({ status: "INELIGIBLE", rootResult: "FAIL", blockers: ["c"] });
    expect(evaluateRules(base, set, groups, [{ ...condition, verification_status: "AUTO_EXTRACTED" }],
      { ...profile, applicant_type: "BUSINESS" }, []).status).toBe("NEEDS_REVIEW");
  });

  it("evaluates bounded IN and integer comparisons with dynamic evidence", () => {
    const population = { ...condition, id: "population", attribute_key: "applicant.population.custom",
      data_type: "INTEGER", condition_operator: "LTE", expected_value_json: "5000" };
    const value = { attribute_definition_id: "a", attribute_key: population.attribute_key, data_type: "INTEGER",
      value_type: "INTEGER", value_json: "3200", source_kind: "CZSO", verification_status: "VERIFIED",
      evidence_id: "input-evidence" };
    const result = evaluateRules(base, set, groups, [population], profile, [value]);
    expect(result).toMatchObject({ status: "ELIGIBLE", conditions: [{ inputSource: "ATTRIBUTE_VALUE",
      inputEvidenceId: "input-evidence", inputVerification: "VERIFIED", result: "PASS" }] });
    expect(JSON.stringify(result)).not.toContain("3200");
    expect(JSON.stringify(result)).not.toContain("5000");
    expect(evaluateRules(base, set, groups, [{ ...condition, condition_operator: "IN",
      expected_value_json: '["MUNICIPALITY","REGION"]' }], profile, []).status).toBe("ELIGIBLE");
  });

  it("falls back from missing mapped values while keeping present columns authoritative", () => {
    const legal = { ...condition, id: "legal", attribute_key: "applicant.legal_form",
      data_type: "STRING", expected_value_json: '"GOOD"', unknown_policy: "NOT_APPLICABLE" };
    const sparse = { attribute_definition_id: "attr-applicant-legal-form", attribute_key: legal.attribute_key,
      data_type: "STRING", value_type: "STRING", value_json: '"BAD"', source_kind: "ARES",
      verification_status: "VERIFIED", evidence_id: "input-evidence" };
    const failed = evaluateRules(base, set, groups, [condition, legal], profile, [sparse]);
    expect(failed).toMatchObject({ status: "INELIGIBLE", rootResult: "FAIL", blockers: ["legal"],
      conditions: [{ result: "PASS" }, { result: "FAIL", inputSource: "ATTRIBUTE_VALUE",
        inputVerification: "VERIFIED", inputEvidenceId: "input-evidence" }] });
    expect(evaluateRules(base, set, groups, [legal], { ...profile, legal_form_code: "GOOD" }, [sparse]))
      .toMatchObject({ rootResult: "PASS", conditions: [{ inputSource: "PROFILE", result: "PASS" }] });
    expect(evaluateRules(base, set, groups, [legal], { ...profile, legal_form_code: "UNKNOWN" }, [sparse]))
      .toMatchObject({ rootResult: "FAIL", conditions: [{ inputSource: "ATTRIBUTE_VALUE" }] });
    expect(evaluateRules(base, set, groups, [legal], profile, [])).toMatchObject({
      rootResult: "NOT_APPLICABLE", status: "NEEDS_REVIEW", conditions: [{ result: "NOT_APPLICABLE" }] });
  });

  it("fails closed for conflicting or invalid sparse fallbacks", () => {
    const legal = { ...condition, attribute_key: "applicant.legal_form", data_type: "STRING",
      expected_value_json: '"GOOD"' };
    const sparse = { attribute_definition_id: "attr-applicant-legal-form", attribute_key: legal.attribute_key,
      data_type: "STRING", value_type: "STRING", value_json: '"BAD"', source_kind: "ARES",
      verification_status: "VERIFIED", evidence_id: "input-evidence" };
    for (const altered of [{ value_type: "INTEGER" }, { value_json: "42" },
      { value_json: "{bad" }, { source_kind: "USER", verification_status: "VERIFIED" },
      { source_kind: "ARES", verification_status: "USER_DECLARED" }]) {
      expect(evaluateRules(base, set, groups, [legal], profile, [{ ...sparse, ...altered }]))
        .toMatchObject({ status: "NEEDS_REVIEW", rootResult: "ERROR" });
    }
    expect(evaluateRules(base, set, groups, [legal], profile, [sparse, { ...sparse, value_json: '"GOOD"' }]))
      .toMatchObject({ status: "NEEDS_REVIEW", rootResult: "ERROR" });
    expect(evaluateRules(base, set, groups, [{ ...legal, condition_operator: "EXISTS" }], profile,
      [{ ...sparse, value_json: "null" }])).toMatchObject({ rootResult: "UNKNOWN", status: "NEEDS_INFORMATION" });
  });

  it("fails closed for malformed, unsupported, and disconnected rules", () => {
    for (const altered of [
      { condition_operator: "GEO_WITHIN" }, { expected_value_json: "{bad" },
      { expected_value_json: "42" }, { data_type: "STRING_SET" },
    ]) expect(evaluateRules(base, set, groups, [{ ...condition, ...altered }], profile, []).status).toBe("NEEDS_REVIEW");
    expect(evaluateRules(base, set, [...groups, { id: "orphan", parent_group_id: null, group_operator: "AND", sort_order: 1 }],
      [condition], profile, []).status).toBe("NEEDS_REVIEW");
    expect(evaluateRules(base, set, groups, [{ ...condition, unknown_policy: "NOT_APPLICABLE" }], null, [])
      .status).toBe("NEEDS_REVIEW");
  });

  it("matches the supported scalar operator and group truth tables", () => {
    const cases: [string, string, string][] = [
      ["EQ", '"MUNICIPALITY"', "PASS"], ["NEQ", '"REGION"', "PASS"],
      ["IN", '["REGION","MUNICIPALITY"]', "PASS"], ["NOT_IN", '["REGION"]', "PASS"],
      ["EXISTS", "null", "PASS"], ["NOT_EXISTS", "null", "FAIL"],
    ];
    for (const [condition_operator, expected_value_json, rootResult] of cases) {
      expect(evaluateRules(base, set, groups, [{ ...condition, condition_operator, expected_value_json }], profile, [])
        .rootResult).toBe(rootResult);
    }
    const population = { ...condition, id: "n", attribute_key: "applicant.municipality.population",
      data_type: "INTEGER", expected_value_json: "5" };
    for (const [op, result] of [["LT", "PASS"], ["LTE", "PASS"], ["GT", "FAIL"], ["GTE", "FAIL"]]) {
      expect(evaluateRules(base, set, groups, [{ ...population, condition_operator: op }],
        { ...profile, municipality_population: 4 }, []).rootResult).toBe(result);
    }
    const second = { ...condition, id: "second", expected_value_json: '"REGION"' };
    expect(evaluateRules(base, set, groups, [condition, second], profile, []).rootResult).toBe("FAIL");
    expect(evaluateRules(base, set, [{ ...groups[0], group_operator: "OR" }],
      [condition, second], profile, []).rootResult).toBe("PASS");
    expect(evaluateRules(base, set, [{ ...groups[0], group_operator: "NOT" }],
      [condition], profile, []).rootResult).toBe("FAIL");
  });

  it("tracks verified causes through NOT and OR for failures", () => {
    const nested = [
      { ...groups[0], group_operator: "NOT" },
      { id: "choice", parent_group_id: "root", group_operator: "OR", sort_order: 0 },
    ];
    const first = { ...condition, id: "first", rule_group_id: "choice", verification_status: "AUTO_EXTRACTED" };
    const second = { ...condition, id: "second", rule_group_id: "choice", expected_value_json: '"REGION"', sort_order: 1 };
    expect(evaluateRules(base, set, nested, [first, second], profile, [])).toMatchObject({
      rootResult: "FAIL", status: "NEEDS_REVIEW", blockers: ["first"],
    });
    expect(evaluateRules(base, set, nested, [{ ...first, verification_status: "VERIFIED" }, second], profile, []))
      .toMatchObject({ rootResult: "FAIL", status: "INELIGIBLE", blockers: ["first"] });
    const doubleNot = [...nested, { id: "inner", parent_group_id: "choice", group_operator: "NOT", sort_order: 0 }];
    expect(evaluateRules(base, set, doubleNot, [{ ...first, rule_group_id: "inner" }, second], profile, []))
      .toMatchObject({ rootResult: "PASS", status: "LIKELY_ELIGIBLE", blockers: [] });
  });

  it("uses one read-only batch for fresh version, rules and applicant inputs", async () => {
    let applicant = false;
    const batches: { query: string; params: unknown[] }[][] = [];
    const env = { DB: {
      prepare(query: string) {
        const statement = { query, params: [] as unknown[],
          bind(...params: unknown[]) { this.params = params; return this; },
          async first() { return { owner_user_id: "owner" }; },
          async all() { throw new Error("evaluation read outside batch"); },
          async run() { throw new Error("evaluation write"); },
        };
        return statement;
      },
      async batch(statements: { query: string; params: unknown[] }[]) {
        batches.push(statements);
        return [
          [{ id: "v" }], [set], [groups[0]], [condition],
          applicant ? [profile] : [], [],
        ].map((results) => ({ success: true, results }));
      },
    } } as unknown as Env;
    const token = "A".repeat(43);
    expect((await evaluateGrant(env, token, "g"))?.status).toBe("NEEDS_INFORMATION");
    applicant = true;
    expect((await evaluateGrant(env, token, "g"))?.status).toBe("ELIGIBLE");
    expect(batches).toHaveLength(2);
    for (const statements of batches) {
      expect(statements).toHaveLength(6);
      expect(statements.every((statement) => /^\s*SELECT\b/i.test(statement.query))).toBe(true);
      expect(statements.slice(0, 4).every((statement) => statement.params[0] === "g")).toBe(true);
      expect(statements.slice(4).every((statement) => statement.params[0] === "owner")).toBe(true);
    }
  });
});
