import { describe, expect, it, vi } from "vitest";
import { readBoundedBody } from "../src/boundedBody";
import { parseProjectInput, parseShareOptions } from "../src/projectAccess";
import { parseApplicantProfileInput } from "../src/applicantProfile";
import { parseWatchEnabled } from "../src/watchAccess";
import { handleRequest } from "../src/index";
import { BODY_LIMIT_BYTES } from "../src/bodyPolicy";
import type { Env } from "../src/env";

function streamed(
  chunks: Uint8Array[], declared?: string, path = "/projects", authorization?: string,
): { request: Request; pulls: () => number } {
  let index = 0;
  const request = new Request(`https://example.test${path}`, {
    method: "POST",
    headers: {
      ...(declared === undefined ? {} : { "content-length": declared }),
      ...(authorization === undefined ? {} : { authorization }),
    },
    body: new ReadableStream<Uint8Array>({
      pull(controller) {
        if (index === chunks.length) controller.close();
        else controller.enqueue(chunks[index++]);
      },
    }, { highWaterMark: 0 }),
    duplex: "half",
  } as RequestInit & { duplex: "half" });
  return { request, pulls: () => index };
}

const bytes = (text: string) => new TextEncoder().encode(text);
const tooLarge = () => new Error("REQUEST_TOO_LARGE");

