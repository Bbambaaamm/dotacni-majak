import type { Env } from "./env";
import {
  ApiInputError,
  hashOwnerToken,
} from "./projectAccess";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TOKEN_RE = /^[A-Za-z0-9_-]{40,128}$/;
const ICO_RE = /^[0-9]{8}$/;
const MAX_BODY_BYTES = 16 * 1024;

const APPLICANT_TYPES = new Set([
  "UNKNOWN", "NATURAL_PERSON", "SELF_EMPLOYED", "BUSINESS", "MUNICIPALITY",
  "REGION", "ASSOCIATION", "SPORTS_CLUB", "NONPROFIT", "SCHOOL",
  "CONTRIBUTORY_ORGANISATION", "HOA", "COOPERATIVE", "AGRICULTURAL_ENTITY",
  "RESEARCH_ORGANISATION", "OTHER",
]);

const MAX_STRING_LENGTH = 200;
const MAX_CZNACE_CODES = 50;

// ---------------------------------------------------------------------------
// Input / response types
// ---------------------------------------------------------------------------

/** Client-upsertable profile payload. All fields optional except applicantType
 *  is required to be a known enum string; unknown/error values are preserved
 *  explicitly rather than silently coerced.
 */
export interface ApplicantProfileInput {
  applicantType: string;
  ico: string | null;
  organisationName: string | null;
  legalFormCode: string | null;
  municipalityCode: string | null;
  municipalityName: string | null;
  regionCode: string | null;
  municipalityPopulation: number | null;
  municipalityPopulationAsOf: string | null;
  vatStatus: string | null;
  organisationSize: string | null;
  publicPrivateStatus: string | null;
  nonprofitStatus: string | null;
  czNaceCodes: readonly string[];
  fieldSources: Record<string, unknown>;
}

/** Server-returned profile with derived provenance timestamp.
 *  No raw token, user_id, or internal IDs are leaked.
 */
export interface ApplicantProfileResponse {
  id: string;
  applicantType: string;
  ico: string | null;
  organisationName: string | null;
  legalFormCode: string | null;
  municipalityCode: string | null;
  municipalityName: string | null;
  regionCode: string | null;
  municipalityPopulation: number | null;
  municipalityPopulationAsOf: string | null;
  vatStatus: string | null;
  organisationSize: string | null;
  publicPrivateStatus: string | null;
  nonprofitStatus: string | null;
  czNaceCodes: readonly string[];
  /** Latest observedAt across official field_sources entries.
   *  null when no public-source facts have been recorded yet.
   *  This is the ARES/ČSÚ refresh timestamp the client uses to
   *  decide whether a resolver refresh is stale.
   */
  lastResolvedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

/** Internal row shape returned by D1 SELECT. */
interface ProfileRow {
  id: string;
  applicant_type: string;
  ico: string | null;
  organisation_name: string | null;
  legal_form_code: string | null;
  municipality_code: string | null;
  municipality_name: string | null;
  region_code: string | null;
  municipality_population: number | null;
  municipality_population_as_of: string | null;
  vat_status: string | null;
  organisation_size: string | null;
  public_private_status: string | null;
  nonprofit_status: string | null;
  cz_nace_json: string | null;
  field_sources_json: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Authorization
// ---------------------------------------------------------------------------

/** Validate the raw owner capability token format (without hitting the DB).
 *  Matches the pattern used by projectAccess.watchAccess.
 */
export function assertOwnerTokenFormat(token: string): void {
  if (!TOKEN_RE.test(token)) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }
}

/** Resolve a live project capability to its stable owner principal. */
export async function ownerUserId(
  ownerToken: string,
  env: Env,
): Promise<string> {
  assertOwnerTokenFormat(ownerToken);
  const hash = await hashOwnerToken(ownerToken);
  const row = await env.DB.prepare(
    `SELECT p.owner_user_id FROM project_owner_capabilities AS c
     JOIN projects AS p ON p.id = c.project_id
     WHERE c.token_hash = ? AND c.revoked_at IS NULL
       AND p.owner_user_id IS NOT NULL LIMIT 1`,
  ).bind(hash).first<{ owner_user_id: string }>();
  if (!row) throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  return row.owner_user_id;
}

// ---------------------------------------------------------------------------
// Input parsing & validation
// ---------------------------------------------------------------------------

export async function parseApplicantProfileInput(
  request: Request,
): Promise<ApplicantProfileInput> {
  const declared = request.headers.get("content-length");
  if (declared && Number(declared) > MAX_BODY_BYTES) {
    throw new ApiInputError("REQUEST_TOO_LARGE", 413);
  }
  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > MAX_BODY_BYTES) {
    throw new ApiInputError("REQUEST_TOO_LARGE", 413);
  }
  if (!text.trim()) {
    throw new ApiInputError("EMPTY_BODY");
  }

  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw new ApiInputError("INVALID_JSON");
  }

  const profile = validateInputShape(body);
  validateFieldValues(profile);
  return profile;
}

