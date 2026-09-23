export type RelevanceJudgment =
  | "RELEVANT"
  | "NOT_RELEVANT"
  | "UNSURE";

export interface RelevanceFeedbackRecord {
  id: string;
  grantCallVersionId: string;
  projectId: string | null;
  judgment: RelevanceJudgment;
  matcherVersion: string;
  context: "SEARCH_RESULT" | "GRANT_DETAIL" | "COMPARISON";
  createdAt: string;
}

export interface FeedbackStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export function createRelevanceFeedback(input: {
  id: string;
  grantCallVersionId: string;
  projectId?: string | null;
  judgment: RelevanceJudgment;
  matcherVersion: string;
  context?: RelevanceFeedbackRecord["context"];
  createdAt: string;
}): RelevanceFeedbackRecord {
  if (!input.id.trim()) throw new Error("feedback id is required");
  if (!input.grantCallVersionId.trim()) {
    throw new Error("grantCallVersionId is required");
  }
  if (!input.matcherVersion.trim()) {
    throw new Error("matcherVersion is required");
  }

  return {
    id: input.id,
    grantCallVersionId: input.grantCallVersionId,
    projectId: input.projectId ?? null,
    judgment: input.judgment,
    matcherVersion: input.matcherVersion,
    context: input.context ?? "SEARCH_RESULT",
    createdAt: input.createdAt,
  };
}

export class LocalRelevanceFeedbackStore {
  constructor(
    private readonly storage: FeedbackStorage,
    private readonly key = "dotacni-majak:relevance-feedback:v1",
  ) {}

  all(): readonly RelevanceFeedbackRecord[] {
    const raw = this.storage.getItem(this.key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isFeedbackRecord);
  }

  save(record: RelevanceFeedbackRecord): void {
    const records = this.all().filter(
      (item) =>
        !(
          item.grantCallVersionId === record.grantCallVersionId &&
          item.projectId === record.projectId &&
          item.context === record.context
        ),
    );
    this.storage.setItem(this.key, JSON.stringify([...records, record]));
  }
}

function isFeedbackRecord(value: unknown): value is RelevanceFeedbackRecord {
  if (!value || typeof value !== "object") return false;
  const record = value as Partial<RelevanceFeedbackRecord>;
  return (
    typeof record.id === "string" &&
    typeof record.grantCallVersionId === "string" &&
    (record.projectId === null || typeof record.projectId === "string") &&
    (record.judgment === "RELEVANT" ||
      record.judgment === "NOT_RELEVANT" ||
      record.judgment === "UNSURE") &&
    typeof record.matcherVersion === "string" &&
    (record.context === "SEARCH_RESULT" ||
      record.context === "GRANT_DETAIL" ||
      record.context === "COMPARISON") &&
    typeof record.createdAt === "string"
  );
}
