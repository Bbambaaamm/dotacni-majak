import type { Env } from "./env";
import { resolvePublicProjectShare } from "./share";

function json(body: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json; charset=utf-8");
  if (!headers.has("cache-control")) {
    headers.set("cache-control", "no-store");
  }
  return new Response(JSON.stringify(body), { ...init, headers });
}

function sharedProjectToken(pathname: string): string | null {
  const match = pathname.match(/^\/share\/([^/]+)$/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
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

  const shareToken = sharedProjectToken(url.pathname);
  if (shareToken !== null) {
    const project = await resolvePublicProjectShare(shareToken, env);
    const headers = {
      "cache-control": "private, no-store",
      "x-robots-tag": "noindex, nofollow",
      "referrer-policy": "no-referrer",
    };
    if (!project) {
      // Unknown, malformed, revoked and expired tokens intentionally collapse
      // to the same external response to avoid project-existence leakage.
      return json({ error: "SHARE_NOT_FOUND" }, { status: 404, headers });
    }
    return json({ project }, { status: 200, headers });
  }

  return json({ error: "NOT_FOUND" }, { status: 404 });
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, env);
  },
};
