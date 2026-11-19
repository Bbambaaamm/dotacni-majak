import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";

test("unavailable facets show no counts, allow manual filters, and preserve first-page facets on load-more", async ({ page }) => {
  const result = (id: string) => ({ grantCallVersionId: id, grantCallId: id,
    title: `Facet test ${id}`, summary: "", status: "OPEN", submissionCloseAt: null,
    providerName: "Manual provider", officialDetailUrl: null, matchKind: "DIRECT" });
  await page.route("**/api/search?*", async (route) => {
    const url = new URL(route.request().url());
    const provider = url.searchParams.get("provider");
    const cursor = url.searchParams.get("cursor");
    const facets = provider ? null : cursor ? null : {
      status: { OPEN: 2, PLANNED: 0, ANNOUNCED: 0 },
      deadline: { KNOWN: 0, UNKNOWN: 2 },
      providers: [{ name: "Manual provider", count: 2 }], providersTruncated: false,
    };
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      intent: "facet-browser-test", indexState: "READY", expandedTerms: [],
      results: [result(cursor ? "v-2" : "v-1")], nextCursor: cursor || provider ? null : "page-2", facets,
    }) });
  });
  await page.goto("/hledat?intent=facet-browser-test");
  await expect(page.getByLabel("Stav výzvy").locator('option[value="OPEN"]')).toHaveText("Lze podat žádost (2)");
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(2);
  await expect(page.getByLabel("Stav výzvy").locator('option[value="OPEN"]')).toHaveText("Lze podat žádost (2)");
  await page.getByLabel("Přesný název poskytovatele").fill("Manual provider");
  await page.getByRole("button", { name: "Použít poskytovatele" }).click();
  await expect(page.getByText("Počty pro filtry nejsou dostupné", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Stav výzvy").locator('option[value="OPEN"]')).toHaveText("Lze podat žádost");
  await expect(page.getByLabel("Termín podání").locator('option[value="UNKNOWN"]')).toHaveText("Termín neuveden (UNKNOWN)");
  await expect(page.locator("#search-providers option")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Zrušit filtr Poskytovatel: Manual provider" })).toBeVisible();
});

test("real D1 search loads more than 20 distinct results and retries a failed later page", async ({ page }) => {
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByText("Načteno 20 výsledků", { exact: false })).toBeVisible();
  let failOnce = true;
  await page.route("**/api/search?*cursor=*", async (route) => {
    if (failOnce) {
      failOnce = false;
      await route.fulfill({ status: 503, contentType: "application/json",
        body: JSON.stringify({ error: "SEARCH_UNAVAILABLE" }) });
    } else {
      await route.continue();
    }
  });
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("alert")).toContainText("Dosud načtené výsledky zůstávají zobrazené");
  await page.getByRole("button", { name: "Zkusit načíst další znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  await expect(page.getByText("Načteno 25 výsledků", { exact: false })).toBeVisible();
  expect(new Set(await page.locator(".grant-card h3").allTextContents()).size).toBe(25);
});

test("global status finds a later-page planned result and rejects a changed cursor", async ({ page, request }) => {
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toHaveCount(0);
  await page.getByLabel("Stav výzvy").selectOption("PLANNED");
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await expect(page.getByText(/Stav, dostupnost termínu, uzávěrka nejdříve, uzávěrka nejpozději a přesný název poskytovatele se filtrují napříč/)).toBeVisible();
  await page.goto("/hledat?intent=digitalizace%20obce");
  await page.getByLabel("Přesný název poskytovatele").fill("E2E test provider A");
  await page.getByRole("button", { name: "Použít poskytovatele" }).click();
  await page.getByLabel("Stav výzvy").selectOption("PLANNED");
  await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByLabel("Přesný název poskytovatele")).toHaveValue("");

  const first = await request.get("/api/search?intent=strankovani&limit=1&status=OPEN");
  expect(first.status()).toBe(200);
  const { nextCursor } = await first.json() as { nextCursor: string | null };
  expect(nextCursor).toBeTruthy();
  const changed = await request.get(`/api/search?intent=strankovani&limit=1&status=PLANNED&cursor=${encodeURIComponent(nextCursor!)}`);
  expect(changed.status()).toBe(400);
  expect(await changed.json()).toEqual({ error: "INVALID_CURSOR" });
  const closed = await request.get("/api/search?intent=strankovani&status=CLOSED");
  expect(closed.status()).toBe(400);
  expect(await closed.json()).toEqual({ error: "INVALID_STATUS" });
  const defaultSearch = await request.get("/api/search?intent=rekonstrukce%20tenisov%C3%BDch%20kurt%C5%AF");
  expect((await defaultSearch.json()).results).toEqual([]);
});

