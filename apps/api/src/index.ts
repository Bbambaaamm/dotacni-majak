import type { Env } from "./env";
import {
  ApiInputError,
  bearerToken,
  createAnonymousProject,
  createProjectShare,
  parseProjectInput,
  parseShareOptions,
  revokeOwnerCapability,
  revokeProjectShare,
  rotateOwnerCapability,
} from "./projectAccess";
import { resolvePublicProjectShare } from "./share";
import { SearchInputError, searchGrants } from "./search";

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

function projectSharePath(pathname: string): { projectId: string; shareId?: string } | null {
  const match = pathname.match(/^\/projects\/(prj_[a-f0-9]{32})\/shares(?:\/(shr_[a-f0-9]{32}))?$/);
  return match ? { projectId: match[1], shareId: match[2] } : null;
}

function projectOwnerPath(pathname: string): { projectId: string; action: "rotate" | "revoke" } | null {
  const match = pathname.match(/^\/projects\/(prj_[a-f0-9]{32})\/owner\/(rotate|revoke)$/);
  return match ? { projectId: match[1], action: match[2] as "rotate" | "revoke" } : null;
}

export async function handleRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);

  try {
    if ((request.method === "GET" || request.method === "HEAD") && url.pathname === "/health") {
      return json({
        status: "ok",
        service: "dotacni-majak-api",
        environment: env.ENVIRONMENT,
        release: env.RELEASE_SHA ?? "unknown",
      });
    }

    if ((request.method === "GET" || request.method === "HEAD") && url.pathname === "/ready") {
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

    if ((request.method === "GET" || request.method === "HEAD") && url.pathname === "/search") {
      try {
        const limitRaw = url.searchParams.get("limit");
        const limit = limitRaw ? Number.parseInt(limitRaw, 10) : 20;
        const result = await searchGrants(
          env.DB,
          url.searchParams.get("intent"),
          Number.isFinite(limit) ? limit : 20,
        );
        return json(result, { status: 200 });
      } catch (error) {
        if (error instanceof SearchInputError) {
          return json({ error: error.code }, { status: error.status });
        }
        return json(
          { error: "SEARCH_UNAVAILABLE" },
          { status: 503 },
        );
      }
    }

    const shareToken = sharedProjectToken(url.pathname);
    if ((request.method === "GET" || request.method === "HEAD") && shareToken !== null) {
      const project = await resolvePublicProjectShare(shareToken, env);
      const headers = {
        "cache-control": "private, no-store",
        "x-robots-tag": "noindex, nofollow",
        "referrer-policy": "no-referrer",
      };
      if (!project) {
        return json({ error: "SHARE_NOT_FOUND" }, { status: 404, headers });
      }
      return json({ project }, { status: 200, headers });
    }

    if (request.method === "POST" && url.pathname === "/projects") {
      const input = await parseProjectInput(request);
      const issued = await createAnonymousProject(input, env);
      return json(
        {
          projectId: issued.projectId,
          ownerCapability: issued.ownerCapability,
          warning: "Owner capability is shown once. Losing it may make an anonymous project unmanageable.",
        },
        { status: 201 },
      );
    }

    const sharePath = projectSharePath(url.pathname);
    if (sharePath && request.method === "POST" && !sharePath.shareId) {
      const owner = bearerToken(request);
      if (!owner) return json({ error: "OWNER_CAPABILITY_INVALID" }, { status: 404 });
      const expiresInDays = await parseShareOptions(request);
      const issued = await createProjectShare(
        sharePath.projectId,
        owner,
        env,
        { expiresInDays },
      );
      return json(
        {
          shareId: issued.shareId,
          token: issued.token,
          sharePath: `/s/${issued.token}`,
          expiresAt: issued.expiresAt,
        },
        { status: 201 },
      );
    }

    if (sharePath?.shareId && request.method === "DELETE") {
      const owner = bearerToken(request);
      if (owner) {
        await revokeProjectShare(
          sharePath.projectId,
          sharePath.shareId,
          owner,
          env,
        );
      }
      return new Response(null, {
        status: 204,
        headers: { "cache-control": "no-store" },
      });
    }

    const ownerPath = projectOwnerPath(url.pathname);
    if (ownerPath && request.method === "POST" && ownerPath.action === "rotate") {
      const owner = bearerToken(request);
      if (!owner) return json({ error: "OWNER_CAPABILITY_INVALID" }, { status: 404 });
      const next = await rotateOwnerCapability(ownerPath.projectId, owner, env);
      return json({ ownerCapability: next }, { status: 200 });
    }

    if (ownerPath && request.method === "DELETE" && ownerPath.action === "revoke") {
      const owner = bearerToken(request);
      if (owner) await revokeOwnerCapability(ownerPath.projectId, owner, env);
      return new Response(null, {
        status: 204,
        headers: { "cache-control": "no-store" },
      });
    }

    if (["GET", "HEAD", "POST", "DELETE"].includes(request.method)) {
      return json({ error: "NOT_FOUND" }, { status: 404 });
    }
    return json(
      { error: "METHOD_NOT_ALLOWED" },
      { status: 405, headers: { allow: "GET, HEAD, POST, DELETE" } },
    );
  } catch (error) {
    if (error instanceof ApiInputError) {
      return json({ error: error.code }, { status: error.status });
    }
    return json({ error: "INTERNAL_ERROR" }, { status: 500 });
  }
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, env);
  },
};
