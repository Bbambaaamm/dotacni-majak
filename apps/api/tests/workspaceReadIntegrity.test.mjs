import { afterEach, describe, expect, it } from "vitest";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { handleRequest } from "../src/index";
import { hashOwnerToken } from "../src/projectAccess";

const ROOT = resolve(import.meta.dirname, "../../..");
const PROJECT = "prj_" + "a".repeat(32);
const OWNER = "A".repeat(43);
const databases = [];
afterEach(() => { for (const db of databases.splice(0)) db.close(); });

async function setup() {
  const db = new DatabaseSync(":memory:");
  databases.push(db);
  for (const file of readdirSync(resolve(ROOT, "migrations")).filter(f => f.endsWith(".sql")).sort()) {
    db.exec(readFileSync(resolve(ROOT, "migrations", file), "utf8"));
  }
  db.exec(readFileSync(resolve(ROOT, "tests/e2e/seed.sql"), "utf8"));
  db.prepare(`INSERT INTO projects(id,owner_user_id,natural_language_intent,currency_code,created_at,updated_at)
    VALUES (?,?,'digitalizace obce','CZK','2026-11-19','2026-11-19')`).run(PROJECT, "anonymous:" + PROJECT);
  db.prepare(`INSERT INTO project_owner_capabilities(project_id,token_hash,generation,created_at)
    VALUES (?,?,1,'2026-11-19')`).run(PROJECT, await hashOwnerToken(OWNER));
  let failTaskRead = false;
  const env = {
    ENVIRONMENT: "local", RAW: { async head() { return null; } }, SEARCH: { async describe() {} },
    DB: {
      prepare(sql) {
        let values = [];
        const statement = {
          bind(...args) { values = args; return statement; },
          async first() { return db.prepare(sql).get(...values) ?? null; },
          async all() {
            if (failTaskRead && sql.includes("FROM workspace_tasks")) return { success: false };
            return { success: true, results: db.prepare(sql).all(...values) };
          },
          async run() { const result = db.prepare(sql).run(...values); return { success: true, meta: { changes: Number(result.changes) } }; },
        };
        return statement;
      },
      async batch(statements) {
        db.exec("BEGIN");
        try { const result = []; for (const statement of statements) result.push(await statement.run()); db.exec("COMMIT"); return result; }
        catch (error) { db.exec("ROLLBACK"); throw error; }
      },
    },
  };
  const headers = { authorization: "Bearer " + OWNER, "content-type": "application/json" };
  const created = await handleRequest(new Request(`https://example.invalid/projects/${PROJECT}/workspaces`, {
    method: "POST", headers, body: JSON.stringify({ grantCallId: "grant:e2e:open" }),
  }), env);
  expect(created.status).toBe(201);
  const result = await created.json();
  const read = () => handleRequest(new Request(`https://example.invalid/projects/${PROJECT}/workspaces/${result.workspace.id}`, { headers }), env);
  return { db, read, failRead: () => { failTaskRead = true; } };
}

describe("workspace checklist integrity over real SQLite migrations", () => {
  it("returns persisted blockers for a healthy workspace", async () => {
    const { read } = await setup();
    const response = await read();
    expect(response.status).toBe(200);
    const result = await response.json();
    expect(result.readiness.state).toBe("BLOCKED");
    expect(result.readiness.totalCount).toBeGreaterThanOrEqual(3);
    expect(result.readiness.blockingOpenCount).toBeGreaterThanOrEqual(3);
  });

  it("rejects a missing checklist instead of fabricating READY with 100% completion", async () => {
    const { db, read } = await setup();
    db.exec("DELETE FROM workspace_tasks");
    const response = await read();
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "WORKSPACE_UNAVAILABLE" });
  });

  it("rejects an unsuccessful task query even when the transport does not throw", async () => {
    const { read, failRead } = await setup();
    failRead();
    const response = await read();
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "WORKSPACE_UNAVAILABLE" });
  });
});
