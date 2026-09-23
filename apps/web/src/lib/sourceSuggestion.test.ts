import { describe, expect, it } from "vitest";

import {
  createSourceSuggestion,
  reviewSourceSuggestion,
} from "./sourceSuggestion";

describe("source suggestion workflow", () => {
  it("always starts in PENDING_REVIEW", () => {
    const item = createSourceSuggestion({
      id: "s1",
      name: "Krajský dotační portál",
      url: "https://example.gov.cz/dotace",
      createdAt: "2026-09-23T18:00:00Z",
    });
    expect(item.status).toBe("PENDING_REVIEW");
  });

  it("rejects non-HTTPS and credential URLs", () => {
    expect(() =>
      createSourceSuggestion({
        id: "s1",
        name: "Test",
        url: "http://example.com",
        createdAt: "2026-09-23T18:00:00Z",
      }),
    ).toThrow(/HTTPS/);

    expect(() =>
      createSourceSuggestion({
        id: "s2",
        name: "Test",
        url: "https://user:pass@example.com",
        createdAt: "2026-09-23T18:00:00Z",
      }),
    ).toThrow(/přihlašovací/);
  });

  it("approval is explicit and does not create a source registry entry", () => {
    const pending = createSourceSuggestion({
      id: "s1",
      name: "Test",
      url: "https://example.com",
      createdAt: "2026-09-23T18:00:00Z",
    });
    const approved = reviewSourceSuggestion(pending, {
      decision: "APPROVED",
      reviewedAt: "2026-09-23T19:00:00Z",
      reviewNote: "Ověřit retrieval metodu v samostatném connector issue.",
    });

    expect(approved.status).toBe("APPROVED");
    expect("sourceRegistryId" in approved).toBe(false);
  });

  it("review cannot be silently overwritten", () => {
    const pending = createSourceSuggestion({
      id: "s1",
      name: "Test",
      url: "https://example.com",
      createdAt: "2026-09-23T18:00:00Z",
    });
    const rejected = reviewSourceSuggestion(pending, {
      decision: "REJECTED",
      reviewedAt: "2026-09-23T19:00:00Z",
    });

    expect(() =>
      reviewSourceSuggestion(rejected, {
        decision: "APPROVED",
        reviewedAt: "2026-09-23T20:00:00Z",
      }),
    ).toThrow();
  });
});
