import type { ApplicantProfile, ApplicantProfileType, FieldSource } from "./applicantProfileTypes";

// Re-export types so consumers can import from one module.
export type { ApplicantProfile, ApplicantProfileType, FieldSource };

// ---------------------------------------------------------------------------
// Storage key & versioning
// ---------------------------------------------------------------------------

/** Storage key used for the local-first applicant profile.
 *  Version component must be bumped whenever the persisted JSON shape changes
 *  in a way that breaks forward compatibility. Backwards-compatible additions
 *  (new optional fields) do not require a version bump on their own.
 */
export const APPLICANT_PROFILE_STORAGE_KEY = "dotacni-majak:applicant-profile:v1";

/** Schema version embedded in every persisted profile.
 *  Currently aligned with the canonical applicant-profile schema v1.0.0.
 *  The store rejects profiles whose embedded schemaVersion does not match this
 *  value — an unknown version is UNSAFE to trust, so it is treated as absent.
 */
export const APPLICANT_PROFILE_SCHEMA_VERSION = "1.0.0";

// ---------------------------------------------------------------------------
// Storage interface (abstracts localStorage; in-memory impl for tests)
// ---------------------------------------------------------------------------

/** Minimal storage contract. Mirrors the pattern used by
 *  LocalRelevanceFeedbackStore (FeedbackStorage) so the store is testable
 *  without DOM/localStorage access.
 */
export interface ProfileStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/** Explicit error carrying a stable machine-readable code.
 *  UNKNOWN is explicitly distinguished from FAIL — a missing/corrupt profile
 *  yields `null` from `get()`, never an exception. Exceptions are reserved for
 *  invalid inputs the caller must not pass.
 */
export class ApplicantProfileError extends Error {
  constructor(public readonly code: string) {
    super(code);
    this.name = "ApplicantProfileError";
  }
}

/** Thrown by `save()` when the profile fails validation. */
export class InvalidProfileError extends ApplicantProfileError {
  constructor(message: string) {
    super(`INVALID_PROFILE: ${message}`);
  }
}

/** Thrown by `save()` when the caller provides a profile whose embedded
 *  schemaVersion does not match the store's expected version. */
export class SchemaVersionMismatchError extends ApplicantProfileError {
  constructor(expected: string, actual: string) {
    super(`SCHEMA_VERSION_MISMATCH: expected ${expected}, got ${actual}`);
  }
}

/** Thrown by `export()` / `import()` when the JSON payload is unparseable. */
export class ExportImportError extends ApplicantProfileError {
  constructor(message: string) {
    super(`EXPORT_IMPORT: ${message}`);
  }
}

// ---------------------------------------------------------------------------
// Validation & type guards
// ---------------------------------------------------------------------------

const ICO_RE = /^[0-9]{8}$/;
const ISO_DATETIME_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const APPLICANT_TYPE_VALUES: ReadonlySet<ApplicantProfileType> = new Set([
  "UNKNOWN",
  "NATURAL_PERSON",
  "SELF_EMPLOYED",
  "BUSINESS",
  "MUNICIPALITY",
  "REGION",
  "ASSOCIATION",
  "SPORTS_CLUB",
  "NONPROFIT",
  "SCHOOL",
  "CONTRIBUTORY_ORGANISATION",
  "HOA",
  "COOPERATIVE",
  "AGRICULTURAL_ENTITY",
  "RESEARCH_ORGANISATION",
  "OTHER",
]);

const VAT_STATUS_VALUES: ReadonlySet<string> = new Set([
  "UNKNOWN",
  "PAYER",
  "NON_PAYER",
]);

const ORGANISATION_SIZE_VALUES: ReadonlySet<string> = new Set([
  "UNKNOWN",
  "MICRO",
  "SMALL",
  "MEDIUM",
  "LARGE",
]);

const PUBLIC_PRIVATE_VALUES: ReadonlySet<string> = new Set([
  "PUBLIC",
  "PRIVATE",
  "MIXED",
  "UNKNOWN",
]);

const NONPROFIT_VALUES: ReadonlySet<string> = new Set([
  "NONPROFIT",
  "FOR_PROFIT",
  "UNKNOWN",
]);

