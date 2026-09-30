import { describe, expect, it } from "vitest";

import {
  APPLICANT_PROFILE_SCHEMA_VERSION,
  APPLICANT_PROFILE_STORAGE_KEY,
  createApplicantProfile,
  createApplicantProfileFromAresResolution,
  createMinimalIndividualProfile,
  isApplicantProfile,
  isFieldSource,
  LocalApplicantProfileStore,
  type ApplicantProfile,
  type ApplicantProfileType,
  type FieldSource,
  type ProfileStorage,
} from "./applicantProfile";

// ---------------------------------------------------------------------------
// In-memory storage for tests (same pattern as LocalRelevanceFeedbackStore)
// ---------------------------------------------------------------------------

class MemoryStorage implements ProfileStorage {
  private readonly store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
}

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const NOW = "2026-09-25T12:00:00Z";
const ARES_SOURCE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/12345678";

function makeAresFields(overrides?: Partial<FieldSource>): FieldSource {
  return {
    sourceKind: "ARES",
    sourceReference: ARES_SOURCE,
    observedAt: NOW,
    verifiedAt: NOW,
    verificationStatus: "VERIFIED",
    evidenceId: null,
    ...overrides,
  };
}

/** A minimal valid profile (UNKNOWN type, no IČO, no sensitive fields).
 *
 *  Overrides use a permissive Record so tests can construct intentionally
 *  invalid profiles (wrong schemaVersion, bad shapes) without fighting the
 *  strict ApplicantProfile type — the helper is test-only, not a public API.
 */
