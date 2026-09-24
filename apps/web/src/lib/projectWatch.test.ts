import { describe, expect, it } from "vitest";

import {
  enableProjectWatch,
  getProjectWatch,
  setProjectWatchEnabled,
} from "./projectWatch";

const PROJECT = "prj_" + "a".repeat(32);
const OWNER = "A".repeat(43);
const WATCH = {
  id: "wch_" + "b".repeat(32),
  projectId: PROJECT,
  enabled: true,
  minimumMatchBand: "POSSIBLE" as const,
  createdAt: "2026-09-24T00:00:00Z",
  updatedAt: "2026-09-24T00:00:00Z",
};

describe("project watch API client", () => {
  it("uses owner capability and parses watch", async () => {
    const calls: Request[] = [];
    const fetcher: typeof fetch = async (input, init) => {
      calls.push(new Request(input, init));
      return new Response(JSON.stringify({ watch: WATCH }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };

    const watch = await enableProjectWatch(
      PROJECT,
      OWNER,
      fetcher,
      "https://example.test",
    );
    expect(watch.id).toBe(WATCH.id);
    expect(calls[0]?.method).toBe("POST");
    expect(calls[0]?.headers.get("authorization")).toBe(`Bearer ${OWNER}`);
  });

  it("returns null when authorized project has no watch", async () => {
    const fetcher: typeof fetch = async () =>
      new Response(JSON.stringify({ watch: null }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    await expect(
      getProjectWatch(PROJECT, OWNER, fetcher, "https://example.test"),
    ).resolves.toBeNull();
  });

  it("sends explicit enabled boolean on PATCH", async () => {
    let body = "";
    const fetcher: typeof fetch = async (input, init) => {
      const request = new Request(input, init);
      body = await request.text();
      return new Response(
        JSON.stringify({ watch: { ...WATCH, enabled: false } }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    };
    const result = await setProjectWatchEnabled(
      PROJECT,
      OWNER,
      false,
      fetcher,
      "https://example.test",
    );
    expect(JSON.parse(body)).toEqual({ enabled: false });
    expect(result.enabled).toBe(false);
  });
});