test("global deadline availability finds a later-page call and remains bound to the cursor", async ({ page, request }) => {
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toHaveCount(0);
  await page.getByLabel("Termín podání").selectOption("KNOWN");
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await page.getByLabel("Stav výzvy").selectOption("OPEN");
  await expect(page.getByText("Zvoleným filtrům neodpovídá žádná aktivní výzva pro váš záměr. Zkuste jiného poskytovatele nebo zrušte filtry.")).toBeVisible();
  await page.getByRole("button", { name: "Zrušit filtr Stav: Lze podat žádost" }).click();
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
  await page.getByLabel("Termín podání").selectOption("UNKNOWN");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toHaveCount(0);
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(24);
  await expect(page.getByRole("heading", { name: "E2E stránkování 24" })).toBeVisible();

  const response = await request.get("/api/search?intent=strankovani&limit=1&deadline=UNKNOWN");
  expect(response.status()).toBe(200);
  const { nextCursor } = await response.json() as { nextCursor: string | null };
  expect(nextCursor).toBeTruthy();
  const changed = await request.get(`/api/search?intent=strankovani&limit=1&deadline=KNOWN&cursor=${encodeURIComponent(nextCursor!)}`);
  expect(changed.status()).toBe(400);
  expect(await changed.json()).toEqual({ error: "INVALID_CURSOR" });
  const invalid = await request.get("/api/search?intent=strankovani&deadline=KNOWN&deadline=UNKNOWN");
  expect(invalid.status()).toBe(400);
  expect(await invalid.json()).toEqual({ error: "INVALID_DEADLINE" });
});

test("provider absent from first page is found by exact name across real D1 and cursor is bound", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.locator("#search-providers option[value='E2E test provider B']")).toHaveCount(1);
  await expect(page.getByText("E2E test provider B (1)")).toBeVisible();
  await page.getByLabel("Přesný název poskytovatele").fill("E2E test provider B");
  await page.getByLabel("Přesný název poskytovatele").press("Enter");
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Zrušit filtr Poskytovatel: E2E test provider B" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.getByRole("button", { name: "Zrušit filtr Poskytovatel: E2E test provider B" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  const first = await request.get("/api/search?intent=strankovani&limit=1&provider=E2E%20test%20provider%20A");
  expect(first.status()).toBe(200);
  const { nextCursor } = await first.json() as { nextCursor: string | null };
  expect(nextCursor).toBeTruthy();
  const changed = await request.get(`/api/search?intent=strankovani&limit=1&provider=E2E%20test%20provider%20B&cursor=${encodeURIComponent(nextCursor!)}`);
  expect(changed.status()).toBe(400);
  expect(await changed.json()).toEqual({ error: "INVALID_CURSOR" });
  const duplicate = await request.get("/api/search?intent=strankovani&provider=A&provider=B");
  expect(duplicate.status()).toBe(400);
  expect(await duplicate.json()).toEqual({ error: "INVALID_PROVIDER" });
});

test("real D1 facets count later pages and exclude their own selected dimension", async ({ request }) => {
  const response = await request.get("/api/search?intent=strankovani&limit=1&status=PLANNED&deadline=KNOWN&provider=E2E%20test%20provider%20B");
  expect(response.status()).toBe(200);
  const body = await response.json() as { results: unknown[]; facets: {
    status: Record<string, number>; deadline: Record<string, number>;
    providers: { name: string; count: number }[]; providersTruncated: boolean } };
  expect(body.results).toHaveLength(1);
  expect(body.facets.status).toEqual({ OPEN: 0, PLANNED: 1, ANNOUNCED: 0 });
  expect(body.facets.deadline).toEqual({ KNOWN: 1, UNKNOWN: 0 });
  expect(body.facets.providers).toEqual([{ name: "E2E test provider B", count: 1 }]);
  expect(body.facets.providersTruncated).toBe(false);

  const all = await request.get("/api/search?intent=strankovani&limit=1");
  const allBody = await all.json() as typeof body;
  expect(allBody.results).toHaveLength(1);
  expect(allBody.facets.status).toEqual({ OPEN: 24, PLANNED: 1, ANNOUNCED: 0 });
  expect(allBody.facets.deadline).toEqual({ KNOWN: 1, UNKNOWN: 24 });
  expect(allBody.facets.providers).toEqual([
    { name: "E2E test provider A", count: 24 }, { name: "E2E test provider B", count: 1 },
  ]);
  const status = await request.get("/api/search?intent=strankovani&status=PLANNED");
  expect((await status.json() as typeof body).facets.status).toEqual(allBody.facets.status);
  const deadline = await request.get("/api/search?intent=strankovani&deadline=KNOWN");
  expect((await deadline.json() as typeof body).facets.deadline).toEqual(allBody.facets.deadline);
  const provider = await request.get("/api/search?intent=strankovani&provider=E2E%20test%20provider%20B");
  expect((await provider.json() as typeof body).facets.providers).toEqual(allBody.facets.providers);
});

test("inclusive cutoff filters real D1 beyond first page without declaring missing dates expired", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await page.getByLabel("Uzávěrka nejpozději (včetně dne, UTC)").fill("2027-05-01");
  await page.getByRole("button", { name: "Použít datum uzávěrky" }).click();
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Zrušit filtr Uzávěrka nejpozději: 2027-05-01" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.getByLabel("Termín podání").selectOption("UNKNOWN");
  await expect(page.getByLabel("Uzávěrka nejpozději (včetně dne, UTC)")).toHaveValue("");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(24);

  const first = await request.get("/api/search?intent=digitalizace%20obce&limit=1&closesBy=2027-12-31");
  expect(first.status()).toBe(200);
  const { nextCursor } = await first.json() as { nextCursor: string | null };
  expect(nextCursor).toBeTruthy();
  const changed = await request.get(`/api/search?intent=digitalizace%20obce&limit=1&closesBy=2027-10-31&cursor=${encodeURIComponent(nextCursor!)}`);
  expect(changed.status()).toBe(400);
  expect(await changed.json()).toEqual({ error: "INVALID_CURSOR" });
  const boundary = await request.get("/api/search?intent=digitalizace%20obce&closesBy=2027-10-31");
  expect(boundary.status()).toBe(200);
  expect((await boundary.json()).results).toEqual([expect.objectContaining({ grantCallVersionId: "gcv-e2e-planned" })]);
});

