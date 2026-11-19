import { describe, expect, it } from "vitest";
import { handleRequest } from "../src/index";
import type { Env } from "../src/env";
import { workspacePath } from "../src/workspaceAccess";

const projectId = `prj_${"a".repeat(32)}`;
const owner = "B".repeat(43);
const env: Env = {
  ENVIRONMENT: "local",
  DB: {
    prepare() { throw new Error("DB must not be touched"); },
    batch() { throw new Error("DB must not be touched"); },
  },
  RAW: { async head() { return null; } },
  SEARCH: { async describe() { return null; } },
};

describe("workspace API boundary", () => {
  it("matches only exact owner-scoped paths", () => {
    expect(workspacePath(`/projects/${projectId}/workspaces`)).toEqual({projectId, workspaceId: undefined, taskId: undefined});
    expect(workspacePath(`/projects/${projectId}/workspaces/nope`)).toBeNull();
    expect(workspacePath(`/projects/${projectId}/workspaces/../../share`)).toBeNull();
  });
  it("returns private 404 before reading body or DB without bearer", async () => {
    const response = await handleRequest(new Request(`https://example.test/projects/${projectId}/workspaces`, {
      method: "POST", body: "not json",
    }), env);
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({error: "OWNER_CAPABILITY_INVALID"});
  });
  it("rejects malformed owner bearer without touching DB", async () => {
    const response = await handleRequest(new Request(`https://example.test/projects/${projectId}/workspaces`, {
      headers: {authorization: `Bearer ${owner.slice(0, 10)}`},
    }), env);
    expect(response.status).toBe(404);
  });
  it("rejects a valid-shaped foreign owner before parsing malformed POST and PATCH bodies", async () => {
    const privateEnv: Env = {
      ...env,
      DB: {
        prepare() { return {
          bind() { return this; },
          async first() { return null; },
          async all() { throw new Error("unauthorized read"); },
          async run() { throw new Error("unauthorized write"); },
        }; },
        batch() { throw new Error("unauthorized write"); },
      },
    };
    const paths = [
      { path: `/projects/${projectId}/workspaces`, method: "POST" },
      { path: `/projects/${projectId}/workspaces/wsp_${"a".repeat(32)}/tasks/tsk_${"b".repeat(32)}`, method: "PATCH" },
    ];
    for (const { path, method } of paths) {
      const response = await handleRequest(new Request(`https://example.test${path}`, {
        method, headers: { authorization: `Bearer ${owner}` }, body: "not json",
      }), privateEnv);
      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({ error: "OWNER_CAPABILITY_INVALID" });
    }
  });
});
