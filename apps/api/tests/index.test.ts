import { describe, expect, it } from "vitest";

import type { Env } from "../src/env";
import { handleRequest } from "../src/index";

function env(dbResult: unknown = { ok: 1 }): Env {
  return {
    ENVIRONMENT: "local",
    DB: {
      prepare() {
        return {
          async first<T = unknown>() {
            return dbResult as T | null;
          },
        };
      },
    },
    RAW: {
      async head() {
        return null;
      },
    },
    SEARCH: {
      async describe() {
        return {};
      },
    },
  };
}

describe("api worker", () => {
  it("reports health without touching remote services", async () => {
    const response = await handleRequest(
      new Request("https://example.test/health"),
      env(),
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      status: "ok",
      service: "dotacni-majak-api",
      environment: "local",
    });
  });

  it("reports ready only when D1 check succeeds", async () => {
    const ok = await handleRequest(new Request("https://example.test/ready"), env());
    expect(ok.status).toBe(200);

    const failed = await handleRequest(
      new Request("https://example.test/ready"),
      env(null),
    );
    expect(failed.status).toBe(503);
  });

  it("rejects state-changing HTTP methods by default", async () => {
    const response = await handleRequest(
      new Request("https://example.test/health", { method: "POST" }),
      env(),
    );
    expect(response.status).toBe(405);
    expect(response.headers.get("allow")).toBe("GET, HEAD");
  });
});