function validateInputShape(body: unknown): ApplicantProfileInput {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new ApiInputError("INVALID_PROFILE_INPUT");
  }
  const value = body as Record<string, unknown>;

  const applicantType = value.applicantType;
  if (typeof applicantType !== "string" || !APPLICANT_TYPES.has(applicantType)) {
    throw new ApiInputError("INVALID_APPLICANT_TYPE");
  }

  return {
    applicantType,
    ico: nullableString(value.ico),
    organisationName: nullableString(value.organisationName),
    legalFormCode: nullableString(value.legalFormCode),
    municipalityCode: nullableString(value.municipalityCode),
    municipalityName: nullableString(value.municipalityName),
    regionCode: nullableString(value.regionCode),
    municipalityPopulation: nullableInteger(value.municipalityPopulation),
    municipalityPopulationAsOf: nullableString(value.municipalityPopulationAsOf),
    vatStatus: nullableString(value.vatStatus),
    organisationSize: nullableString(value.organisationSize),
    publicPrivateStatus: nullableString(value.publicPrivateStatus),
    nonprofitStatus: nullableString(value.nonprofitStatus),
    czNaceCodes: validateCzNaceCodes(value.czNaceCodes),
    fieldSources: validateFieldSources(value.fieldSources),
  };
}

function nullableString(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") {
    throw new ApiInputError("INVALID_STRING_FIELD");
  }
  const trimmed = value.trim();
  if (trimmed.length === 0) return null;
  if (trimmed.length > MAX_STRING_LENGTH) {
    throw new ApiInputError("FIELD_TOO_LONG", 413);
  }
  return trimmed;
}

function nullableInteger(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value)) {
    throw new ApiInputError("INVALID_INTEGER_FIELD");
  }
  if (value < 0) {
    throw new ApiInputError("INVALID_INTEGER_FIELD");
  }
  return value;
}

function validateCzNaceCodes(value: unknown): readonly string[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) {
    throw new ApiInputError("INVALID_CZNACE_CODES");
  }
  if (value.length > MAX_CZNACE_CODES) {
    throw new ApiInputError("CZNACE_CODES_TOO_MANY", 413);
  }
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") {
      throw new ApiInputError("INVALID_CZNACE_CODE");
    }
    const trimmed = item.trim();
    if (!trimmed) {
      throw new ApiInputError("INVALID_CZNACE_CODE");
    }
    if (seen.has(trimmed)) {
      throw new ApiInputError("DUPLICATE_CZNACE_CODE");
    }
    seen.add(trimmed);
    result.push(trimmed);
  }
  return Object.freeze(result);
}

function validateFieldSources(value: unknown): Record<string, unknown> {
  if (value === undefined || value === null) return {};
  if (typeof value !== "object" || Array.isArray(value)) {
    throw new ApiInputError("INVALID_FIELD_SOURCES");
  }
  const map = value as Record<string, unknown>;
  for (const key of Object.keys(map)) {
    if (!/^[A-Za-z][A-Za-z0-9]*$/.test(key)) {
      throw new ApiInputError("INVALID_FIELD_SOURCE_KEY");
    }
    const source = map[key];
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new ApiInputError("INVALID_FIELD_SOURCE");
    }
    const s = source as Record<string, unknown>;
    if (Object.keys(s).some((field) => ![
      "sourceKind", "sourceReference", "observedAt", "verifiedAt",
      "verificationStatus", "evidenceId",
    ].includes(field))) throw new ApiInputError("INVALID_FIELD_SOURCE");
    if (
      typeof s.sourceKind !== "string" ||
      !["USER", "ARES", "CZSO", "OTHER_OFFICIAL", "DERIVED"].includes(s.sourceKind)
    ) {
      throw new ApiInputError("INVALID_SOURCE_KIND");
    }
    if (
      s.sourceReference !== undefined && s.sourceReference !== null &&
      typeof s.sourceReference !== "string"
    ) {
      throw new ApiInputError("INVALID_SOURCE_REFERENCE");
    }
    if (!isDateTime(s.observedAt)) {
      throw new ApiInputError("INVALID_OBSERVED_AT");
    }
    if (s.verifiedAt !== undefined && s.verifiedAt !== null && !isDateTime(s.verifiedAt)) {
      throw new ApiInputError("INVALID_VERIFIED_AT");
    }
    if (!["USER_DECLARED", "AUTO_EXTRACTED", "PARTIALLY_VERIFIED", "VERIFIED", "NEEDS_REVIEW"].includes(s.verificationStatus as string)) {
      throw new ApiInputError("INVALID_VERIFICATION_STATUS");
    }
    if (s.evidenceId !== undefined && s.evidenceId !== null &&
      (typeof s.evidenceId !== "string" || s.evidenceId.length === 0)) {
      throw new ApiInputError("INVALID_EVIDENCE_ID");
    }
  }
  return map;
}

