import { describe, expect, it } from "vitest";
import { evaluateRules } from "../src/eligibility";

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
});