function minimalProfile(
  overrides: Record<string, unknown> = {},
): ApplicantProfile {
  const now = NOW;
  const base: ApplicantProfile = {
    schemaVersion: APPLICANT_PROFILE_SCHEMA_VERSION,
    id: "test-profile-1",
    applicantType: "UNKNOWN",
    applicantTypeId: null,
    ico: null,
    organisationName: null,
    legalFormCode: null,
    municipalityCode: null,
    municipalityName: null,
    regionCode: null,
    seatGeographyId: null,
    municipalityPopulation: null,
    municipalityPopulationAsOf: null,
    vatStatus: null,
    organisationSize: null,
    publicPrivateStatus: null,
    nonprofitStatus: null,
    czNaceCodes: [],
    fieldSources: {},
    createdAt: now,
    updatedAt: now,
  };
  return { ...base, ...overrides } as ApplicantProfile;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("applicant profile types", () => {
  it("recognises a minimal valid profile", () => {
    expect(
      isApplicantProfile(
        minimalProfile(),
      ),
    ).toBe(true);
  });

  it("rejects a profile whose schemaVersion is unknown", () => {
    expect(
      isApplicantProfile(
        minimalProfile({ schemaVersion: "0.0.1" }),
      ),
    ).toBe(false);
  });

  it("rejects a profile with an invalid IČO", () => {
    expect(
      isApplicantProfile(
        minimalProfile({ ico: "123" }),
      ),
    ).toBe(false);
  });

  it("rejects a profile with a non-unique czNaceCodes entry", () => {
    expect(
      isApplicantProfile(
        minimalProfile({
          czNaceCodes: ["93.12", "93.12"],
        }),
      ),
    ).toBe(false);
  });

  it("rejects a profile with an unknown applicantType", () => {
    expect(
      isApplicantProfile(
        minimalProfile({ applicantType: "NOT_A_REAL_TYPE" as ApplicantProfileType }),
      ),
    ).toBe(false);
  });

  it("accepts UNKNOWN applicantType explicitly", () => {
    expect(
      isApplicantProfile(
        minimalProfile({ applicantType: "UNKNOWN" }),
      ),
    ).toBe(true);
  });

  it("recognises a valid ARES field source", () => {
    expect(
      isFieldSource(
        makeAresFields(),
      ),
    ).toBe(true);
  });

  it("rejects a field source with an unknown sourceKind", () => {
    expect(
      isFieldSource({
        sourceKind: "FAKE_SOURCE_KIND",
        sourceReference: null,
        observedAt: NOW,
        verifiedAt: null,
        verificationStatus: "VERIFIED",
        evidenceId: null,
      }),
    ).toBe(false);
  });

  it("rejects a field source with an unknown verificationStatus", () => {
    expect(
      isFieldSource({
        sourceKind: "ARES",
        sourceReference: null,
        observedAt: NOW,
        verifiedAt: null,
        verificationStatus: "NOT_REAL",
        evidenceId: null,
      }),
    ).toBe(false);
  });
});

describe("applicant profile creation helpers", () => {
  it("createApplicantProfile produces a valid profile", () => {
    const profile = createApplicantProfile({
      id: "helper-test",
      applicantType: "NONPROFIT",
      ico: "12345678",
      organisationName: "Test organisace",
      legalFormCode: "706",
      municipalityCode: "123456",
      municipalityName: "Testov",
      czNaceCodes: ["93.12"],
      fieldSources: {
        ico: makeAresFields(),
      },
    });
    expect(isApplicantProfile(profile)).toBe(true);
    expect(profile.applicantType).toBe("NONPROFIT");
    expect(profile.ico).toBe("12345678");
    expect(profile.czNaceCodes).toEqual(["93.12"]);
  });

  it("createApplicantProfile fills missing nullable fields with null", () => {
    const profile = createApplicantProfile({
      id: "helper-test-2",
      applicantType: "UNKNOWN",
    });
    expect(profile.organisationName).toBeNull();
    expect(profile.legalFormCode).toBeNull();
    expect(profile.municipalityCode).toBeNull();
    expect(profile.czNaceCodes).toEqual([]);
    expect(profile.fieldSources).toEqual({});
  });

  it("createApplicantProfileFromAresResolution marks IČO as ARES-resolved", () => {
    const profile = createApplicantProfileFromAresResolution({
      id: "ares-test",
      ico: "12345678",
      organisationName: "Testovací organizace",
      legalFormCode: "706",
      municipalityCode: "123456",
      municipalityName: "Testov",
      czNaceCodes: ["93.12"],
      sourceReference: ARES_SOURCE,
      observedAt: NOW,
    });
    expect(isApplicantProfile(profile)).toBe(true);
    expect(profile.applicantType).toBe("UNKNOWN");
    expect(profile.ico).toBe("12345678");
    expect(profile.fieldSources.ico).toBeTruthy();
    expect(profile.fieldSources.ico?.sourceKind).toBe("ARES");
    expect(profile.fieldSources.ico?.sourceReference).toBe(ARES_SOURCE);
    expect(profile.fieldSources.ico?.observedAt).toBe(NOW);
    expect(profile.fieldSources.ico?.verificationStatus).toBe("VERIFIED");
  });

  it("createMinimalIndividualProfile contains no personal identifying attributes", () => {
    const profile = createMinimalIndividualProfile({
      id: "individual-test",
      municipalityCode: "123456",
      municipalityName: "Testov",
      municipalityPopulation: 3200,
      municipalityPopulationAsOf: "2026-01-01",
      sourceReference: "https://example.test/user-input",
      observedAt: NOW,
    });
    expect(isApplicantProfile(profile)).toBe(true);
    expect(profile.ico).toBeNull();
    expect(profile.organisationName).toBeNull();
    expect(profile.legalFormCode).toBeNull();
    expect(profile.applicantType).toBe("UNKNOWN");
    // Only municipality fields are present, no personal data.
    expect(profile.municipalityCode).toBe("123456");
    expect(profile.municipalityName).toBe("Testov");
    expect(profile.municipalityPopulation).toBe(3200);
    expect(profile.municipalityPopulationAsOf).toBe("2026-01-01");
    expect(profile.fieldSources.municipalityCode).toBeTruthy();
    expect(profile.fieldSources.municipalityCode?.sourceKind).toBe("USER");
  });

  it("createMinimalIndividualProfile with no input is still a valid empty profile", () => {
    const profile = createMinimalIndividualProfile({ id: "empty-individual" });
    expect(isApplicantProfile(profile)).toBe(true);
    expect(profile.ico).toBeNull();
    expect(profile.municipalityCode).toBeNull();
    expect(profile.fieldSources).toEqual({});
  });
});

describe("LocalApplicantProfileStore", () => {
  it("returns null when no profile is stored", () => {
    const store = new LocalApplicantProfileStore(new MemoryStorage());
    expect(store.get()).toBeNull();
    expect(store.has()).toBe(false);
  });

  it("saves and retrieves a profile", () => {
    const storage = new MemoryStorage();
    const store = new LocalApplicantProfileStore(storage);
    const profile = minimalProfile();

    store.save(profile);
    expect(store.has()).toBe(true);

    const retrieved = store.get();
    expect(retrieved).not.toBeNull();
    expect(retrieved?.id).toBe("test-profile-1");
    expect(retrieved?.applicantType).toBe("UNKNOWN");
    expect(retrieved?.ico).toBeNull();
  });

  it("persists the profile to the underlying storage", () => {
    const storage = new MemoryStorage();
    const store = new LocalApplicantProfileStore(storage);
    const profile = minimalProfile({ id: "persist-test" });

    store.save(profile);

    expect(storage.getItem(APPLICANT_PROFILE_STORAGE_KEY)).not.toBeNull();
    const raw = JSON.parse(storage.getItem(APPLICANT_PROFILE_STORAGE_KEY)!);
    expect(raw.schemaVersion).toBe(APPLICANT_PROFILE_SCHEMA_VERSION);
    expect(raw.id).toBe("persist-test");
  });

  it("updates updatedAt on save", () => {
    const storage = new MemoryStorage();
    const store = new LocalApplicantProfileStore(storage);
    const profile = minimalProfile({ createdAt: "2026-09-20T00:00:00Z", updatedAt: "2026-09-20T00:00:00Z" });

    store.save(profile);
    const retrieved = store.get()!;
    expect(retrieved.updatedAt).not.toBe("2026-09-20T00:00:00Z");
    expect(Date.parse(retrieved.updatedAt)).toBeGreaterThan(Date.parse("2026-09-20T00:00:00Z"));
    expect(retrieved.createdAt).toBe("2026-09-20T00:00:00Z");
  });

  it("clears the stored profile", () => {
    const storage = new MemoryStorage();
    const store = new LocalApplicantProfileStore(storage);
    store.save(minimalProfile());

    store.clear();
    expect(store.get()).toBeNull();
    expect(store.has()).toBe(false);
    expect(storage.getItem(APPLICANT_PROFILE_STORAGE_KEY)).toBeNull();
  });

  it("export produces a valid JSON string of the current profile", () => {
    const store = new LocalApplicantProfileStore(new MemoryStorage());
    store.save(minimalProfile({ id: "export-test" }));

    const exported = store.export();
    expect(exported).toContain(`"id": "export-test"`);
    expect(exported).toContain(`"schemaVersion": "${APPLICANT_PROFILE_SCHEMA_VERSION}"`);

    // The exported JSON round-trips through isApplicantProfile.
    expect(isApplicantProfile(JSON.parse(exported))).toBe(true);
  });

  it("export throws when no profile is stored", () => {
    const store = new LocalApplicantProfileStore(new MemoryStorage());
    expect(() => store.export()).toThrowError(
      /No applicant profile is stored locally/,
    );
  });

  it("import restores a previously-exported profile", () => {
    const store = new LocalApplicantProfileStore(new MemoryStorage());
    store.save(minimalProfile({ id: "import-source" }));
    const exported = store.export();

    const otherStore = new LocalApplicantProfileStore(new MemoryStorage());
    const restored = otherStore.import(exported);
    expect(restored).not.toBeNull();
    expect(restored?.id).toBe("import-source");
    expect(otherStore.has()).toBe(true);
  });

  it("import returns null for malformed JSON", () => {
    const store = new LocalApplicantProfileStore(new MemoryStorage());
    expect(store.import("not json {{{")).toBeNull();
    expect(store.has()).toBe(false);
  });

  it("import returns null for a profile with an unknown schemaVersion", () => {
    const store = new LocalApplicantProfileStore(new MemoryStorage());
    const badProfile = JSON.stringify({
      schemaVersion: "0.0.1",
      id: "bad-version",
      applicantType: "UNKNOWN",
      applicantTypeId: null,
      ico: null,
      organisationName: null,
      legalFormCode: null,
      municipalityCode: null,
      municipalityName: null,
      regionCode: null,
      seatGeographyId: null,
      municipalityPopulation: null,
      municipalityPopulationAsOf: null,
      vatStatus: null,
      organisationSize: null,
      publicPrivateStatus: null,
      nonprofitStatus: null,
      czNaceCodes: [],
      fieldSources: {},
      createdAt: NOW,
      updatedAt: NOW,
    });
    expect(store.import(badProfile)).toBeNull();
    expect(store.has()).toBe(false);
  });

  it("import returns null for a bare profile wrapped in an object", () => {
    const innerStore = new LocalApplicantProfileStore(new MemoryStorage());
    innerStore.save(minimalProfile({ id: "wrapped" }));
    const exported = innerStore.export();

    // Simulate a wrapped format: { profile: <exported> }
    const wrapped = JSON.stringify({ profile: JSON.parse(exported) });
    const store = new LocalApplicantProfileStore(new MemoryStorage());
    const restored = store.import(wrapped);
    expect(restored).not.toBeNull();
    expect(restored?.id).toBe("wrapped");
  });

  it("get returns null and clears storage for corrupted JSON", () => {
    const storage = new MemoryStorage();
    storage.setItem(APPLICANT_PROFILE_STORAGE_KEY, "not-valid-json{{{");
    const store = new LocalApplicantProfileStore(storage);

    expect(store.get()).toBeNull();
    expect(store.has()).toBe(false);
    expect(storage.getItem(APPLICANT_PROFILE_STORAGE_KEY)).toBeNull();
  });

  it("get returns null and clears storage for a profile that fails validation", () => {
    const storage = new MemoryStorage();
    storage.setItem(
      APPLICANT_PROFILE_STORAGE_KEY,
      JSON.stringify({
        schemaVersion: APPLICANT_PROFILE_SCHEMA_VERSION,
        id: "bad-shape",
        applicantType: "UNKNOWN",
        applicantTypeId: null,
        ico: null,
        organisationName: null,
        legalFormCode: null,
        municipalityCode: null,
        municipalityName: null,
        regionCode: null,
        seatGeographyId: null,
        municipalityPopulation: -1, // invalid: negative population
        municipalityPopulationAsOf: null,
        vatStatus: null,
        organisationSize: null,
        publicPrivateStatus: null,
        nonprofitStatus: null,
        czNaceCodes: [],
        fieldSources: {},
        createdAt: NOW,
        updatedAt: NOW,
      }),
    );
    const store = new LocalApplicantProfileStore(storage);

    expect(store.get()).toBeNull();
    expect(store.has()).toBe(false);
    expect(storage.getItem(APPLICANT_PROFILE_STORAGE_KEY)).toBeNull();
  });

  it("save throws InvalidProfileError for an invalid IČO", () => {
    const store = new LocalApplicantProfileStore(new MemoryStorage());
    const badProfile = minimalProfile({ ico: "12345" });
    expect(() => store.save(badProfile)).toThrowError(
      /IČO must be exactly 8 digits/,
    );
    expect(store.has()).toBe(false);
  });

  it("save throws InvalidProfileError for an unknown applicantType", () => {
    const store = new LocalApplicantProfileStore(new MemoryStorage());
    const badProfile = minimalProfile({ applicantType: "FAKE_TYPE" as ApplicantProfileType });
    expect(() => store.save(badProfile)).toThrowError(/Unknown applicantType/);
  });

  it("save throws SchemaVersionMismatchError for a profile with a mismatched schemaVersion", () => {
    const store = new LocalApplicantProfileStore(new MemoryStorage());
    const badProfile = minimalProfile({ schemaVersion: "2.0.0" }) as unknown as ApplicantProfile;
    expect(() => store.save(badProfile)).toThrowError(
      /SCHEMA_VERSION_MISMATCH/,
    );
  });

  it("preserves ARES provenance on save and retrieve", () => {
    const storage = new MemoryStorage();
    const store = new LocalApplicantProfileStore(storage);
    const profile = createApplicantProfileFromAresResolution({
      id: "provenance-test",
      ico: "12345678",
      organisationName: "Testovací organizace",
      legalFormCode: "706",
      municipalityCode: "123456",
      municipalityName: "Testov",
      czNaceCodes: ["93.12"],
      sourceReference: ARES_SOURCE,
      observedAt: NOW,
    });

    store.save(profile);
    const retrieved = store.get()!;

    expect(retrieved.fieldSources.ico).toBeTruthy();
    expect(retrieved.fieldSources.ico?.sourceKind).toBe("ARES");
    expect(retrieved.fieldSources.ico?.sourceReference).toBe(ARES_SOURCE);
    expect(retrieved.fieldSources.ico?.observedAt).toBe(NOW);
    expect(retrieved.fieldSources.ico?.verificationStatus).toBe("VERIFIED");
  });

  it("deduplicates czNaceCodes on save", () => {
    const storage = new MemoryStorage();
    const store = new LocalApplicantProfileStore(storage);
    const profile = minimalProfile({
      czNaceCodes: ["93.12", "93.12", "94.99"],
    });

    store.save(profile);
    const retrieved = store.get()!;
    expect(retrieved.czNaceCodes).toEqual(["93.12", "94.99"]);
  });

  it("supports a custom storage key", () => {
    const storage = new MemoryStorage();
    const store = new LocalApplicantProfileStore(storage, "custom-key:test");

    store.save(minimalProfile({ id: "custom-key-test" }));
    expect(store.get()).not.toBeNull();
    expect(storage.getItem("custom-key:test")).not.toBeNull();
    expect(storage.getItem(APPLICANT_PROFILE_STORAGE_KEY)).toBeNull();
  });

  it("store exposes a stable storage key constant", () => {
    expect(APPLICANT_PROFILE_STORAGE_KEY).toContain(":v1");
    expect(APPLICANT_PROFILE_STORAGE_KEY).toMatch(/^dotacni-majak:applicant-profile:v\d+$/);
  });

  it("store exposes a stable schema version constant", () => {
    expect(APPLICANT_PROFILE_SCHEMA_VERSION).toBe("1.0.0");
  });
});
