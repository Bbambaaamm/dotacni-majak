import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";

test("Dotáhne: detail → project → persisted owner workspace → trusted version diff → failed RAW", async ({ page }) => {
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await page.locator(".sticky-action").getByRole("link", { name: "Přidat k projektu" }).click();
  await expect(page).toHaveURL(/\/projekty\?.*grantCallId=/);
  await page.getByLabel("Název projektu").fill("E2E obec");
  await page.getByRole("button", { name: "Vytvořit projekt" }).click();
  await expect(page.getByRole("heading", { name: "Příprava žádosti · Dotáhne" })).toBeVisible();
  await expect(page.getByText("Výchozí verze:")).toContainText("gcv-e2e-open");
  await expect(page.getByText(/Co udělat teď\?/)).toBeVisible();
  await expect(page.getByText(/ELIGIBILITY_UNKNOWN/)).toBeVisible();
  await expect(page.getByText(/Toto není posouzení způsobilosti/)).toBeVisible();
  const eligibility = page.getByRole("region", { name: "Způsobilost pro vybranou výzvu" });
  await expect(eligibility.getByRole("status")).toContainText("Chybí údaj pro posouzení (UNKNOWN)");
  const owner = await page.evaluate(() => JSON.parse(sessionStorage.getItem("dotacni-majak:active-project") || "null") as {projectId: string; ownerCapability: string});
  const base = `/api/projects/${owner.projectId}/workspaces`;
  expect((await page.request.get(base)).status()).toBe(404);
  expect((await page.request.get(base, { headers: { authorization: `Bearer ${"x".repeat(43)}` } })).status()).toBe(404);
  expect((await page.request.post(base, { headers: { authorization: `Bearer ${"x".repeat(43)}` }, data: "not json" })).status()).toBe(404);
  const headers = { authorization: `Bearer ${owner.ownerCapability}` };
  const list = await page.request.get(base, { headers });
  expect(list.status()).toBe(200);
  const [{ id }] = (await list.json()).workspaces as Array<{id: string}>;
  const first = await page.request.get(`${base}/${id}`, { headers });
  const initial = await first.json();
  expect(initial.workspace.baselineGrantVersionId).toBe("gcv-e2e-open");
  expect(initial.versionReview).toMatchObject({
    currentCapturedAt: "2026-09-26T20:00:00Z", sourceCheckedAt: "2026-10-01T09:00:00Z",
  });
  const required = initial.tasks.find((task: {title: string}) => task.title === "Připravit rozpočet projektu");
  const conditional = initial.tasks.find((task: {title: string}) => task.title === "Ověřit potřebu stavebního povolení");
  expect(conditional.status).toBe("BLOCKED");
  expect((await page.request.patch(`${base}/${id}/tasks/${conditional.id}`, { headers, data: { status: "DONE" } })).status()).toBe(404);
  const marked = await page.request.patch(`${base}/${id}/tasks/${required.id}`, { headers, data: { status: "DONE" } });
  expect(marked.status()).toBe(200);
  expect((await marked.json()).readiness.state).toBe("BLOCKED");
  expect((await page.request.patch(`${base}/${id}/tasks/${required.id}`, { data: { status: "DONE" } })).status()).toBe(404);
  expect((await page.request.post(base, { headers, data: { grantCallId: "grant:e2e:open" } })).status()).toBe(201);
  expect((await (await page.request.get(base, { headers })).json()).workspaces).toHaveLength(1);
  expect((await page.request.get(`${base}/${id}`)).status()).toBe(404);
  const run = (action: string) => execFileSync("python3", ["scripts/e2e_watch_flow.py", action], {
    encoding: "utf8", cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: ["pipelines/ingestion/src", "packages/source-sdk/src", "packages/watches/src", "packages/notifications/src", "packages/search/src", "packages/eligibility/src", "packages/finance/src", "packages/change-detection/src", "packages/workspace/src", "packages/checklist/src"].join(":") },
  });
  expect(run("workspace-update")).toContain("RAW_EVIDENCE_VERIFIED");
  let releaseRefresh!: () => void;
  const refreshHeld = new Promise<void>((resolve) => { releaseRefresh = resolve; });
  await page.route(`**${base}/${id}`, async (route) => {
    if (route.request().method() === "GET") await refreshHeld;
    await route.continue();
  });
  let releaseWrite!: () => void;
  const writeHeld = new Promise<void>((resolve) => { releaseWrite = resolve; });
  await page.route("**/api/applicant-profile", async (route) => {
    if (route.request().method() === "PUT") await writeHeld;
    await route.continue();
  });
  let eligibilityLoads = 0;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen/eligibility", async (route) => {
    eligibilityLoads++;
    await route.continue();
  });
  await page.getByRole("button", { name: "Obnovit přípravu a změny" }).click();
  await eligibility.getByLabel("Typ žadatele").selectOption("MUNICIPALITY");
  await eligibility.getByRole("button", { name: "Uložit odpověď a přepočítat" }).click();
  releaseRefresh();
  await expect(eligibility.getByRole("status")).toContainText("Výsledek vyžaduje ověření, nejde o zamítnutí");
  await expect.poll(() => eligibilityLoads).toBeGreaterThan(0);
  const beforeCommit = eligibilityLoads;
  releaseWrite();
  await expect.poll(() => eligibilityLoads).toBeGreaterThan(beforeCommit);
  await expect(eligibility.getByRole("status")).toContainText("Výsledek vyžaduje ověření, nejde o zamítnutí");
  const refreshed = await (await page.request.get(`${base}/${id}`, { headers })).json();
  expect(refreshed.workspace.currentGrantVersionId).not.toBe("gcv-e2e-open");
  await expect(eligibility).toContainText(refreshed.workspace.currentGrantVersionId);
  await expect(eligibility.getByRole("heading", { name: "Jaký typ žadatele bude žádost podávat?" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Podmínky výzvy se od zahájení přípravy změnily" })).toBeVisible();
  expect(refreshed.versionReview.sourceCheckedAt).toBeTruthy();
  await expect(page.getByText(/Poslední pozorování záznamu u zdroje:/)).toContainText(refreshed.versionReview.sourceCheckedAt);
  await expect(page.getByText(/Poslední pozorování záznamu u zdroje:/)).toContainText(refreshed.versionReview.currentCapturedAt);
  await expect(page.getByText(/Pozorování není ověření podmínek verze/)).toBeVisible();
  await expect(page.getByLabel("Změny výzvy")).toContainText("2028-01-31T23:59:59Z");
  await expect(page.getByLabel("Změny výzvy")).toContainText("2027-12-31T23:59:59Z");
  await expect(page.getByText("Zkontrolujte změny podmínek výzvy vůči původní verzi")).toBeVisible();
  await expect(page.getByText("Upozornění na změny verzí: 1")).toBeVisible();
  await expect(page.getByRole("link", { name: /Zkontrolovat zdroj/ })).toHaveAttribute("href", "https://example.invalid/e2e/open");
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => ({
    width: window.innerWidth,
    overflow: Array.from(document.querySelectorAll("header, header nav, footer, main, .projects-page, .owner-secret, .share-card"))
      .map(element => ({ element: element.className, right: Math.round(element.getBoundingClientRect().right) }))
      .filter(element => element.right > window.innerWidth),
    pageOverflow: document.documentElement.scrollWidth > window.innerWidth,
  }))).toEqual({ width: 390, overflow: [], pageOverflow: false });
  const mobileAccessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(mobileAccessibility.violations).toEqual([]);
  const second = await (await page.request.get(`${base}/${id}`, { headers })).json();
  expect(second.workspace.baselineGrantVersionId).toBe("gcv-e2e-open");
  expect(second.workspace.currentGrantVersionId).not.toBe("gcv-e2e-open");
  expect(second.versionReview.alerts).toHaveLength(1);
  const deadlineChange = second.versionReview.diff.find((change: {field: string}) => change.field === "deadlines.application_close");
  expect(deadlineChange?.evidenceId).toBeTruthy();
  const grantDetail = await (await page.request.get("/api/grants/grant%3Ae2e%3Aopen")).json();
  const evidence = grantDetail.evidence.find((item: {id: string}) => item.id === deadlineChange.evidenceId);
  expect(evidence?.fieldPath).toBe("/submission_close_at");
  expect(evidence?.sourceUrl).toBe("https://example.invalid/e2e/open");
  expect(second.versionReview.diff.some((change: {field: string}) => change.field.includes("Removed"))).toBe(false);
  expect(run("workspace-fail")).toContain("WORKSPACE_FAILED_RAW_LAST_GOOD_PRESERVED");
  const after = await (await page.request.get(`${base}/${id}`, { headers })).json();
  expect(after.versionReview.alerts).toHaveLength(1);
  expect(after.workspace.currentGrantVersionId).toBe(second.workspace.currentGrantVersionId);
  await page.route(`**${base}/${id}`, async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"D1_UNAVAILABLE"}' });
  });
  await page.getByRole("button", { name: "Obnovit přípravu a změny" }).click();
  await expect(page.getByText(/Zastaralé kroky nelze měnit/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Označit jako hotové" })).toHaveCount(0);
  await page.unroute(`**${base}/${id}`);
  await page.getByRole("button", { name: "Zkusit načíst přípravu znovu" }).click();
  await expect(page.getByRole("heading", { name: "Podmínky výzvy se od zahájení přípravy změnily" })).toBeVisible();
});