describe("bounded streaming request bodies", () => {
  it("declares the existing default and explicit endpoint overrides", () => {
    expect(BODY_LIMIT_BYTES).toEqual({
      project: 16 * 1024,
      profile: 16 * 1024,
      share: 16 * 1024,
      watch: 4 * 1024,
      workspace: 4 * 1024,
    });
  });

  it("rejects a declared oversize body without consuming its stream", async () => {
    const { request, pulls } = streamed([bytes("ok")], "4097");
    await expect(readBoundedBody(request, 4096, tooLarge)).rejects.toThrow("REQUEST_TOO_LARGE");
    // The runtime may prefetch one chunk while constructing the Request; no reader is acquired.
    expect(request.bodyUsed).toBe(false);
    expect(pulls()).toBeLessThanOrEqual(1);
  });

  it("stops on the first over-limit chunk despite a falsely small length header", async () => {
    const { request, pulls } = streamed([bytes("x".repeat(2048)), bytes("y".repeat(2049)), bytes("secret")], "1");
    await expect(readBoundedBody(request, 4096, tooLarge)).rejects.toThrow("REQUEST_TOO_LARGE");
    expect(pulls()).toBeLessThan(3);
  });

  it("counts UTF-8 bytes and preserves multibyte characters split across chunks", async () => {
    const euro = bytes("€");
    const { request } = streamed([bytes("a".repeat(4093)), euro.subarray(0, 1), euro.subarray(1)]);
    expect(await readBoundedBody(request, 4096, tooLarge)).toBe("a".repeat(4093) + "€");
    const oversize = streamed([bytes("a".repeat(4094)), euro]);
    await expect(readBoundedBody(oversize.request, 4096, tooLarge)).rejects.toThrow("REQUEST_TOO_LARGE");
  });

  it("returns a safe 413 for declared and streamed overflow in both endpoint classes", async () => {
    const owner = "S".repeat(43);
    const projectId = `prj_${"a".repeat(32)}`;
    const prepare = vi.fn((query: string) => {
      if (!query.includes("FROM project_owner_capabilities")) throw new Error("Unexpected DB read");
      return { bind() { return this; }, async first() { return { ok: 1 }; } };
    });
    const batch = vi.fn(() => { throw new Error("DB mutation attempted"); });
    const env = { ENVIRONMENT: "local", DB: { prepare, batch } } as unknown as Env;
    const routes = [
      { path: "/projects", limit: BODY_LIMIT_BYTES.project, authorization: undefined, expectedReads: 0 },
      { path: `/projects/${projectId}/workspaces`, limit: BODY_LIMIT_BYTES.workspace,
        authorization: `Bearer ${owner}`, expectedReads: 1 },
    ];

    for (const route of routes) {
      for (const mode of ["declared", "streamed"] as const) {
        prepare.mockClear();
        batch.mockClear();
        const secret = `private-${owner}`;
        const chunks = mode === "declared"
          ? [bytes(secret)]
          : [bytes("x".repeat(route.limit)), bytes(secret)];
        const { request } = streamed(chunks, mode === "declared" ? String(route.limit + 1) : "1",
          route.path, route.authorization);
        const response = await handleRequest(request, env);
        expect(response.status).toBe(413);
        const responseText = await response.text();
        expect(JSON.parse(responseText)).toEqual({ error: "REQUEST_TOO_LARGE" });
        expect(responseText).not.toContain(secret);
        expect(prepare).toHaveBeenCalledTimes(route.expectedReads);
        expect(batch).not.toHaveBeenCalled();
      }
    }
  });

  it("retains the public 413 contract for project, profile, share and watch parsers", async () => {
    for (const [parse, limit] of [
      [parseProjectInput, BODY_LIMIT_BYTES.project],
      [parseApplicantProfileInput, BODY_LIMIT_BYTES.profile],
      [parseShareOptions, BODY_LIMIT_BYTES.share],
      [parseWatchEnabled, BODY_LIMIT_BYTES.watch],
    ] as const) {
      const { request } = streamed([bytes(" ".repeat(limit)), bytes("x")], "1");
      await expect(parse(request)).rejects.toMatchObject({ code: "REQUEST_TOO_LARGE", status: 413 });
    }
    expect(await parseWatchEnabled(streamed([bytes('{"enabled":true}')]).request)).toBe(true);
  });

  it("defaults only absent or empty-object share options", async () => {
    const parse = (body?: string) => parseShareOptions(new Request("https://example.test", {
      method: "POST",
      ...(body === undefined ? {} : { body }),
    }));
    await expect(parse()).resolves.toBe(30);
    await expect(parse("{}")).resolves.toBe(30);
    for (const body of ["null", "", "   \n\t"]) {
      await expect(parse(body)).rejects.toMatchObject({
        code: "INVALID_SHARE_OPTIONS", status: 400,
      });
    }
    for (const days of [1, 365]) {
      await expect(parse(JSON.stringify({ expiresInDays: days }))).resolves.toBe(days);
    }
    await expect(parse('{"expiresInDays":null}')).rejects.toMatchObject({
      code: "INVALID_SHARE_EXPIRY", status: 400,
    });
    await expect(parse('{"expiresInDays":30,"unexpectedSecret":"private"}'))
      .rejects.toMatchObject({ code: "UNKNOWN_SHARE_FIELD", status: 400 });
  });

  it("checks workspace authorization before rejecting an oversized body", async () => {
    const projectId = `prj_${"a".repeat(32)}`;
    const { request } = streamed([bytes("secret")], String(BODY_LIMIT_BYTES.workspace + 1),
      `/projects/${projectId}/workspaces`);
    const env = {
      ENVIRONMENT: "local",
      DB: { prepare() { throw new Error("DB touched"); }, batch() { throw new Error("DB touched"); } },
    } as unknown as Env;
    const response = await handleRequest(request, env);
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "OWNER_CAPABILITY_INVALID" });
    expect(request.bodyUsed).toBe(false);
  });

  it("returns 408 for a stalled body before project persistence and never echoes credentials", async () => {
    vi.useFakeTimers();
    try {
      const request = new Request("https://example.test/projects", {
        method: "POST",
        body: new ReadableStream<Uint8Array>({ start() { /* no bytes */ } }),
        duplex: "half",
      } as RequestInit & { duplex: "half" });
      const env = {
        ENVIRONMENT: "local",
        DB: { prepare() { throw new Error("DB touched"); }, batch() { throw new Error("DB touched"); } },
      } as unknown as Env;
      const responsePromise = handleRequest(request, env);
      await vi.advanceTimersByTimeAsync(10_000);
      const response = await responsePromise;
      expect(response.status).toBe(408);
      expect(await response.json()).toEqual({ error: "REQUEST_TIMEOUT" });
    } finally {
      vi.useRealTimers();
    }
  });

  it("enforces a total body deadline even when successive chunks arrive", async () => {
    vi.useFakeTimers();
    try {
      let controller!: ReadableStreamDefaultController<Uint8Array>;
      const request = new Request("https://example.test/projects", {
        method: "POST",
        body: new ReadableStream<Uint8Array>({ start(value) { controller = value; } }),
        duplex: "half",
      } as RequestInit & { duplex: "half" });
      const result = readBoundedBody(request, 4096, tooLarge, () => new Error("REQUEST_TIMEOUT"));
      const rejection = expect(result).rejects.toThrow("REQUEST_TIMEOUT");
      controller.enqueue(bytes("a"));
      await vi.advanceTimersByTimeAsync(5_000);
      controller.enqueue(bytes("b"));
      await vi.advanceTimersByTimeAsync(5_000);
      await rejection;
    } finally {
      vi.useRealTimers();
    }
  });
});