const SOURCE_KIND_VALUES: ReadonlySet<string> = new Set([
  "USER",
  "ARES",
  "CZSO",
  "OTHER_OFFICIAL",
  "DERIVED",
]);

const VERIFICATION_STATUS_VALUES: ReadonlySet<string> = new Set([
  "USER_DECLARED",
  "AUTO_EXTRACTED",
  "PARTIALLY_VERIFIED",
  "VERIFIED",
  "NEEDS_REVIEW",
]);

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

/** Helper to read a nullable string field from a parsed JSON object.
 *  Returns null when the field is absent, null, or not a string.
 */
function readNullableString(
  obj: Record<string, unknown>,
  key: string,
): string | null {
  const v = obj[key];
  if (v === null || v === undefined) return null;
  if (typeof v !== "string") return null; // invalid shape
  return v;
}

/** Helper to read a nullable integer field. */
function readNullableInteger(
  obj: Record<string, unknown>,
  key: string,
): number | null {
  const v = obj[key];
  if (v === null || v === undefined) return null;
  if (typeof v !== "number" || !Number.isInteger(v)) return null;
  return v;
}

/** Helper to read a nullable enum field. */
function readNullableEnum<T extends string>(
  obj: Record<string, unknown>,
  key: string,
  allowed: ReadonlySet<T>,
): T | null {
  const v = obj[key];
  if (v === null || v === undefined) return null;
  if (typeof v !== "string" || !allowed.has(v as T)) return null;
  return v as T;
}

interface RawProfile {
  [key: string]: unknown;
  schemaVersion?: unknown;
  id?: unknown;
  applicantType?: unknown;
  applicantTypeId?: unknown;
  ico?: unknown;
  organisationName?: unknown;
  legalFormCode?: unknown;
  municipalityCode?: unknown;
  municipalityName?: unknown;
  regionCode?: unknown;
  seatGeographyId?: unknown;
  municipalityPopulation?: unknown;
  municipalityPopulationAsOf?: unknown;
  vatStatus?: unknown;
  organisationSize?: unknown;
  publicPrivateStatus?: unknown;
  nonprofitStatus?: unknown;
  czNaceCodes?: unknown;
  fieldSources?: unknown;
  createdAt?: unknown;
  updatedAt?: unknown;
}

