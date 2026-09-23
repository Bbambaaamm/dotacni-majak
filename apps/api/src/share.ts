import type { Env } from "./env";

const TOKEN_DOMAIN = "dotacni-majak-project-share-v1\0";
const TOKEN_RE = /^[A-Za-z0-9_-]{40,128}$/;

interface SharedProjectRow {
  id: string;
  title: string | null;
  natural_language_intent: string;
  currency_code: string;
  estimated_total_budget_minor: number | null;
  planned_start: string | null;
  planned_end: string | null;
  updated_at: string;
}

export interface PublicSharedProject {
  id: string;
  title: string | null;
  intent: string;
  currencyCode: string;
  estimatedTotalBudgetMinor: number | null;
  plannedStart: string | null;
  plannedEnd: string | null;
  updatedAt: string;
}

export async function resolvePublicProjectShare(
  token: string,
  env: Env,
  now: Date = new Date(),
): Promise<PublicSharedProject | null> {
  if (!TOKEN_RE.test(token)) {
    return null;
  }

  const tokenHash = await hashShareToken(token);
  const row = await env.DB.prepare(
    `SELECT
       p.id,
       p.title,
       p.natural_language_intent,
       p.currency_code,
       p.estimated_total_budget_minor,
       p.planned_start,
       p.planned_end,
       p.updated_at
     FROM project_share_links AS s
     INNER JOIN projects AS p ON p.id = s.project_id
     WHERE s.token_hash = ?
       AND s.scope = 'PROJECT_READ_ONLY'
       AND s.revoked_at IS NULL
       AND (s.expires_at IS NULL OR s.expires_at > ?)
     LIMIT 1`,
  )
    .bind(tokenHash, now.toISOString())
    .first<SharedProjectRow>();

  if (!row) {
    return null;
  }

  // Explicit allowlist: applicant profile, owner ID, internal notes, document
  // storage references and watch/account data never leave this resolver.
  return {
    id: row.id,
    title: row.title,
    intent: row.natural_language_intent,
    currencyCode: row.currency_code,
    estimatedTotalBudgetMinor: row.estimated_total_budget_minor,
    plannedStart: row.planned_start,
    plannedEnd: row.planned_end,
    updatedAt: row.updated_at,
  };
}

export async function hashShareToken(token: string): Promise<string> {
  const bytes = new TextEncoder().encode(TOKEN_DOMAIN + token);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}