function isDateTime(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return false;
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return false;
  const parts = /^\d{4}-\d{2}-\d{2}/.exec(value);
  const date = parts?.[0];
  return date !== undefined && validCalendarDate(date) &&
    Number(value.slice(11, 13)) <= 23 && Number(value.slice(14, 16)) <= 59 &&
    Number(value.slice(17, 19)) <= 59;
}

function validCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value + "T00:00:00Z");
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

/** Semantic validation of cross-field / pattern constraints. */
function validateFieldValues(profile: ApplicantProfileInput): void {
  if (profile.ico !== null && !ICO_RE.test(profile.ico)) {
    throw new ApiInputError("INVALID_ICO");
  }
  if (
    profile.municipalityPopulationAsOf !== null &&
    !validCalendarDate(profile.municipalityPopulationAsOf)
  ) {
    throw new ApiInputError("INVALID_POPULATION_AS_OF");
  }
  if (
    profile.vatStatus !== null &&
    !["UNKNOWN", "PAYER", "NON_PAYER"].includes(profile.vatStatus)
  ) {
    throw new ApiInputError("INVALID_VAT_STATUS");
  }
  if (
    profile.organisationSize !== null &&
    !["UNKNOWN", "MICRO", "SMALL", "MEDIUM", "LARGE"].includes(profile.organisationSize)
  ) {
    throw new ApiInputError("INVALID_ORGANISATION_SIZE");
  }
  if (
    profile.publicPrivateStatus !== null &&
    !["PUBLIC", "PRIVATE", "MIXED", "UNKNOWN"].includes(profile.publicPrivateStatus)
  ) {
    throw new ApiInputError("INVALID_PUBLIC_PRIVATE_STATUS");
  }
  if (
    profile.nonprofitStatus !== null &&
    !["NONPROFIT", "FOR_PROFIT", "UNKNOWN"].includes(profile.nonprofitStatus)
  ) {
    throw new ApiInputError("INVALID_NONPROFIT_STATUS");
  }
}

// ---------------------------------------------------------------------------
// Database row mapping
// ---------------------------------------------------------------------------