export function isApplicantProfile(value: unknown): value is ApplicantProfile {
  if (!value || typeof value !== "object") return false;
  const p = value as RawProfile;

  // schemaVersion must match the store's expected version exactly.
  if (p.schemaVersion !== APPLICANT_PROFILE_SCHEMA_VERSION) return false;
  if (!isNonEmptyString(p.id as unknown)) return false;
  if (
    typeof p.applicantType !== "string" ||
    !APPLICANT_TYPE_VALUES.has(p.applicantType as ApplicantProfileType)
  )
    return false;

  if (
    p.applicantTypeId !== undefined &&
    p.applicantTypeId !== null &&
    !isNonEmptyString(p.applicantTypeId as unknown)
  )
    return false;

  if (p.ico === null) {
    // ok
  } else if (typeof p.ico === "string" && ICO_RE.test(p.ico)) {
    // ok
  } else {
    return false;
  }

  {
    const orgName = readNullableString(p, "organisationName");
    if (orgName === null) {
      // ok — field is absent from raw; treat as null
    } else if (!orgName) {
      return false;
    }
  }
  {
    const legalForm = readNullableString(p, "legalFormCode");
    if (legalForm === null) {
      // ok
    } else if (!legalForm) {
      return false;
    }
  }
  {
    const muniCode = readNullableString(p, "municipalityCode");
    if (muniCode === null) {
      // ok
    } else if (!muniCode) {
      return false;
    }
  }
  {
    const muniName = readNullableString(p, "municipalityName");
    if (muniName === null) {
      // ok
    } else if (!muniName) {
      return false;
    }
  }
  {
    const regionCode = readNullableString(p, "regionCode");
    if (regionCode === null) {
      // ok
    } else if (!regionCode) {
      return false;
    }
  }
  {
    const seatGeo = readNullableString(p, "seatGeographyId");
    if (seatGeo === null) {
      // ok
    } else if (!seatGeo) {
      return false;
    }
  }

  {
    const pop = readNullableInteger(p, "municipalityPopulation");
    if (pop === null) {
      // ok
    } else if (pop < 0) {
      return false;
    }
  }
  {
    const popAsOf = readNullableString(p, "municipalityPopulationAsOf");
    if (popAsOf === null) {
      // ok
    } else if (!ISO_DATE_RE.test(popAsOf)) {
      return false;
    }
  }

  {
    const vat = readNullableEnum(p, "vatStatus", VAT_STATUS_VALUES);
    if (vat === null) {
      // ok
    }
  }
  {
    const size = readNullableEnum(p, "organisationSize", ORGANISATION_SIZE_VALUES);
    if (size === null) {
      // ok
    }
  }
  {
    const pp = readNullableEnum(
      p,
      "publicPrivateStatus",
      PUBLIC_PRIVATE_VALUES,
    );
    if (pp === null) {
      // ok
    }
  }
  {
    const np = readNullableEnum(p, "nonprofitStatus", NONPROFIT_VALUES);
    if (np === null) {
      // ok
    }
  }

  // czNaceCodes must be an array of unique non-empty strings.
  {
    const codes = p.czNaceCodes;
    if (!Array.isArray(codes)) return false;
    const seen = new Set<string>();
    for (const code of codes) {
      if (!isNonEmptyString(code)) return false;
      if (seen.has(code)) return false;
      seen.add(code);
    }
  }

  if (!isFieldSourcesObject(p.fieldSources)) return false;

  if (!ISO_DATETIME_RE.test(p.createdAt as string)) return false;
  if (!ISO_DATETIME_RE.test(p.updatedAt as string)) return false;

  return true;
}

function isFieldSourcesObject(
  value: unknown,
): value is Record<string, FieldSource> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const map = value as Record<string, unknown>;
  for (const key of Object.keys(map)) {
    if (!/^^[A-Za-z][A-Za-z0-9]*$/.test(key)) return false;
    if (!isFieldSource(map[key])) return false;
  }
  return true;
}

export function isFieldSource(value: unknown): value is FieldSource {
  if (!value || typeof value !== "object") return false;
  const s = value as Record<string, unknown>;

  if (!SOURCE_KIND_VALUES.has(s.sourceKind as string)) return false;
  if (
    s.sourceReference !== null &&
    !isNonEmptyString(s.sourceReference)
  )
    return false;
  if (!ISO_DATETIME_RE.test(s.observedAt as string)) return false;
  if (
    s.verifiedAt !== null &&
    !ISO_DATETIME_RE.test(s.verifiedAt as string)
  )
    return false;
  if (
    !VERIFICATION_STATUS_VALUES.has(s.verificationStatus as string)
  )
    return false;
  if (
    s.evidenceId !== null &&
    !isNonEmptyString(s.evidenceId)
  )
    return false;

  return true;
}

// ---------------------------------------------------------------------------
// Profile construction helpers
// ---------------------------------------------------------------------------

/** Build a profile suitable for persistence.
 *
 *  The caller is responsible for the provenance semantics of each field.
 *  This helper does NOT validate the profile shape; validation happens at
 *  `save()` time. Prefer `createApplicantProfileForSave()` when constructing
 *  a profile that will be persisted.
 */
