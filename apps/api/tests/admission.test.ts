import { describe, expect, it } from "vitest";

import type { D1PreparedStatementLike, Env } from "../src/env";
import { handleRequest, MAX_IN_FLIGHT_READY_REQUESTS, MAX_IN_FLIGHT_REQUESTS } from "../src/index";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function envWithPrepare(prepare: () => D1PreparedStatementLike): Env {
  return {
    ENVIRONMENT: "local",
    DB: {
      prepare,
      async batch() { throw new Error("unexpected DB batch"); },
    },
    RAW: { async head() { throw new Error("unexpected R2 access"); } },
    SEARCH: { async describe() { throw new Error("unexpected Vectorize access"); } },
  };
}

describe("per-isolate API admission", () => {
  it("admits exactly the cap, rejects excess work without DB access, and releases success and failure slots", async () => {
    const gates = Array.from({ length: MAX_IN_FLIGHT_REQUESTS }, () => deferred<null>());
    let prepares = 0;
    const env = envWithPrepare(() => {
      const index = prepares++;
      const statement = {
        bind: () => statement,
        first: () => gates[index]?.promise ?? Promise.resolve(null),
      } as D1PreparedStatementLike;
      return statement;
    });
    const request = () => new Request("https://example.test/grants/unknown");
    const admitted = gates.map(() => handleRequest(request(), env));
    expect(prepares).toBe(MAX_IN_FLIGHT_REQUESTS);

    const excess = await handleRequest(request(), env);
    expect(excess.status).toBe(503);
    expect(excess.headers.get("retry-after")).toBe("1");
    expect(excess.headers.get("cache-control")).toBe("no-store");
    expect(excess.headers.get("content-type")).toContain("application/json");
    expect(await excess.json()).toEqual({ error: "API_OVERLOADED" });
    expect(prepares).toBe(MAX_IN_FLIGHT_REQUESTS);

    // A rejected dependency still releases its slot through the outer finally.
    gates[0].reject(new Error("synthetic D1 failure"));
    expect((await admitted[0]).status).toBe(500);
    const replacement = await handleRequest(request(), env);
    expect(replacement.status).toBe(404);
    expect(prepares).toBe(MAX_IN_FLIGHT_REQUESTS + 1);

    gates.slice(1).forEach((gate) => gate.resolve(null));
    expect((await Promise.all(admitted.slice(1))).map((response) => response.status))
      .toEqual(Array(MAX_IN_FLIGHT_REQUESTS - 1).fill(404));
    expect((await handleRequest(request(), env)).status).toBe(404);
  });

  it("keeps GET and HEAD health and ready probes available at capacity", async () => {
    const gate = deferred<null>();
    let ordinaryPrepares = 0;
    const ordinaryEnv = envWithPrepare(() => {
      ordinaryPrepares += 1;
      const statement = { bind: () => statement, first: () => gate.promise } as D1PreparedStatementLike;
      return statement;
    });
    const pending = Array.from({ length: MAX_IN_FLIGHT_REQUESTS }, () =>
      handleRequest(new Request("https://example.test/grants/unknown"), ordinaryEnv));
    expect(ordinaryPrepares).toBe(MAX_IN_FLIGHT_REQUESTS);

    let readyChecks = 0;
    const probeEnv = envWithPrepare(() => {
      readyChecks += 1;
      return { first: async () => ({ ok: 1 }) } as D1PreparedStatementLike;
    });
    for (const method of ["GET", "HEAD"]) {
      expect((await handleRequest(new Request("https://example.test/health", { method }), probeEnv)).status).toBe(200);
      expect((await handleRequest(new Request("https://example.test/ready", { method }), probeEnv)).status).toBe(200);
    }
    expect(readyChecks).toBe(2);
    expect(ordinaryPrepares).toBe(MAX_IN_FLIGHT_REQUESTS);
    expect((await handleRequest(new Request("https://example.test/health", { method: "PATCH" }), probeEnv)).status).toBe(503);
    expect(readyChecks).toBe(2);

    gate.resolve(null);
    expect((await Promise.all(pending)).map((response) => response.status))
      .toEqual(Array(MAX_IN_FLIGHT_REQUESTS).fill(404));
  });

  it("bounds ready D1 checks independently and releases slots after success and failure", async () => {
    const gates = Array.from({ length: MAX_IN_FLIGHT_READY_REQUESTS + 2 }, () => deferred<{ ok: number }>());
    let prepares = 0;
    const probeEnv = envWithPrepare(() => {
      const gate = gates[prepares++];
      const statement = { first: () => gate.promise } as D1PreparedStatementLike;
      return statement;
    });
    const ready = (method: string) => handleRequest(new Request("https://example.test/ready", { method }), probeEnv);
    const pendingGet = ready("GET");
    const pendingHead = ready("HEAD");
    expect(prepares).toBe(MAX_IN_FLIGHT_READY_REQUESTS);

    for (const method of ["GET", "HEAD"]) {
      const excess = await ready(method);
      expect(excess.status).toBe(503);
      expect(excess.headers.get("retry-after")).toBe("1");
      expect(excess.headers.get("cache-control")).toBe("no-store");
      expect(excess.headers.get("content-type")).toContain("application/json");
      expect(await excess.json()).toEqual({ error: "API_OVERLOADED" });
    }
    expect(prepares).toBe(MAX_IN_FLIGHT_READY_REQUESTS);
    expect((await handleRequest(new Request("https://example.test/health"), probeEnv)).status).toBe(200);
    expect(prepares).toBe(MAX_IN_FLIGHT_READY_REQUESTS);

    gates[0].resolve({ ok: 1 });
    expect((await pendingGet).status).toBe(200);
    const afterSuccess = ready("GET");
    expect(prepares).toBe(MAX_IN_FLIGHT_READY_REQUESTS + 1);

    gates[1].reject(new Error("synthetic D1 failure"));
    const failed = await pendingHead;
    expect(failed.status).toBe(503);
    expect(await failed.json()).toEqual({ status: "not_ready", reason: "D1_UNAVAILABLE" });
    const afterFailure = ready("HEAD");
    expect(prepares).toBe(MAX_IN_FLIGHT_READY_REQUESTS + 2);

    gates[2].resolve({ ok: 1 });
    gates[3].resolve({ ok: 1 });
    expect((await Promise.all([afterSuccess, afterFailure])).map((response) => response.status))
      .toEqual([200, 200]);
  });
});
