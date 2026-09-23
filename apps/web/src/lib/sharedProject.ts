export interface SharedProject {
  id: string;
  title: string | null;
  intent: string;
  currencyCode: string;
  estimatedTotalBudgetMinor: number | null;
  plannedStart: string | null;
  plannedEnd: string | null;
  updatedAt: string;
}

export type SharedProjectLoadResult =
  | { status: "ok"; project: SharedProject }
  | { status: "not-found" }
  | { status: "error" };

export function sharedProjectTokenFromPath(pathname: string): string | null {
  const normalized = "/" + pathname.split(/[?#]/, 1)[0].split("/").filter(Boolean).join("/");
  const match = normalized.match(/^\/s\/([A-Za-z0-9_-]{40,128})$/);
  return match?.[1] ?? null;
}

export function apiUrl(path: string, base = import.meta.env.VITE_API_BASE_URL ?? ""): string {
  if (!path.startsWith("/")) {
    throw new Error("API path must be absolute");
  }
  const trimmed = base.trim();
  if (!trimmed) return path;

  const root = new URL(trimmed.endsWith("/") ? trimmed : trimmed + "/");
  const local = root.hostname === "localhost" || root.hostname === "127.0.0.1";
  if (root.protocol !== "https:" && !(local && root.protocol === "http:")) {
    throw new Error("API base URL must use HTTPS outside local development");
  }
  return new URL(path.slice(1), root).toString();
}

export async function loadSharedProject(
  token: string,
  fetcher: typeof fetch = fetch,
  baseUrl?: string,
): Promise<SharedProjectLoadResult> {
  if (!/^[A-Za-z0-9_-]{40,128}$/.test(token)) {
    return { status: "not-found" };
  }

  let response: Response;
  try {
    response = await fetcher(
      apiUrl("/share/" + encodeURIComponent(token), baseUrl),
      {
        method: "GET",
        headers: { accept: "application/json" },
        credentials: "omit",
        cache: "no-store",
        referrerPolicy: "no-referrer",
      },
    );
  } catch {
    return { status: "error" };
  }

  if (response.status === 404) return { status: "not-found" };
  if (!response.ok) return { status: "error" };

  try {
    const payload = await response.json() as unknown;
    const project = parseSharedProject(payload);
    return project ? { status: "ok", project } : { status: "error" };
  } catch {
    return { status: "error" };
  }
}

export function formatMinorMoney(
  minor: number | null,
  currencyCode: string,
  locale = "cs-CZ",
): string | null {
  if (minor === null || !Number.isSafeInteger(minor)) return null;
  try {
    const formatter = new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currencyCode,
    });
    const digits = formatter.resolvedOptions().maximumFractionDigits;
    return formatter.format(minor / 10 ** digits);
  } catch {
    return null;
  }
}

function parseSharedProject(payload: unknown): SharedProject | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const project = (payload as Record<string, unknown>).project;
  if (!project || typeof project !== "object" || Array.isArray(project)) return null;
  const value = project as Record<string, unknown>;

  if (
    typeof value.id !== "string"
    || (value.title !== null && typeof value.title !== "string")
    || typeof value.intent !== "string"
    || typeof value.currencyCode !== "string"
    || !/^[A-Z]{3}$/.test(value.currencyCode)
    || (
      value.estimatedTotalBudgetMinor !== null
      && (
        typeof value.estimatedTotalBudgetMinor !== "number"
        || !Number.isSafeInteger(value.estimatedTotalBudgetMinor)
        || value.estimatedTotalBudgetMinor < 0
      )
    )
    || (value.plannedStart !== null && typeof value.plannedStart !== "string")
    || (value.plannedEnd !== null && typeof value.plannedEnd !== "string")
    || typeof value.updatedAt !== "string"
  ) {
    return null;
  }

  return {
    id: value.id,
    title: value.title,
    intent: value.intent,
    currencyCode: value.currencyCode,
    estimatedTotalBudgetMinor: value.estimatedTotalBudgetMinor,
    plannedStart: value.plannedStart,
    plannedEnd: value.plannedEnd,
    updatedAt: value.updatedAt,
  };
}