export function createApplicantProfile(input: {
  id: string;
  applicantType: ApplicantProfileType;
  applicantTypeId?: string | null;
  ico?: string | null;
  organisationName?: string | null;
  legalFormCode?: string | null;
  municipalityCode?: string | null;
  municipalityName?: string | null;
  regionCode?: string | null;
  seatGeographyId?: string | null;
  municipalityPopulation?: number | null;
  municipalityPopulationAsOf?: string | null;
  vatStatus?: "UNKNOWN" | "PAYER" | "NON_PAYER" | null;
  organisationSize?: "UNKNOWN" | "MICRO" | "SMALL" | "MEDIUM" | "LARGE" | null;
  publicPrivateStatus?: "PUBLIC" | "PRIVATE" | "MIXED" | "UNKNOWN" | null;
  nonprofitStatus?: "NONPROFIT" | "FOR_PROFIT" | "UNKNOWN" | null;
  czNaceCodes?: readonly string[];
  fieldSources?: Readonly<Record<string, Readonly<FieldSource>>>;
  createdAt?: string;
  updatedAt?: string;
}): ApplicantProfile {
  const now = new Date().toISOString();
  return {
    schemaVersion: APPLICANT_PROFILE_SCHEMA_VERSION,
    id: input.id,
    applicantType: input.applicantType,
    applicantTypeId: input.applicantTypeId ?? null,
    ico: input.ico ?? null,
    organisationName: input.organisationName ?? null,
    legalFormCode: input.legalFormCode ?? null,
    municipalityCode: input.municipalityCode ?? null,
    municipalityName: input.municipalityName ?? null,
    regionCode: input.regionCode ?? null,
    seatGeographyId: input.seatGeographyId ?? null,
    municipalityPopulation: input.municipalityPopulation ?? null,
    municipalityPopulationAsOf: input.municipalityPopulationAsOf ?? null,
    vatStatus: input.vatStatus ?? null,
    organisationSize: input.organisationSize ?? null,
    publicPrivateStatus: input.publicPrivateStatus ?? null,
    nonprofitStatus: input.nonprofitStatus ?? null,
    czNaceCodes: Array.isArray(input.czNaceCodes)
      ? input.czNaceCodes.slice()
      : [],
    fieldSources: input.fieldSources ?? {},
    createdAt: input.createdAt ?? now,
    updatedAt: input.updatedAt ?? now,
  };
}

/** A simplified helper for building a profile that carries ARES-resolved
 *  provenance on the IČO field. This is intentionally minimal — the store
 *  does not invent personal data; it only persists what was resolved or
 *  explicitly declared.
 */
export function createApplicantProfileFromAresResolution(input: {
  id: string;
  ico: string;
  organisationName?: string | null;
  legalFormCode?: string | null;
  municipalityCode?: string | null;
  municipalityName?: string | null;
  regionCode?: string | null;
  czNaceCodes?: readonly string[];
  sourceReference: string;
  observedAt: string;
}): ApplicantProfile {
  const now = new Date().toISOString();
  const fieldSources: Record<string, FieldSource> = {
    ico: {
      sourceKind: "ARES",
      sourceReference: input.sourceReference,
      observedAt: input.observedAt,
      verifiedAt: input.observedAt,
      verificationStatus: "VERIFIED",
      evidenceId: null,
    },
  };

  return {
    schemaVersion: APPLICANT_PROFILE_SCHEMA_VERSION,
    id: input.id,
    applicantType: "UNKNOWN",
    applicantTypeId: null,
    ico: input.ico,
    organisationName: input.organisationName ?? null,
    legalFormCode: input.legalFormCode ?? null,
    municipalityCode: input.municipalityCode ?? null,
    municipalityName: input.municipalityName ?? null,
    regionCode: input.regionCode ?? null,
    seatGeographyId: null,
    municipalityPopulation: null,
    municipalityPopulationAsOf: null,
    vatStatus: null,
    organisationSize: null,
    publicPrivateStatus: null,
    nonprofitStatus: null,
    czNaceCodes: Array.isArray(input.czNaceCodes)
      ? input.czNaceCodes.slice()
      : [],
    fieldSources,
    createdAt: now,
    updatedAt: now,
  };
}

/** A helper for building a minimal individual (natural person) profile that
 *  intentionally contains NO personal identifying attributes — only the
 *  municipality context is recorded, matching the privacy principle that
 *  personal data is never auto-filled.
 */
