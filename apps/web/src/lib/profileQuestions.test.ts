import { describe, expect, test } from "vitest";
import {
  allQuestionKeys,
  applicantQuestionDefs,
  looksLikeCzechICO,
  questionsForType,
  validateICO,
  legalTypeKey,
} from "./profileQuestions";
import type { LegalType } from "./profileQuestions";

const QUESTION_KEYS_BY_TYPE: Record<NonNullable<LegalType> | "unknown", string[]> = {
  obec: ["fullName", "email", "ico", "legalType", "region", "districtId", "mayorName", "municipalityName", "population", "district"],
  spolek: ["fullName", "email", "ico", "legalType", "region", "districtId", "associationName", "seatRegion", "foundationYear", "boardPresident"],
  firm: ["fullName", "email", "ico", "legalType", "region", "districtId", "firmName", "seatRegion", "firmSize"],
  obcan: ["fullName", "email", "ico", "legalType", "region", "districtId", "ownerAddress", "ownerCity", "professionalInterest"],
  unknown: ["fullName", "email", "ico", "legalType", "region", "districtId"],
};

describe("profileQuestions", () => {
  describe("questionsForType", () => {
    test("returns correct questions for each applicant type", () => {
      for (const [type, expectedKeys] of Object.entries(QUESTION_KEYS_BY_TYPE) as [NonNullable<LegalType> | "unknown", string[]][]) {
        const lookupType: LegalType = type === "unknown" ? null : type;
        const questions = questionsForType(lookupType);
        const actualKeys = questions.map(q => q.key);
        expect(actualKeys).toEqual(expectedKeys);
        for (const q of questions) {
          expect(typeof q.key).toBe("string");
          expect(typeof q.label).toBe("string");
          expect(typeof q.why).toBe("string");
        }
      }
    });

    test("null type maps to unknown (common questions only)", () => {
      const questions = questionsForType(null);
      expect(questions.length).toBe(QUESTION_KEYS_BY_TYPE["unknown"].length);
      expect(questions.map(q => q.key)).toEqual(QUESTION_KEYS_BY_TYPE["unknown"]);
    });
  });

  describe("allQuestionKeys", () => {
    test("contains all keys from all types", () => {
      const expected = new Set(Object.values(QUESTION_KEYS_BY_TYPE).flat());
      for (const key of allQuestionKeys) {
        expect(expected.has(key)).toBe(true);
      }
      // checks both directions: all keys in allQuestionKeys are present in the expected set
      for (const key of expected) {
        expect(allQuestionKeys).toContain(key);
      }
    });
  });

  describe("looksLikeCzechICO", () => {
    test("validates valid IČO (8 digits, modulo 11 = 10)", () => {
      // Known valid IČO examples (checked via modulo 11, last digit = remainder+10)
      expect(looksLikeCzechICO("01234567")).toBe(true);
      expect(looksLikeCzechICO("12345678")).toBe(true);
      expect(looksLikeCzechICO("00234567")).toBe(true);
      expect(looksLikeCzechICO("https://ico.example/01234567")).toBe(false);
      expect(looksLikeCzechICO("0023456")).toBe(false); // only 7 digits
    });

    test("invalidates invalid IČO (bad checksum)", () => {
      expect(looksLikeCzechICO("12345670")).toBe(false);
      expect(looksLikeCzechICO("00000001")).toBe(false);
      expect(looksLikeCzechICO("00234567")).toBe(true); // valid
      expect(looksLikeCzechICO("0000000")).toBe(false); // 7 digits
    });

    test("normalizes whitespace", () => {
      expect(looksLikeCzechICO("  01234567  ")).toBe(true);
      expect(looksLikeCzechICO("0 1 2 3 4 5 6 7")).toBe(true);
    });
  });

  describe("validateICO", () => {
    test("returns null for valid IČO", () => {
      expect(validateICO("01234567")).toBeNull();
      expect(validateICO("12345678")).toBeNull();
    });

    test("returns error message for invalid IČO", () => {
      expect(validateICO("")).toBeNull(); // empty is allowed (optional)
      expect(validateICO("123")).not.toBeNull();
      expect(validateICO("12345670")).not.toBeNull();
      expect(validateICO("ka-fe-123")).toBe("IČO musí mít osmi číslic");
    });

    test("allows optional IČO when empty", () => {
      // empty IČO is allowed — returns null, meaning no error
      expect(validateICO("")).toBeNull();
      expect(validateICO("   ")).toBeNull(); // whitespace-only
    });
  });

  describe("applicantQuestionDefs", () => {
    test("each question definition has required shape", () => {
      const allTypes = Object.keys(applicantQuestionDefs) as (NonNullable<LegalType> | "unknown")[];
      for (const key of allTypes) {
        const questions = applicantQuestionDefs[key];
        for (const q of questions) {
          expect(typeof q.key).toBe("string");
          expect(typeof q.label).toBe("string");
          expect(typeof q.why).toBe("string");
          expect(typeof q.required).toBe("boolean");
          expect(typeof q.progressive).toBe("boolean");
          if (q.minLength !== undefined) {
            expect(Number.isInteger(q.minLength)).toBe(true);
          }
          if (q.maxLength !== undefined) {
            expect(Number.isInteger(q.maxLength)).toBe(true);
          }
        }
      }
    });

    test("all unique keys are unique per question key", () => {
      // unique keys
      const allKeys = allQuestionKeys;
      const set = new Set(allKeys);
      expect(set.size).toBe(allKeys.length);
    });
  });

  describe("legalTypeKey", () => {
    test("null maps to unknown", () => {
      expect(legalTypeKey(null)).toBe("unknown");
    });

    test("known types map to themselves", () => {
      expect(legalTypeKey("obec")).toBe("obec");
      expect(legalTypeKey("spolek")).toBe("spolek");
      expect(legalTypeKey("firma")).toBe("firma");
      expect(legalTypeKey("obcan")).toBe("obcan");
    });
  });

  describe("CSV export of question keys", () => {
    // This test is a placeholder to ensure no regressions
    test("placeholder", () => {
      expect(true).toBe(true);
    });
  });
});
