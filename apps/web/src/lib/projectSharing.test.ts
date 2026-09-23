import { describe, expect, it, vi } from "vitest";

import {
  ProjectSharingError,
  createAnonymousProject,
  createReadOnlyShare,
  revokeReadOnlyShare,
} from "./projectSharing";

const PROJECT_ID = "prj_" + "a".repeat(32);
const SHARE_ID = "shr_" + "b".repeat(32);
const OWNER = "O".repeat(43);
const TOKEN = "S".repeat(43);

describe("project sharing mutations", () => {
  it("creates project without persisting or sending an owner id", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({
        projectId: PROJECT_ID,
        ownerCapability: OWNER,
      }), { status: 201, headers: { "content-type": "application/json" } }),
    );
    const result = await createAnonymousProject(
      { title: "Kurty", naturalLanguageIntent: "Rekonstrukce kurtů" },
      fetcher,
      "https://api.example.com",
    );
    expect(result.projectId).toBe(PROJECT_ID);
    const [, init] = fetcher.mock.calls[0];
    expect(String(init?.body)).not.toContain("owner_user_id");
  });

  it("uses owner capability only in Authorization for share creation", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({
        shareId: SHARE_ID,
        token: TOKEN,
        sharePath: `/s/${TOKEN}`,
        expiresAt: "2026-10-23T20:00:00.000Z",
      }), { status: 201, headers: { "content-type": "application/json" } }),
    );
    await createReadOnlyShare(PROJECT_ID, OWNER, 30, fetcher, "https://api.example.com");
    const [url, init] = fetcher.mock.calls[0];
    expect(String(url)).toContain(`/projects/${PROJECT_ID}/shares`);
    expect(new Headers(init?.headers).get("authorization")).toBe(`Bearer ${OWNER}`);
    expect(String(init?.body)).not.toContain(OWNER);
  });

  it("revocation treats 204 as success", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    await expect(
      revokeReadOnlyShare(PROJECT_ID, SHARE_ID, OWNER, fetcher, "https://api.example.com"),
    ).resolves.toBeUndefined();
  });

  it("rejects malformed owner capability before request", async () => {
    const fetcher = vi.fn<typeof fetch>();
    await expect(
      createReadOnlyShare(PROJECT_ID, "tiny", 30, fetcher, "https://api.example.com"),
    ).rejects.toBeInstanceOf(ProjectSharingError);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
