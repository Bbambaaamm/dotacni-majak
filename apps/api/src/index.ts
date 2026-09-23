import type { Env } from "./env";

function json(body: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json; charset=utf-8");
  headers.set("cache-control", "no-store");
  return new Response(JSON.stringify(body), { ...init, headers });
}

export async function handleRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  if (request.method !== "GET" && request.method !== "HEAD") {
    return json(
      { error: "METHOD_NOT_ALLOWED" },
      { status: 405, headers: { allow: "GET, HEAD" } },
    );
  }

  if (url.pathname === "/health") {
    return json({
      status: "ok",
      service: "dotacni-majak-api",
      environment: env.ENVIRONMENT,
      release: env.RELEASE_SHA ?? "unknown",
    });
  }

  if (url.pathname === "/ready") {
    try {
      const row = await env.DB.prepare("SELECT 1 AS ok").first<{ ok: number }>();
      if (row?.ok !== 1) {
        return json({ status: "not_ready", reason: "D1_CHECK_FAILED" }, { status: 503 });
      }
      return json({ status: "ready" });
    } catch {
      return json({ status: "not_ready", reason: "D1_UNAVAILABLE" }, { status: 503 });
    }
  }

  return json({ error: "NOT_FOUND" }, { status: 404 });
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, env);
  },
};