function rowToResponse(row: ProfileRow): ApplicantProfileResponse {
  let czNaceCodes: readonly string[] = [];
  if (row.cz_nace_json) {
    try {
      const parsed = JSON.parse(row.cz_nace_json);
      if (Array.isArray(parsed)) {
        czNaceCodes = Object.freeze([...parsed].filter(isNonEmptyString));
      }
    } catch {
      czNaceCodes = [];
    }
  }

  let lastResolvedAt: string | null = null;
  if (row.field_sources_json) {
    try {
      const fieldSources: unknown = JSON.parse(row.field_sources_json);
      if (typeof fieldSources === "object" && fieldSources !== null) {
        const sources = fieldSources as Record<string, unknown>;
        for (const s of Object.values(sources)) {
          if (
            s &&
            typeof s === "object" &&
            !Array.isArray(s) &&
            ["ARES", "CZSO", "OTHER_OFFICIAL"].includes((s as { sourceKind?: string }).sourceKind ?? "") &&
            isDateTime((s as { observedAt?: unknown }).observedAt)
          ) {
            const observed = (s as { observedAt: string }).observedAt;
            if (
              lastResolvedAt === null ||
              Date.parse(observed) > Date.parse(lastResolvedAt)
            ) {
              lastResolvedAt = observed;
            }
          }
        }
      }
    } catch {
        lastResolvedAt = null;
    }
  }

  return {
    id: row.id,
    applicantType: row.applicant_type,
    ico: row.ico,
    organisationName: row.organisation_name,
    legalFormCode: row.legal_form_code,
    municipalityCode: row.municipality_code,
    municipalityName: row.municipality_name,
    regionCode: row.region_code,
    municipalityPopulation: row.municipality_population,
    municipalityPopulationAsOf: row.municipality_population_as_of,
    vatStatus: row.vat_status,
    organisationSize: row.organisation_size,
    publicPrivateStatus: row.public_private_status,
    nonprofitStatus: row.nonprofit_status,
    czNaceCodes,
    lastResolvedAt,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

// ---------------------------------------------------------------------------
// CRUD operations
// ---------------------------------------------------------------------------

/** Read the caller's applicant profile (anonymous owner capability).
 *  Returns null when no profile exists — UNKNOWN, not FAIL.
 */
export async function getApplicantProfile(
  env: Env,
  ownerToken: string,
): Promise<ApplicantProfileResponse | null> {
  const userId = await ownerUserId(ownerToken, env);
  const row = await env.DB.prepare(
    `SELECT
       id, applicant_type, ico, organisation_name, legal_form_code,
       municipality_code, municipality_name, region_code,
       municipality_population, municipality_population_as_of,
       vat_status, organisation_size, public_private_status,
       nonprofit_status, cz_nace_json, field_sources_json,
       created_at, updated_at
     FROM applicant_profiles
     WHERE user_id = ?
     LIMIT 1`,
  ).bind(userId).first<ProfileRow>();

  return row ? rowToResponse(row) : null;
}

/** Create or update the caller's applicant profile (local→server sync hook).
 *  Upsert is idempotent per owner (user_id): repeated calls with the same
 *  payload produce the same profile state.
 */
export async function upsertApplicantProfile(
  input: ApplicantProfileInput,
  env: Env,
  ownerToken: string,
  now: Date = new Date(),
): Promise<ApplicantProfileResponse> {
  const userId = await ownerUserId(ownerToken, env);
  const timestamp = now.toISOString();
  const czNaceJson = JSON.stringify([...input.czNaceCodes]);
  const fieldSourcesJson = JSON.stringify(input.fieldSources);

  const profileId = "app_" + randomId();
  await env.DB.prepare(
      `INSERT INTO applicant_profiles(
         id, user_id, applicant_type, ico, organisation_name, legal_form_code,
         municipality_code, municipality_name, region_code,
         municipality_population, municipality_population_as_of,
         vat_status, organisation_size, public_private_status,
         nonprofit_status, cz_nace_json, field_sources_json,
         created_at, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(user_id) WHERE user_id IS NOT NULL DO UPDATE SET
         applicant_type = excluded.applicant_type, ico = excluded.ico,
         organisation_name = excluded.organisation_name,
         legal_form_code = excluded.legal_form_code,
         municipality_code = excluded.municipality_code,
         municipality_name = excluded.municipality_name,
         region_code = excluded.region_code,
         municipality_population = excluded.municipality_population,
         municipality_population_as_of = excluded.municipality_population_as_of,
         vat_status = excluded.vat_status,
         organisation_size = excluded.organisation_size,
         public_private_status = excluded.public_private_status,
         nonprofit_status = excluded.nonprofit_status,
         cz_nace_json = excluded.cz_nace_json,
         field_sources_json = excluded.field_sources_json,
         updated_at = excluded.updated_at`,
    ).bind(
      profileId, userId, input.applicantType, input.ico, input.organisationName,
      input.legalFormCode, input.municipalityCode, input.municipalityName,
      input.regionCode, input.municipalityPopulation, input.municipalityPopulationAsOf,
      input.vatStatus, input.organisationSize, input.publicPrivateStatus,
      input.nonprofitStatus, czNaceJson, fieldSourcesJson,
      timestamp, timestamp,
    ).run();

  // Read back so the response reflects DB defaults/CONSTRAINTS and the
  // computed lastResolvedAt is fresh.
  const updated = await getApplicantProfile(env, ownerToken);
  if (!updated) {
    throw new Error("PROFILE_UPSERT_READBACK_FAILED");
  }
  return updated;
}

/** Delete the caller's applicant profile (reset/clear on server).
 *  Idempotent: deleting a non-existent profile is a no-op (204).
 */
export async function deleteApplicantProfile(
  env: Env,
  ownerToken: string,
): Promise<void> {
  const userId = await ownerUserId(ownerToken, env);
  await env.DB.prepare(
    `DELETE FROM applicant_profiles WHERE user_id = ?`,
  ).bind(userId).run();
}

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

/** Matches exactly "/applicant-profile", no path params. */
export function isApplicantProfileRoute(pathname: string): boolean {
  return pathname === "/applicant-profile";
}

/** Matches "/applicant-profile/last-resolved" — read-only refresh info. */
export function isApplicantProfileRefreshRoute(pathname: string): boolean {
  return pathname === "/applicant-profile/last-resolved";
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

function randomId(): string {
  return crypto.randomUUID().replaceAll("-", "");
}