test("inclusive start and end find a later-page D1 result on mobile and reset stale pages", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await page.getByLabel("Uzávěrka nejdříve (včetně dne, UTC)").fill("2027-05-01");
  await page.getByRole("button", { name: "Použít datum od" }).click();
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await page.getByLabel("Uzávěrka nejpozději (včetně dne, UTC)").fill("2027-05-01");
  await page.getByRole("button", { name: "Použít datum uzávěrky" }).click();
  await expect(page.getByRole("button", { name: "Zrušit filtr Uzávěrka nejdříve: 2027-05-01" })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await page.getByLabel("Řazení všech odpovídajících výsledků").selectOption("DEADLINE_LATEST");
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await page.getByLabel("Termín podání").selectOption("UNKNOWN");
  await expect(page.getByLabel("Uzávěrka nejdříve (včetně dne, UTC)")).toHaveValue("");
  await expect(page.getByLabel("Uzávěrka nejpozději (včetně dne, UTC)")).toHaveValue("");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  for (const sort of ["RELEVANCE", "DEADLINE", "DEADLINE_LATEST"]) {
    const first = await request.get(`/api/search?intent=digitalizace%20obce&limit=1&closesFrom=2027-10-31&closesBy=2027-12-31&sort=${sort}`);
    expect(first.status()).toBe(200);
    const body = await first.json() as { results: Array<{ grantCallVersionId: string }>; nextCursor: string | null };
    expect(body.nextCursor).toBeTruthy();
    const second = await request.get(`/api/search?intent=digitalizace%20obce&limit=1&closesFrom=2027-10-31&closesBy=2027-12-31&sort=${sort}&cursor=${encodeURIComponent(body.nextCursor!)}`);
    expect(second.status()).toBe(200);
    const next = await second.json() as typeof body;
    expect(new Set([...body.results, ...next.results].map((item) => item.grantCallVersionId))).toEqual(new Set(["gcv-e2e-open", "gcv-e2e-planned"]));
    const changed = await request.get(`/api/search?intent=digitalizace%20obce&limit=1&closesFrom=2027-11-01&closesBy=2027-12-31&sort=${sort}&cursor=${encodeURIComponent(body.nextCursor!)}`);
    expect(changed.status()).toBe(400);
    expect(await changed.json()).toEqual({ error: "INVALID_CURSOR" });
  }
  for (const [query, code] of [
    ["closesFrom=", "INVALID_CLOSES_FROM"],
    ["closesFrom=2027-02-29", "INVALID_CLOSES_FROM"],
    ["closesFrom=2027-05-01&closesFrom=2027-06-01", "INVALID_CLOSES_FROM"],
    ["closesFrom=2027-12-31&closesBy=2027-10-31", "INVALID_DEADLINE_RANGE"],
  ]) {
    const response = await request.get(`/api/search?intent=strankovani&${query}`);
    expect(response.status()).toBe(400);
    expect(await response.json()).toEqual({ error: code });
  }
});

test("bounded API search includes date-only source values and excludes invalid source dates", async ({ request }) => {
  for (const bounds of ["closesFrom=2027-02-01", "closesBy=2027-05-31",
    "closesFrom=2027-05-01&closesBy=2027-05-01"]) {
    for (const sort of ["RELEVANCE", "DEADLINE", "DEADLINE_LATEST"]) {
      const response = await request.get(`/api/search?intent=date-boundary&${bounds}&sort=${sort}`);
      expect(response.status()).toBe(200);
      const body = await response.json() as { results: Array<{ grantCallVersionId: string; submissionCloseAt: string | null }> };
      expect(body.results).toEqual([expect.objectContaining({
        grantCallVersionId: "gcv-e2e-date-only", submissionCloseAt: "2027-05-01",
      })]);
    }
  }
});

test("UTC date bounds keep sub-millisecond deadlines on their actual source day", async ({ request }) => {
  for (const sort of ["RELEVANCE", "DEADLINE", "DEADLINE_LATEST"]) {
    for (const [bounds, expected] of [
      ["closesBy=2027-05-01", "gcv-e2e-precision-before"],
      ["closesFrom=2027-05-02", "gcv-e2e-precision-after"],
      ["closesFrom=2027-05-01&closesBy=2027-05-01", "gcv-e2e-precision-before"],
    ]) {
      const response = await request.get(`/api/search?intent=precision-boundary&${bounds}&sort=${sort}`);
      expect(response.status()).toBe(200);
      const body = await response.json() as { results: Array<{ grantCallVersionId: string }> };
      expect(body.results.map((row) => row.grantCallVersionId)).toEqual([expected]);
    }
  }
});

