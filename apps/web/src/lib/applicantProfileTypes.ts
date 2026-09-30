/**
 * Local-first applicant profile types.
 *
 * These mirror the canonical applicant-profile schema
 * (schemas/v1/applicant-profile.schema.json, v1.0.0) so the web store and the
 * backend share one vocabulary. The store treats schemaVersion as a strict
 * gate: a profile whose embedded schemaVersion does not match
 * APPLICANT_PROFILE_SCHEMA_VERSION is never trusted.
 */

/** Applicant type enum — UNKNOWN is the default, "I don't know yet" state.
 *  Type is NEVER inferred from legal form alone (ARES tells you právni forma,
 *  not "sportovní klub"). Type is either user-declared or explicitly derived
 *  by a separate rule.
 */
export type ApplicantProfileType =
  | "UNKNOWN"
  | "NATURAL_PERSON"
  | "SELF_EMPLOYED"
  | "BUSINESS"
  | "MUNICIPALITY"
  | "REGION"
  | "ASSOCIATION"
  | "SPORTS_CLUB"
  | "NONPROFIT"
  | "SCHOOL"
  | "CONTRIBUTORY_ORGANISATION"
  | "HOA"
  | "COOPERATIVE"
  | "AGRICULTURAL_ENTITY"
  | "RESEARCH_ORGANISATION"
  | "OTHER";

/** Who/what provided a single profile field.
 *  Provenance is preserved on every field so the UI can show "auto-extracted
 *  from ARES" vs "you typed this" vs "needs review" without reconstructing it
 *  from elsewhere.
 */
export interface FieldSource {
  /** One of USER, ARES, CZSO, OTHER_OFFICIAL, DERIVED. */
  sourceKind: "USER" | "ARES" | "CZSO" | "OTHER_OFFICIAL" | "DERIVED";
  /** Optional reference to the source (e.g. ARES IČO URL, CZSO dataset id). */
  sourceReference: string | null;
  /** When this field value was observed from its source (ISO-8601). */
  observedAt: string;
  /** When the field was verified by a human or process (ISO-8601), or null. */
  verifiedAt: string | null;
  /** Verification posture of this field. */
  verificationStatus:
    | "USER_DECLARED"
    | "AUTO_EXTRACTED"
    | "PARTIALLY_VERIFIED"
    | "VERIFIED"
    | "NEEDS_REVIEW";
  /** Optional link to a stored evidence artifact (manual upload, snapshot). */
  evidenceId: string | null;
}

/** A local-first applicant profile.
 *
 *  Every persisted profile MUST embed schemaVersion === "1.0.0".
 *  Nullable fields are null when unknown — never omitted or made-up.
 *
 *  Privacy note: no personal identity fields (tax ID, personal name, contact)
 *  are present here by design. For natural persons the profile may contain
 *  only the minimal municipality context needed for grant eligibility.
 */
export interface ApplicantProfile {
  readonly schemaVersion: "1.0.0";
  readonly id: string;
  readonly applicantType: ApplicantProfileType;
  readonly applicantTypeId: string | null;
  readonly ico: string | null;
  readonly organisationName: string | null;
  readonly legalFormCode: string | null;
  readonly municipalityCode: string | null;
  readonly municipalityName: string | null;
  readonly regionCode: string | null;
  readonly seatGeographyId: string | null;
  readonly municipalityPopulation: number | null;
  readonly municipalityPopulationAsOf: string | null;
  readonly vatStatus:
    | "UNKNOWN"
    | "PAYER"
    | "NON_PAYER"
    | null;
  readonly organisationSize:
    | "UNKNOWN"
    | "MICRO"
    | "SMALL"
    | "MEDIUM"
    | "LARGE"
    | null;
  readonly publicPrivateStatus:
    | "PUBLIC"
    | "PRIVATE"
    | "MIXED"
    | "UNKNOWN"
    | null;
  readonly nonprofitStatus:
    | "NONPROFIT"
    | "FOR_PROFIT"
    | "UNKNOWN"
    | null;
  readonly czNaceCodes: readonly string[];
  readonly fieldSources: Readonly<
    Record<string, Readonly<FieldSource>>
  >;
  readonly createdAt: string;
  readonly updatedAt: string;
}
