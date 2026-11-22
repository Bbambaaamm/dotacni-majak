// Limits apply to request body bytes, before JSON parsing or persistence.
export type BodyEndpoint = "project" | "profile" | "share" | "watch" | "workspace";

const DEFAULT_BODY_LIMIT_BYTES = 16 * 1024;

export const BODY_LIMIT_BYTES = {
  project: DEFAULT_BODY_LIMIT_BYTES,
  profile: DEFAULT_BODY_LIMIT_BYTES,
  share: DEFAULT_BODY_LIMIT_BYTES,
  watch: 4 * 1024,
  workspace: 4 * 1024,
} as const satisfies Record<BodyEndpoint, number>;