test("date form constraints use applied bounds while the other form has an unsent draft", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/search?")) requests.push(request.url());
  });

  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  const by = page.getByLabel("Uzávěrka nejpozději (včetně dne, UTC)");
  const from = page.getByLabel("Uzávěrka nejdříve (včetně dne, UTC)");
  await by.fill("2027-05-01");
  await page.getByRole("button", { name: "Použít datum uzávěrky" }).click();
  await expect(page.getByRole("button", { name: "Zrušit filtr Uzávěrka nejpozději: 2027-05-01" })).toBeVisible();
  await by.fill("2027-06-01");
  await from.fill("2027-05-15");
  await expect(from).toHaveAttribute("max", "2027-05-01");
  expect(await from.evaluate((input: HTMLInputElement) => input.validity.rangeOverflow)).toBe(true);
  await page.getByRole("button", { name: "Použít datum od" }).click();
  await page.waitForTimeout(100);
  expect(requests.some((url) => url.includes("closesBy=2027-05-01") && url.includes("closesFrom=2027-05-15"))).toBe(false);
  await expect(page.getByRole("button", { name: "Zrušit filtr Uzávěrka nejpozději: 2027-05-01" })).toBeVisible();

  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await from.fill("2027-05-15");
  await page.getByRole("button", { name: "Použít datum od" }).click();
  await expect(page.getByRole("button", { name: "Zrušit filtr Uzávěrka nejdříve: 2027-05-15" })).toBeVisible();
  await from.fill("2027-04-01");
  await by.fill("2027-05-01");
  await expect(by).toHaveAttribute("min", "2027-05-15");
  expect(await by.evaluate((input: HTMLInputElement) => input.validity.rangeUnderflow)).toBe(true);
  await page.getByRole("button", { name: "Použít datum uzávěrky" }).click();
  await page.waitForTimeout(100);
  expect(requests.some((url) => url.includes("closesFrom=2027-05-15") && url.includes("closesBy=2027-05-01"))).toBe(false);
  await expect(page.getByRole("button", { name: "Zrušit filtr Uzávěrka nejdříve: 2027-05-15" })).toBeVisible();
});

test("global date ordering moves a later-page deadline first and paginates missing dates safely", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toHaveCount(0);
  await page.getByLabel("Řazení všech odpovídajících výsledků").selectOption("DEADLINE");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.locator(".grant-card h3").first()).toHaveText("E2E pozdější plánovaná výzva");
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  expect(new Set(await page.locator(".grant-card h3").allTextContents()).size).toBe(25);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const firstResponse = await request.get("/api/search?intent=strankovani&sort=DEADLINE_LATEST&limit=1");
  expect(firstResponse.status()).toBe(200);
  const first = await firstResponse.json() as { results: Array<{ grantCallVersionId: string }>; nextCursor: string };
  expect(first.results[0].grantCallVersionId).toBe("gcv-e2e-page-25");
  const next = await request.get(`/api/search?intent=strankovani&sort=DEADLINE_LATEST&limit=1&cursor=${encodeURIComponent(first.nextCursor)}`);
  expect(next.status()).toBe(200);
  expect((await next.json()).results[0].submissionCloseAt).toBeNull();
  const changed = await request.get(`/api/search?intent=strankovani&sort=DEADLINE&limit=1&cursor=${encodeURIComponent(first.nextCursor)}`);
  expect(changed.status()).toBe(400);
  expect(await changed.json()).toEqual({ error: "INVALID_CURSOR" });
  const invalid = await request.get("/api/search?intent=strankovani&sort=DEADLINE&sort=RELEVANCE");
  expect(invalid.status()).toBe(400);
  expect(await invalid.json()).toEqual({ error: "INVALID_SORT" });
});