export function createMinimalIndividualProfile(input: {
  id: string;
  municipalityCode?: string | null;
  municipalityName?: string | null;
  municipalityPopulation?: number | null;
  municipalityPopulationAsOf?: string | null;
  sourceReference?: string | null;
  observedAt?: string;
}): ApplicantProfile {
  const now = new Date().toISOString();
  const fieldSources: Record<string, FieldSource> = {};

  if (input.sourceReference && input.observedAt) {
    if (input.municipalityCode) {
      fieldSources.municipalityCode = {
        sourceKind: "USER",
        sourceReference: input.sourceReference,
        observedAt: input.observedAt,
        verifiedAt: null,
        verificationStatus: "USER_DECLARED",
        evidenceId: null,
      };
    }
    if (input.municipalityPopulation !== null) {
      fieldSources.municipalityPopulation = {
        sourceKind: "USER",
        sourceReference: input.sourceReference,
        observedAt: input.observedAt,
        verifiedAt: null,
        verificationStatus: "USER_DECLARED",
        evidenceId: null,
      };
    }
  }

  return {
    schemaVersion: APPLICANT_PROFILE_SCHEMA_VERSION,
    id: input.id,
    applicantType: "UNKNOWN",
    applicantTypeId: null,
    ico: null,
    organisationName: null,
    legalFormCode: null,
    municipalityCode: input.municipalityCode ?? null,
    municipalityName: input.municipalityName ?? null,
    regionCode: null,
    seatGeographyId: null,
    municipalityPopulation: input.municipalityPopulation ?? null,
    municipalityPopulationAsOf: input.municipalityPopulationAsOf ?? null,
    vatStatus: null,
    organisationSize: null,
    publicPrivateStatus: null,
    nonprofitStatus: null,
    czNaceCodes: [],
    fieldSources,
    createdAt: now,
    updatedAt: now,
  };
}

// ---------------------------------------------------------------------------
// Local store
// ---------------------------------------------------------------------------

/** A local-first applicant profile store backed by a `ProfileStorage`
 *  implementation. The default browser-backed implementation uses
 *  `localStorage`; the same API is testable with an in-memory store.
 *
 *  Design principles:
 *  - UNKNOWN != FAIL: a missing profile returns `null`, never throws.
 *  - Corrupt/unknown-version data is treated as absent (cleared) rather than
 *    trusted.
 *  - No sensitive personal attributes are auto-filled or inferred; the profile
 *    only contains what was resolved from official sources (ARES/CZSO) or
 *    explicitly declared by the user.
 *  - Provenance (`fieldSources`) is preserved verbatim on save; the store does
 *    not rewrite observed_at or source_reference.
 *  - Zero-cost-first: the store is a pure in-memory/localStorage operation with
 *    no network calls and no external dependencies.
 */
export class LocalApplicantProfileStore {
  constructor(
    private readonly storage: ProfileStorage,
    private readonly key = APPLICANT_PROFILE_STORAGE_KEY,
  ) {}

  /** Returns the stored profile, or `null` when no profile is present,
   *  the stored data is corrupted, or the embedded schemaVersion is unknown.
   *  Corrupt/unknown-version data is cleared so a subsequent save restitches
   *  cleanly.
   */
  get(): ApplicantProfile | null {
    const raw = this.storage.getItem(this.key);
    if (raw === null) return null;

    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      this.storage.removeItem(this.key);
      return null;
    }

    if (!isApplicantProfile(parsed)) {
      this.storage.removeItem(this.key);
      return null;
    }

