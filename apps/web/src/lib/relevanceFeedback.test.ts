import { describe, expect, it } from "vitest";

import {
  createRelevanceFeedback,
  LocalRelevanceFeedbackStore,
  type FeedbackStorage,
} from "./relevanceFeedback";

class MemoryStorage implements FeedbackStorage {
  private readonly data = new Map<string, string>();
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
}

describe("relevance feedback", () => {
  it("contains no free-text or personal identity field", () => {
    const record = createRelevanceFeedback({
      id: "f1",
      grantCallVersionId: "v1",
      judgment: "RELEVANT",
      matcherVersion: "hybrid-v1",
      createdAt: "2026-09-23T17:00:00Z",
    });

    expect(record.projectId).toBeNull();
    expect("comment" in record).toBe(false);
    expect("userId" in record).toBe(false);
    expect("email" in record).toBe(false);
  });

  it("replaces previous judgment for same context instead of inflating counts", () => {
    const storage = new MemoryStorage();
    const store = new LocalRelevanceFeedbackStore(storage);

    store.save(
      createRelevanceFeedback({
        id: "f1",
        grantCallVersionId: "v1",
        projectId: "p1",
        judgment: "RELEVANT",
        matcherVersion: "hybrid-v1",
        createdAt: "2026-09-23T17:00:00Z",
      }),
    );
    store.save(
      createRelevanceFeedback({
        id: "f2",
        grantCallVersionId: "v1",
        projectId: "p1",
        judgment: "NOT_RELEVANT",
        matcherVersion: "hybrid-v1",
        createdAt: "2026-09-23T17:05:00Z",
      }),
    );

    expect(store.all()).toHaveLength(1);
    expect(store.all()[0]?.judgment).toBe("NOT_RELEVANT");
  });

  it("keeps unsure as an explicit judgment", () => {
    const record = createRelevanceFeedback({
      id: "f1",
      grantCallVersionId: "v1",
      judgment: "UNSURE",
      matcherVersion: "hybrid-v1",
      createdAt: "2026-09-23T17:00:00Z",
    });
    expect(record.judgment).toBe("UNSURE");
  });
});
