export const intentExamples = [
  "rekonstrukce sportoviště",
  "zateplení školy",
  "dětské hřiště",
  "digitalizace malé firmy",
] as const;

export function normalizeIntent(intent: string): string {
  return intent.trim().replace(/\s+/g, " ");
}

export function readIntentFromSearch(search: string): string {
  return normalizeIntent(new URLSearchParams(search).get("intent") ?? "");
}

export interface SearchUrlState {
  intent: string;
  status: "ALL" | "OPEN" | "PLANNED" | "ANNOUNCED";
  instrument: "ALL" | "GRANT" | "LOAN" | "GUARANTEE" | "EQUITY" | "MIXED" | "OTHER";
  projectBudgetCzk: string;
  provider: string;
  deadline: "ALL" | "KNOWN" | "UNKNOWN";
  closesBy: string;
  closesFrom: string;
  sort: "RELEVANCE" | "DEADLINE" | "DEADLINE_LATEST";
}

const defaults: SearchUrlState = {
  intent: "", status: "ALL", instrument: "ALL", projectBudgetCzk: "", provider: "",
  deadline: "ALL", closesBy: "", closesFrom: "", sort: "RELEVANCE",
};

export function readSearchUrlState(search: string): SearchUrlState {
  if (search.length > 65536) return { ...defaults };
  const params = new URLSearchParams(search);
  const single = (key: string, maxLength: number): string | null => {
    const values = params.getAll(key);
    return values.length === 1 && values[0].length <= maxLength ? values[0] : null;
  };
  const intent = normalizeIntent(single("intent", 65536) ?? "");
  if (!intent || intent.length > 500) return { ...defaults };
  const oneOf = <T extends string>(key: string, options: readonly T[], fallback: T): T => {
    const value = single(key, 32);
    return options.find((option) => option === value) ?? fallback;
  };
  const date = (key: string): string => {
    const value = single(key, 10);
    if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "";
    const parsed = new Date(`${value}T00:00:00Z`);
    return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value ? value : "";
  };
  const providerValue = single("provider", 200);
  const provider = providerValue && providerValue === providerValue.trim() &&
    !/[\u0000-\u001f\u007f]/.test(providerValue) ? providerValue : "";
  const budgetValue = single("projectBudgetCzk", 13);
  const projectBudgetCzk = budgetValue && /^(0|[1-9][0-9]{0,12})$/.test(budgetValue) &&
    Number.isSafeInteger(Number(budgetValue) * 100) ? budgetValue : "";
  const state: SearchUrlState = {
    intent,
    status: oneOf("status", ["OPEN", "PLANNED", "ANNOUNCED"], "ALL"),
    instrument: oneOf("instrument", ["GRANT", "LOAN", "GUARANTEE", "EQUITY", "MIXED", "OTHER"], "ALL"),
    projectBudgetCzk,
    provider,
    deadline: oneOf("deadline", ["KNOWN", "UNKNOWN"], "ALL"),
    closesBy: date("closesBy"), closesFrom: date("closesFrom"),
    sort: oneOf("sort", ["DEADLINE", "DEADLINE_LATEST"], "RELEVANCE"),
  };
  if (state.projectBudgetCzk) state.instrument = "GRANT";
  if (state.deadline === "UNKNOWN") { state.closesBy = ""; state.closesFrom = ""; }
  if (state.closesFrom && state.closesBy && state.closesFrom > state.closesBy) {
    state.closesBy = ""; state.closesFrom = "";
  }
  return state;
}

export function buildSearchUrl(state: SearchUrlState): string {
  if (!state.intent) return "/hledat";
  const params = new URLSearchParams({ intent: state.intent });
  for (const key of ["status", "instrument", "deadline"] as const) {
    if (state[key] !== "ALL") params.set(key, state[key]);
  }
  if (state.sort !== "RELEVANCE") params.set("sort", state.sort);
  for (const key of ["projectBudgetCzk", "provider", "closesBy", "closesFrom"] as const) {
    if (state[key]) params.set(key, state[key]);
  }
  return `/hledat?${params.toString()}`;
}

export function buildDetailSearchQuery(state: SearchUrlState): string {
  const query = buildSearchUrl(state).split("?")[1];
  return query ? query.replace(/^intent=[^&]*/, `intent=${encodeURIComponent(state.intent)}`) : "";
}

export function readReturnResult(search: string): string | null {
  const values = new URLSearchParams(search).getAll("returnResult");
  const value = values.length === 1 ? values[0] : "";
  return value.length > 0 && value.length <= 200 && !/[\u0000-\u001f\u007f]/.test(value) ? value : null;
}

export function buildReturnSearchUrl(search: string): string {
  const url = buildSearchUrl(readSearchUrlState(search));
  const result = readReturnResult(search);
  if (!result || url === "/hledat") return url;
  const params = new URLSearchParams(url.split("?")[1]);
  params.set("returnResult", result);
  return `/hledat?${params.toString()}`;
}

export function buildIntentSearchUrl(intent: string): string {
  const normalized = normalizeIntent(intent);
  if (!normalized) {
    return "/hledat";
  }
  const params = new URLSearchParams({ intent: normalized });
  return `/hledat?${params.toString()}`;
}