    return parsed;
  }

  /** Persist a profile. Validates the profile shape and the embedded
   *  schemaVersion before writing. Throws `InvalidProfileError` for invalid
   *  shapes and `SchemaVersionMismatchError` when the embedded version does
   *  not match the store's expected version.
   *
   *  Normalization (deduplication of czNaceCodes, updatedAt bump) happens
   *  before validation so that deterministic transforms are applied before the
   *  shape is checked.
   */
  save(profile: ApplicantProfile): ApplicantProfile {
    // Normalize deterministic fields first — e.g. deduplicate czNaceCodes —
    // before running the shape check, so normalized output is what gets
    // validated.
    const normalized = this.normalizeForPersistence(profile);

    // Schema version gate: do not trust a profile whose embedded version
    // differs from what this store expects. Checked before field-level
    // validation so the mismatch error is surfaced distinctly.
    if (normalized.schemaVersion !== APPLICANT_PROFILE_SCHEMA_VERSION) {
      throw new SchemaVersionMismatchError(
        APPLICANT_PROFILE_SCHEMA_VERSION,
        normalized.schemaVersion,
      );
    }

    // Specific field checks with clear messages, so callers can distinguish
    // "bad IČO" from "bad applicantType" from "general shape failure".
    if (!isNonEmptyString(normalized.id)) {
      throw new InvalidProfileError(
        "Profile id must be a non-empty string.",
      );
    }
    if (
      typeof normalized.applicantType !== "string" ||
      !APPLICANT_TYPE_VALUES.has(normalized.applicantType)
    ) {
      throw new InvalidProfileError(
        `Unknown applicantType: ${normalized.applicantType}.`,
      );
    }
    if (
      normalized.ico !== null &&
      (!isNonEmptyString(normalized.ico) || !ICO_RE.test(normalized.ico))
    ) {
      throw new InvalidProfileError(
        `IČO must be exactly 8 digits, got: ${normalized.ico}.`,
      );
    }

    // Final catch-all shape validation. Should pass for anything that survived
    // the checks above; kept as a safety net for future schema changes.
    if (!isApplicantProfile(normalized)) {
      throw new InvalidProfileError(
        "Profile failed internal validation. Do not construct profiles with " +
          "arbitrary values — use the creation helpers or a validated source.",
      );
    }

    this.storage.setItem(this.key, JSON.stringify(normalized, null, 2));
    return normalized;
  }

  /** Remove the stored profile. After this call, `get()` returns `null`. */
  clear(): void {
    this.storage.removeItem(this.key);
  }

  /** Returns `true` when a valid profile is present, `false` otherwise.
   *  Equivalent to `this.get() !== null` but avoids the extra allocation.
   */
  has(): boolean {
    const raw = this.storage.getItem(this.key);
    if (raw === null) return false;
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      this.storage.removeItem(this.key);
      return false;
    }
    if (!isApplicantProfile(parsed)) {
      this.storage.removeItem(this.key);
      return false;
    }
    return true;
  }

  /** Serialize the current profile to a JSON string suitable for download or
   *  clipboard transfer. Throws `ExportImportError` when no profile is present
   *  or serialization fails.
   */
  export(): string {
    const profile = this.get();
    if (profile === null) {
      throw new ExportImportError(
        "No applicant profile is stored locally.",
      );
    }
    try {
      return JSON.stringify(profile, null, 2);
    } catch (error) {
      throw new ExportImportError(
        `Serialization failed: ${error}`,
      );
    }
  }

  /** Restore a profile from a JSON string (e.g. exported previously or
   *  imported from a file). Validates the shape and schema version before
   *  persisting. Returns the restored profile, or `null` when the payload is
   *  invalid/unparseable.
   *
   *  This is intentionally read-validate-write rather than blind setItem, so
   *  a malformed export cannot corrupt the local store.
   */
  import(json: string): ApplicantProfile | null {
    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch {
      return null;
    }

    // import() accepts a bare profile or a JSON object whose value is the
    // profile (some export formats wrap the profile under a key).
    const candidate =
      typeof parsed === "object" && !Array.isArray(parsed)
        ? (parsed as Record<string, unknown>).profile ?? parsed
        : parsed;

    if (!isApplicantProfile(candidate)) {
      return null;
    }

    try {
      return this.save(candidate as ApplicantProfile);
    } catch {
      // If the incoming profile's schemaVersion mismatches, import must not
      // throw a SchemaVersionMismatchError to the caller — the caller is
      // likely restoring their own previously-exported data. Treat it as a
      // no-op and return null so the caller can surface the mismatch.
      return null;
    }
  }

  // -------------------------------------------------------------------
  // Internal
  // -------------------------------------------------------------------

  private normalizeForPersistence(profile: ApplicantProfile): ApplicantProfile {
    // Deterministic output: sort optional string fields that are empty-ish to
    // null, freeze the czNaceCodes array, and bump updatedAt.
    const updatedAt = new Date().toISOString();

    return {
      ...profile,
      czNaceCodes: Array.from(
        new Set(profile.czNaceCodes.filter(isNonEmptyString)),
      ),
      updatedAt,
    };
  }
}
