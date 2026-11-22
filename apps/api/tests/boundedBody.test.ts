import { describe, expect, it } from "vitest";
import { readBoundedBody } from "../src/boundedBody";
import { parseProjectInput } from "../src/projectAccess";
import { parseApplicantProfileInput } from "../src/applicantProfile";
import { parseWatchEnabled } from "../src/watchAccess";
import { handleRequest } from "../src/index";
import type { Env } from "../src/env";

function streamed(chunks: Uint8Array[], declared?: string): { request: Request; pulls: () => number } {
  let index = 0;
  const request = new Request("https://example.test/projects", {
    method: "POST",
    headers: declared === undefined ? {} : { "content-length": declared },
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

  it("returns a safe 413 at the API boundary without touching persistence", async () => {
    const env = {
      ENVIRONMENT: "local",
      DB: { prepare() { throw new Error("DB touched"); }, batch() { throw new Error("DB touched"); } },
    } as unknown as Env;
    const { request } = streamed([bytes("x".repeat(16 * 1024)), bytes("y")], "1");
    const response = await handleRequest(request, env);
    expect(response.status).toBe(413);
    expect(await response.json()).toEqual({ error: "REQUEST_TOO_LARGE" });
  });

  it("retains the public 413 contract for project, profile and watch parsers", async () => {
    for (const [parse, limit] of [
      [parseProjectInput, 16 * 1024],
      [parseApplicantProfileInput, 16 * 1024],
      [parseWatchEnabled, 4096],
    ] as const) {
      const { request } = streamed([bytes(" ".repeat(limit)), bytes("x")], "1");
      await expect(parse(request)).rejects.toMatchObject({ code: "REQUEST_TOO_LARGE", status: 413 });
    }
    expect(await parseWatchEnabled(streamed([bytes('{"enabled":true}')]).request)).toBe(true);
  });
});