test("date ordering retains direct and ontology match labels across null-date cursor boundaries", async ({ request }) => {
  for (const sort of ["DEADLINE", "DEADLINE_LATEST"]) {
    let cursor: string | null = null;
    const results: Array<{ grantCallVersionId: string; matchKind: string; submissionCloseAt: string | null }> = [];
    do {
      const response = await request.get(`/api/search?intent=koupali%C5%A1t%C4%9B&sort=${sort}&limit=1${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
      expect(response.status()).toBe(200);
      const page = await response.json() as { results: typeof results; nextCursor: string | null };
      results.push(...page.results);
      cursor = page.nextCursor;
    } while (cursor);
    expect(results.map((row) => [row.grantCallVersionId, row.matchKind, row.submissionCloseAt])).toEqual([
      ["gcv-e2e-page-1", "DIRECT", null],
      ["gcv-e2e-page-2", "ONTOLOGY", null],
      ["gcv-e2e-page-3", "ONTOLOGY", null],
    ]);
  }
});

test("real D1 cursor crosses from direct to ontology without replaying direct matches", async ({ request }) => {
  const firstResponse = await request.get("/api/search?intent=koupali%C5%A1t%C4%9B&limit=1");
  expect(firstResponse.status()).toBe(200);
  const first = await firstResponse.json() as { results: Array<{ grantCallVersionId: string; matchKind: string }>; nextCursor: string | null };
  expect(first.results).toEqual([expect.objectContaining({ grantCallVersionId: "gcv-e2e-page-1", matchKind: "DIRECT" })]);
  expect(first.nextCursor).toBeTruthy();
  const secondResponse = await request.get(`/api/search?intent=koupali%C5%A1t%C4%9B&limit=1&cursor=${encodeURIComponent(first.nextCursor!)}`);
  expect(secondResponse.status()).toBe(200);
  const second = await secondResponse.json() as { results: Array<{ grantCallVersionId: string; matchKind: string }>; nextCursor: string | null };
  expect(second.results).toEqual([expect.objectContaining({ grantCallVersionId: "gcv-e2e-page-2", matchKind: "ONTOLOGY" })]);
  expect(second.nextCursor).toBeTruthy();
  const thirdResponse = await request.get(`/api/search?intent=koupali%C5%A1t%C4%9B&limit=1&cursor=${encodeURIComponent(second.nextCursor!)}`);
  expect(thirdResponse.status()).toBe(200);
  const third = await thirdResponse.json() as { results: Array<{ grantCallVersionId: string; matchKind: string }>; nextCursor: string | null };
  expect(third.results).toEqual([expect.objectContaining({ grantCallVersionId: "gcv-e2e-page-3", matchKind: "ONTOLOGY" })]);
  expect(third.nextCursor).toBeNull();
});

test("non-sport intent -> real API results -> filters -> detail -> provenance", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Co chcete uskutečnit?").first().fill("digitalizace obce");
  await page.getByRole("button", { name: "Najít možnosti" }).first().click();

  await expect(page).toHaveURL(/\/hledat\?intent=digitalizace\+obce/);
  await expect(page.getByRole("heading", { name: "Nalezené možnosti" })).toBeVisible();
  await expect(page.locator(".section-heading").getByText("2 výsledků.")).toBeVisible();

  await expect(
    page.getByText(
      "Způsobilost konkrétního žadatele zatím není v tomto výsledku vyhodnocena",
    ).first(),
  ).toBeVisible();

  await page.getByLabel("Stav výzvy").selectOption("OPEN");
  await expect(
    page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" }),
  ).toHaveCount(0);
  await expect(page.locator(".section-heading").getByText("1 výsledků.")).toBeVisible();

  await page.getByLabel("Přesný název poskytovatele").fill("E2E test provider A");
  await page.getByRole("button", { name: "Použít poskytovatele" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await page.getByRole("link", { name: "Zobrazit detail" }).click();

  await expect(page).toHaveURL(/\/dotace\/grant%3Ae2e%3Aopen$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" }),
  ).toBeVisible();
  await expect(page.getByText("Lze podat žádost").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Oficiální zdroje" })).toBeVisible();
  await expect(page.getByRole("link", { name: /E2E oficiální zdroj A/ })).toHaveAttribute(
    "href",
    "https://example.invalid/e2e/open",
  );

  const deadlines = page.getByRole("region", { name: "Termíny podle zdroje" });
  await expect(deadlines).toContainText("Ukončení příjmu žádostí");
  await expect(deadlines).toContainText("2027-12-31 23:59:59 UTC");
  await expect(deadlines.getByRole("link", { name: /Doklad termínu: E2E oficiální podmínky, str. 2/ }))
    .toHaveAttribute("href", "https://example.invalid/e2e/open-source");
  await expect(deadlines).toContainText("nikoli potvrzení, že lze právě podat žádost");

  const evidence = page.getByText("Konkrétní evidence (4)");
  await expect(evidence).toBeVisible();
  await evidence.click();
  await expect(page.getByRole("link", { name: /E2E oficiální podmínky/ }).first()).toHaveAttribute(
    "href",
    "https://example.invalid/e2e/open-source",
  );
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toBeVisible();
});

test("UNKNOWN applicant type -> one answer -> fresh D1 reevaluation stays non-definitive", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await page.getByRole("link", { name: "Přidat k projektu" }).click();
  await page.getByRole("button", { name: "Vytvořit projekt" }).click();
  const eligibility = page.getByRole("region", { name: "Způsobilost pro vybranou výzvu" });
  await expect(eligibility.getByText("Chybí údaj pro posouzení (UNKNOWN)")).toBeVisible();
  await eligibility.getByText("Podklad pravidla").click();
  await expect(eligibility.getByText("e2e-fe-applicant-type")).toBeVisible();
  await expect(eligibility.getByRole("heading", { name: "Jaký typ žadatele bude žádost podávat?" })).toBeVisible();
  await expect(eligibility.getByLabel("Typ žadatele")).toHaveValue("");
  expect(await eligibility.getByLabel("Typ žadatele").evaluate((input: HTMLSelectElement) => input.validity.valueMissing)).toBe(true);
  const project = await page.evaluate(() => JSON.parse(sessionStorage.getItem("dotacni-majak:active-project") || "null") as {
    ownerCapability: string;
  });
  const headers = { authorization: `Bearer ${project.ownerCapability}` };
  const before = await page.request.get("/api/grants/grant%3Ae2e%3Aopen/eligibility", { headers });
  expect(before.status()).toBe(200);
  expect(await before.json()).toMatchObject({ versionId: "gcv-e2e-open", ruleSetId: "e2e-rule-set-open",
    status: "NEEDS_INFORMATION", missingAttributes: ["applicant.type"],
    conditions: [{ evidenceId: "e2e-fe-applicant-type" }] });
  await eligibility.getByLabel("Typ žadatele").selectOption("MUNICIPALITY");
  await eligibility.getByRole("button", { name: "Uložit odpověď a přepočítat" }).click();
  await expect(eligibility.getByRole("status")).toContainText("Známé podmínky vycházejí, ale vstup není ověřený");
  await expect(eligibility.getByText(/Shoda není ověřená způsobilost/)).toBeVisible();
  const after = await page.request.get("/api/grants/grant%3Ae2e%3Aopen/eligibility", { headers });
  expect(after.headers()["cache-control"]).toBe("private, no-store");
  expect(await after.json()).toMatchObject({ status: "LIKELY_ELIGIBLE", rootResult: "PASS", missingAttributes: [],
    conditions: [{ inputSource: "PROFILE", inputVerification: "USER_DECLARED" }] });

  const changed = await page.request.put("/api/applicant-profile", { headers, data: { applicantType: "BUSINESS" } });
  expect(changed.status()).toBe(200);
  await eligibility.getByRole("button", { name: "Obnovit posouzení z aktuální verze" }).click();
  await expect(eligibility.getByText("Výsledek vyžaduje ověření, nejde o zamítnutí")).toBeVisible();
  await expect(eligibility.getByText("Známé podmínky vycházejí, ale vstup není ověřený")).toHaveCount(0);
  expect(await (await page.request.get("/api/grants/grant%3Ae2e%3Aopen/eligibility", { headers })).json())
    .toMatchObject({ status: "NEEDS_REVIEW", rootResult: "FAIL", blockers: ["e2e-applicant-type"] });
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  expect(accessibility.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("pending profile write blocks workspace switching until owner-wide update commits", async ({ page }) => {
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await page.getByRole("link", { name: "Přidat k projektu" }).click();
  await page.getByRole("button", { name: "Vytvořit projekt" }).click();
  const eligibility = page.getByRole("region", { name: "Způsobilost pro vybranou výzvu" });
  await expect(eligibility.getByRole("status")).toContainText("Chybí údaj pro posouzení (UNKNOWN)");
  const project = await page.evaluate(() => JSON.parse(sessionStorage.getItem("dotacni-majak:active-project") || "null") as {
    projectId: string; ownerCapability: string;
  });
  const created = await page.request.post(`/api/projects/${project.projectId}/workspaces`, {
    headers: { authorization: `Bearer ${project.ownerCapability}` }, data: { grantCallId: "grant:e2e:planned" },
  });
  expect(created.status()).toBe(201);
  await page.reload();
  await expect(page.getByRole("button", { name: "Otevřít přípravu: grant:e2e:planned" })).toBeVisible();
  await expect(eligibility.getByRole("status")).toContainText("Chybí údaj pro posouzení (UNKNOWN)");
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/applicant-profile", async (route) => {
    if (route.request().method() === "PUT") await pending;
    await route.continue();
  });
  await eligibility.getByLabel("Typ žadatele").selectOption("MUNICIPALITY");
  await eligibility.getByRole("button", { name: "Uložit odpověď a přepočítat" }).click();
  await expect(page.getByRole("button", { name: "Otevřít přípravu: grant:e2e:planned" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Obnovit přípravu a změny" })).toBeDisabled();
  release();
  await expect(page.getByRole("button", { name: "Otevřít přípravu: grant:e2e:planned" })).toBeEnabled();
  await page.getByRole("button", { name: "Otevřít přípravu: grant:e2e:planned" }).click();
  await expect(eligibility.getByRole("status")).toContainText("Výsledek vyžaduje ověření, nejde o zamítnutí");
  await expect(eligibility).toContainText("gcv-e2e-planned");
});

test("eligibility outage hides a previously computed result and recovers only from real D1", async ({ page }) => {
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await page.getByRole("link", { name: "Přidat k projektu" }).click();
  await page.getByRole("button", { name: "Vytvořit projekt" }).click();
  const eligibility = page.getByRole("region", { name: "Způsobilost pro vybranou výzvu" });
  await expect(eligibility.getByText("Chybí údaj pro posouzení (UNKNOWN)")).toBeVisible();
  let unavailable = true;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen/eligibility", async (route) => {
    if (unavailable) await route.fulfill({ status: 503, body: '{"error":"ELIGIBILITY_UNAVAILABLE"}' });
    else await route.continue();
  });
  await eligibility.getByRole("button", { name: "Obnovit posouzení z aktuální verze" }).click();
  await expect(eligibility.getByRole("alert")).toContainText("Starý výsledek nepoužíváme");
  await expect(eligibility.getByText("Chybí údaj pro posouzení (UNKNOWN)")).toHaveCount(0);
  unavailable = false;
  await eligibility.getByRole("button", { name: "Obnovit posouzení z aktuální verze" }).click();
  await expect(eligibility.getByText("Chybí údaj pro posouzení (UNKNOWN)")).toBeVisible();
});

test("detail API outage stays fail-closed and retry recovers from real D1", async ({ page }) => {
  const path = "/dotace/grant%3Ae2e%3Aopen";
  let unavailable = true;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (unavailable) {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "DETAIL_UNAVAILABLE" }) });
    } else {
      await route.continue();
    }
  });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Oficiální zdroje" })).toHaveCount(0);
  unavailable = false;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByRole("link", { name: /E2E oficiální zdroj A/ })).toHaveAttribute("href", "https://example.invalid/e2e/open");
  await expect(page.getByRole("button", { name: "Zkusit načíst detail znovu" })).toHaveCount(0);
});

test("missing detail is not presented as a transient outage", async ({ page }) => {
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", (route) => route.fulfill({
    status: 404, contentType: "application/json", body: JSON.stringify({ error: "NOT_FOUND" }),
  }));
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await expect(page.getByRole("heading", { name: "Tuto dotační výzvu jsme v aktuálním indexu nenašli." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Zkusit načíst detail znovu" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
});

test("detail distinguishes a normalized deadline with evidence from a source-version fallback", async ({ page }) => {
  await page.goto("/dotace/grant%3Ae2e%3Aplanned");
  const deadlines = page.getByRole("region", { name: "Termíny podle zdroje" });
  await expect(deadlines).toContainText("Příjem žádostí (souhrn výzvy)");
  await expect(deadlines).toContainText("2027-10-31 23:59:59 UTC");
  await expect(deadlines).toContainText("Samostatný doklad termínu není připojen");
  await expect(deadlines.getByRole("link")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(deadlines).toBeVisible();
  await expect(page.getByRole("link", { name: /E2E oficiální zdroj B/ })).toBeVisible();
});

test("detail does not present version capture as a source check when no source record exists", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Adate%3Aonly");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { sources: unknown[]; capturedAt: string };
  expect(detail.sources).toEqual([]);
  expect(detail.capturedAt).toBe("2026-09-26T20:00:00Z");

  await page.goto("/dotace/grant%3Ae2e%3Adate%3Aonly");
  const facts = page.locator(".detail-section .facts").first();
  await expect(facts.locator("div").filter({ has: page.locator("dt", { hasText: "Verze výzvy zachycena" }) }).first())
    .toContainText("26. září 2026");
  await expect(facts.locator("div").filter({ has: page.locator("dt", { hasText: "Poslední pozorování záznamu u zdroje" }) }).first())
    .toContainText("Není doložena");
  await expect(page.getByText("Zdrojový odkaz zatím není v indexu dostupný")).toHaveCount(0);

  await page.getByRole("link", { name: "Přidat k projektu" }).click();
  await page.getByRole("button", { name: "Vytvořit projekt" }).click();
  await expect(page.getByRole("heading", { name: "Příprava žádosti · Dotáhne" })).toBeVisible();
  const owner = await page.evaluate(() => JSON.parse(sessionStorage.getItem("dotacni-majak:active-project") || "null") as {
    projectId: string; ownerCapability: string;
  });
  const base = `/api/projects/${owner.projectId}/workspaces`;
  const headers = { authorization: `Bearer ${owner.ownerCapability}` };
  const list = await page.request.get(base, { headers });
  expect(list.status()).toBe(200);
  const [{ id }] = (await list.json()).workspaces as Array<{ id: string }>;
  const workspace = await page.request.get(`${base}/${id}`, { headers });
  expect(workspace.status()).toBe(200);
  expect((await workspace.json()).versionReview).toMatchObject({
    currentCapturedAt: "2026-09-26T20:00:00Z", sourceCheckedAt: null,
  });

  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  const sourcedFacts = page.locator(".detail-section .facts").first();
  await expect(sourcedFacts.locator("div").filter({ has: page.locator("dt", { hasText: "Verze výzvy zachycena" }) }).first())
    .toContainText("26. září 2026");
  await expect(sourcedFacts.locator("div").filter({ has: page.locator("dt", { hasText: "Poslední pozorování záznamu u zdroje" }) }).first())
    .toContainText("1. října 2026");
  await expect(page.getByText("Pozorování záznamu nepotvrzuje, že podmínky této verze byly znovu ověřeny.", { exact: false })).toBeVisible();
});

test("mobile result filters, deadline order and chips use the real API without implying eligibility", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce");
  const planned = page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" });
  const open = page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" });
  await expect(planned).toBeVisible();
  await expect(open).toBeVisible();
  expect(await page.locator(".results-list .grant-card h3").first().textContent()).toContain("E2E plánovaná výzva");
  await page.getByLabel("Řazení všech odpovídajících výsledků").selectOption("DEADLINE_LATEST");
  expect(await page.locator(".results-list .grant-card h3").first().textContent()).toContain("E2E otevřená výzva");
  await page.getByLabel("Řazení všech odpovídajících výsledků").selectOption("DEADLINE");
  expect(await page.locator(".results-list .grant-card h3").first().textContent()).toContain("E2E plánovaná výzva");
  await page.getByLabel("Termín podání").selectOption("UNKNOWN");
  await expect(page.getByText("Zvoleným filtrům neodpovídá žádná aktivní výzva pro váš záměr. Zkuste jiného poskytovatele nebo zrušte filtry.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Zrušit filtr Termín: neuveden" })).toBeVisible();
  await page.getByRole("button", { name: "Zrušit filtr Termín: neuveden" }).click();
  await page.getByLabel("Stav výzvy").selectOption("PLANNED");
  await expect(planned).toBeVisible();
  await expect(open).toHaveCount(0);
  await page.getByRole("button", { name: "Zrušit všechny filtry" }).click();
  await expect(open).toBeVisible();
  const filterToggle = page.getByText("Upravit filtry a řazení");
  await filterToggle.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Stav výzvy")).toBeHidden();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Stav výzvy")).toBeVisible();
  await expect(page.getByText(/Stav, dostupnost termínu, uzávěrka nejdříve, uzávěrka nejpozději a přesný název poskytovatele se filtrují napříč/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
});

test("tennis intent never surfaces the CLOSED historical NSA fixture as active", async ({ page }) => {
  await page.goto("/");
  await page
    .getByLabel("Co chcete uskutečnit?")
    .first()
    .fill("rekonstrukce tenisových kurtů");
  await page.getByRole("button", { name: "Najít možnosti" }).first().click();

  await expect(page.getByText("Teď není vhodná otevřená výzva")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Maják může hledat dál." })).toBeVisible();
  await expect(
    page.getByText("Regiony 2026 — investice pod 10 mil. Kč (historický E2E fixture)"),
  ).toHaveCount(0);

  const watch = page.getByRole("link", { name: "Pohlídat tento záměr" });
  await expect(watch).toBeVisible();
  await expect(watch).toHaveAttribute("href", /\/projekty\?.*watch=1/);
});

test("search API failure is fail-closed and shows no invented results", async ({ page }) => {
  await page.route("**/api/search?*", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "SEARCH_UNAVAILABLE" }),
    });
  });

  await page.goto("/hledat?intent=digitalizace%20obce");
  await expect(
    page.getByRole("heading", { name: "Výsledky teď neumíme bezpečně zobrazit." }),
  ).toBeVisible();
  await expect(page.getByText(/Vyhledávací index není dostupný/)).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" }),
  ).toHaveCount(0);
});

test("no result → saved watch → published source → notification → detail; failure keeps last good", async ({ page }) => {
  await page.goto("/hledat?intent=rekonstrukce%20tenisov%C3%BDch%20kurt%C5%AF");
  await expect(page.getByRole("heading", { name: "Maják může hledat dál." })).toBeVisible();
  await page.getByRole("link", { name: "Pohlídat tento záměr" }).click();
  await expect(page.getByLabel("Co chcete uskutečnit?")).toHaveValue("rekonstrukce tenisových kurtů");
  const created = page.waitForResponse((response) => response.url().endsWith("/api/projects") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Vytvořit projekt" }).click();
  expect((await created).status()).toBe(201);
  await expect(page.getByText("Maják tento projekt hlídá", { exact: true })).toBeVisible();
  await expect(page.getByText(/Zatím nemáte žádná upozornění/)).toBeVisible();

  const project = await page.evaluate(() => JSON.parse(
    sessionStorage.getItem("dotacni-majak:active-project") || "null",
  ) as { projectId: string; ownerCapability: string });
  const path = `/api/projects/${project.projectId}/notifications`;
  expect((await page.request.get(path)).status()).toBe(404);
  expect((await page.request.get(path, {
    headers: { authorization: `Bearer ${"x".repeat(43)}` },
  })).status()).toBe(404);
  const run = (action: string) => execFileSync("python3", ["scripts/e2e_watch_flow.py", action], {
    encoding: "utf8", cwd: process.cwd(),
  });
  expect(run("publish")).toContain("PUBLISHED");
  expect(run("drain")).toContain('["DELIVERED", "DELIVERED", "DELIVERED"]');
  expect(run("drain")).toContain("[]");
  await page.getByRole("button", { name: "Obnovit upozornění" }).click();
  await expect(page.getByText("Nová možnost potřebuje doplnit údaj")).toBeVisible();
  await expect(page.getByText(/Výzva tematicky odpovídá projektu, ale/)).toBeVisible();
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  const link = page.getByRole("link", { name: "Otevřít detail výzvy a ověřit podmínky" });
  await expect(link).toHaveAttribute("href", "/dotace/grant%3Ae2e%3Atennis-new");
  await link.click();
  await expect(page.getByRole("heading", { level: 1, name: /E2E nová výzva/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Simulovaný oficiální zdroj E2E/ })).toHaveAttribute(
    "href", "https://example.invalid/e2e/tennis-official-simulation",
  );

  expect(run("fail")).toContain("SIMULATED_SOURCE_FAILURE_LAST_GOOD_PRESERVED");
  expect(run("drain")).toContain("[]");
  await page.goto("/projekty");
  await expect(page.getByText("Nová možnost potřebuje doplnit údaj")).toBeVisible();
  await expect(page.getByRole("link", { name: "Otevřít detail výzvy a ověřit podmínky" })).toHaveCount(1);
  const authorized = await page.request.get(path, {
    headers: { authorization: `Bearer ${project.ownerCapability}` },
  });
  expect(authorized.ok()).toBeTruthy();
  expect((await authorized.json()).notifications).toHaveLength(1);
});
