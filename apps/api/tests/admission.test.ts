import { describe, expect, it, vi } from "vitest";

import type { D1PreparedStatementLike, Env } from "../src/env";
import { handleRequest } from "../src/index";

const MAX_IN_FLIGHT_REQUESTS = 16;
const MAX_IN_FLIGHT_READY_REQUESTS = 2;

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
  it("bounds warnings per lane, counts a flood, and recovers after clock and logger failures", async () => {
    vi.resetModules();
    const { handleRequest: isolatedHandleRequest } = await import("../src/index");
    const clock = vi.spyOn(Date, "now").mockReturnValue(100_000);
    const ordinaryGate = deferred<null>();
    const readyGate = deferred<{ ok: number }>();
    const ordinaryEnv = envWithPrepare(() => {
      const statement = { bind: () => statement, first: () => ordinaryGate.promise } as D1PreparedStatementLike;
      return statement;
    });
    const readyEnv = envWithPrepare(() => ({ first: () => readyGate.promise }) as D1PreparedStatementLike);
    const log = vi.spyOn(console, "warn").mockImplementation(() => {});
    const ordinary = Array.from({ length: MAX_IN_FLIGHT_REQUESTS }, () =>
      isolatedHandleRequest(new Request("https://example.test/grants/unknown"), ordinaryEnv));
    const ready = Array.from({ length: MAX_IN_FLIGHT_READY_REQUESTS }, () =>
      isolatedHandleRequest(new Request("https://example.test/ready"), readyEnv));

    try {
      expect(log).not.toHaveBeenCalled();
      const secret = "private-sentinel-550";
      const rejectedOrdinary = await isolatedHandleRequest(new Request(
        `https://example.test/${secret}?token=${secret}`,
        { method: "POST", headers: { authorization: `Bearer ${secret}`, "x-forwarded-for": secret }, body: secret },
      ), ordinaryEnv);
      clock.mockReturnValue(130_000);
      const rejectedReady = await isolatedHandleRequest(new Request(
        `https://example.test/ready?token=${secret}`,
        { headers: { authorization: `Bearer ${secret}`, "x-forwarded-for": secret } },
      ), readyEnv);
      expect(rejectedOrdinary.status).toBe(503);
      expect(rejectedReady.status).toBe(503);
      expect(log.mock.calls).toEqual([
        [{ event: "api_admission_overload", lane: "ordinary", occupancy: 16, cap: 16, rejectedSinceLast: 1 }],
        [{ event: "api_admission_overload", lane: "ready", occupancy: 2, cap: 2, rejectedSinceLast: 1 }],
      ]);
      expect(JSON.stringify(log.mock.calls)).not.toContain(secret);

      for (let i = 0; i < 1000; i += 1) {
        expect((await isolatedHandleRequest(new Request("https://example.test/grants/unknown"), ordinaryEnv)).status).toBe(503);
      }
      expect(log).toHaveBeenCalledTimes(2);
      clock.mockReturnValue(Number.NaN);
      expect((await isolatedHandleRequest(new Request("https://example.test/grants/unknown"), ordinaryEnv)).status).toBe(503);
      clock.mockReturnValue(90_000);
      expect((await isolatedHandleRequest(new Request("https://example.test/grants/unknown"), ordinaryEnv)).status).toBe(503);
      expect(log).toHaveBeenCalledTimes(2);

      clock.mockReturnValue(160_000);
      expect((await isolatedHandleRequest(new Request("https://example.test/grants/unknown"), ordinaryEnv)).status).toBe(503);
      expect((await isolatedHandleRequest(new Request("https://example.test/ready"), readyEnv)).status).toBe(503);
      expect(log).toHaveBeenCalledTimes(3);
      expect(log.mock.calls[2]).toEqual([{ event: "api_admission_overload", lane: "ordinary", occupancy: 16, cap: 16, rejectedSinceLast: 1003 }]);

      clock.mockReturnValue(190_000);
      expect((await isolatedHandleRequest(new Request("https://example.test/ready"), readyEnv)).status).toBe(503);
      expect(log.mock.calls[3]).toEqual([{ event: "api_admission_overload", lane: "ready", occupancy: 2, cap: 2, rejectedSinceLast: 2 }]);

      clock.mockReturnValue(220_000);
      log.mockImplementationOnce(() => { throw new Error("logger failure"); });
      expect((await isolatedHandleRequest(new Request("https://example.test/grants/unknown"), ordinaryEnv)).status).toBe(503);
      expect((await isolatedHandleRequest(new Request("https://example.test/grants/unknown"), ordinaryEnv)).status).toBe(503);
      expect(log).toHaveBeenCalledTimes(5);
      clock.mockReturnValue(280_000);
      expect((await isolatedHandleRequest(new Request("https://example.test/grants/unknown"), ordinaryEnv)).status).toBe(503);
      expect(log.mock.calls[5]).toEqual([{ event: "api_admission_overload", lane: "ordinary", occupancy: 16, cap: 16, rejectedSinceLast: 3 }]);
    } finally {
      ordinaryGate.resolve(null);
      readyGate.resolve({ ok: 1 });
      await Promise.all([...ordinary, ...ready]);
      log.mockRestore();
      clock.mockRestore();
    }
    expect((await isolatedHandleRequest(new Request("https://example.test/grants/unknown"), ordinaryEnv)).status).toBe(404);
    expect((await isolatedHandleRequest(new Request("https://example.test/ready"), readyEnv)).status).toBe(200);
  });

  it("does not log normal admission or health probes", async () => {
    const env = envWithPrepare(() => ({ first: async () => ({ ok: 1 }) }) as D1PreparedStatementLike);
    const log = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      expect((await handleRequest(new Request("https://example.test/health", { method: "POST" }), env)).status).toBe(405);
      expect((await handleRequest(new Request("https://example.test/ready"), env)).status).toBe(200);
      expect((await handleRequest(new Request("https://example.test/health"), env)).status).toBe(200);
      expect(log).not.toHaveBeenCalled();
    } finally {
      log.mockRestore();
    }
  });

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
