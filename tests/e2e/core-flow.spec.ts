import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";

test("unsafe indexed source URL is not a link in real D1 search or detail", async ({ page, request }) => {
  const intent = "bezpecnost odkazu";
  const search = await request.get(`/api/search?intent=${encodeURIComponent(intent)}`);
  expect(search.status()).toBe(200);
  const results = (await search.json() as { results: Array<{ grantCallId: string; officialDetailUrl: string | null }> }).results;
  expect(results).toHaveLength(1);
  expect(results[0].officialDetailUrl).toBe("javascript:alert(1)");
  const detail = await request.get(`/api/grants/${encodeURIComponent(results[0].grantCallId)}`);
  expect(detail.status()).toBe(200);
  expect((await detail.json() as { officialDetailUrl: string | null; sources: Array<{ canonicalUrl: string }> })).toMatchObject({
    officialDetailUrl: "javascript:alert(1)",
    sources: [{ canonicalUrl: "javascript:alert(2)" }],
  });

  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/hledat?intent=${encodeURIComponent(intent)}`);
    const card = page.locator(".grant-card");
    await expect(card.getByRole("heading", { name: "E2E výzva — bezpečnost odkazu" })).toBeVisible();
    await expect(card.getByRole("link", { name: /Oficiální zdroj/ })).toHaveCount(0);
    await expect(card.getByRole("note")).toContainText("chybějící odkaz neznamená zrušení výzvy");
    await card.getByRole("link", { name: /Zobrazit detail/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "E2E výzva — bezpečnost odkazu" })).toBeVisible();
    const sources = page.locator(".evidence-card");
    await expect(sources).toContainText("E2E oficiální zdroj A");
    await expect(sources).toContainText("Odkaz na konkrétní výzvu není bezpečně dostupný; toto je pouze obecný web poskytovatele.");
    await expect(sources.getByRole("link", { name: /Web poskytovatele/ })).toHaveAttribute("href", "https://example.invalid/provider-a");
    await expect(sources.getByRole("link", { name: /E2E oficiální zdroj A/ })).toHaveCount(0);
    expect(await page.locator('a[href^="javascript:"]').count()).toBe(0);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
});

test("project-cost filter uses verified grant scenarios in real D1 on desktop and mobile", async ({ page, request }) => {
  const intent = "digitalizace obce";
  const api = await request.get(`/api/search?intent=${encodeURIComponent(intent)}&projectBudgetCzk=300000`);
  expect(api.status()).toBe(200);
  expect((await api.json()).results.map((row: { grantCallVersionId: string }) => row.grantCallVersionId))
    .toEqual(["gcv-e2e-open"]);
  const outside = await request.get(`/api/search?intent=${encodeURIComponent(intent)}&projectBudgetCzk=500000`);
  expect(outside.status()).toBe(200);
  expect((await outside.json()).results).toHaveLength(0);
  const retainedFilter = await request.get(`/api/search?intent=${encodeURIComponent(intent)}&instrument=GRANT&status=OPEN`);
  expect(retainedFilter.status()).toBe(200);
  expect((await retainedFilter.json()).results.map((row: { grantCallVersionId: string }) => row.grantCallVersionId))
    .toEqual(["gcv-e2e-open"]);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/hledat?intent=${encodeURIComponent(intent)}`);
    await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
    if (width === 390) await page.locator(".filter-panel summary").click();
    const budget = page.getByLabel("Náklady projektu (celé Kč)");
    await budget.fill("12.5");
    await page.getByRole("button", { name: "Použít rozpočet projektu" }).click();
    await expect(page.getByRole("alert")).toContainText("celé nezáporné koruny");
    await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
    await budget.fill("300000");
    await page.getByRole("button", { name: "Použít rozpočet projektu" }).click();
    await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Zrušit filtr Náklady projektu: 300000 Kč" })).toBeVisible();
    await expect(page.getByLabel("Typ financování", { exact: true })).toHaveValue("GRANT");
    await page.getByLabel("Stav výzvy").selectOption("OPEN");
    await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
    await budget.fill("500000");
    await page.getByRole("button", { name: "Použít rozpočet projektu" }).click();
    const empty = page.locator(".filter-empty");
    await expect(empty).toContainText("mezi indexovanými výsledky");
    await expect(empty).toContainText("doloženým intervalem nákladů projektu v CZK");
    await expect(empty).toContainText("neznámými nebo neověřenými hranicemi");
    await expect(empty).toContainText("Nejde o posouzení vaší způsobilosti");
    await expect(page.locator(".grant-card")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Zrušit filtr Stav: Otevřeno v zachycené verzi" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Zrušit filtr Náklady projektu: 500000 Kč" })).toBeVisible();
    const clearBudget = empty.getByRole("button", { name: "Zrušit pouze filtr nákladů projektu" });
    await expect(clearBudget).toBeVisible();
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await clearBudget.click();
    await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toHaveCount(0);
    await expect(page.getByLabel("Stav výzvy")).toHaveValue("OPEN");
    await expect(page.getByLabel("Typ financování", { exact: true })).toHaveValue("GRANT");
    await expect(page.getByRole("button", { name: "Zrušit filtr Náklady projektu: 500000 Kč" })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.getByLabel("Stav výzvy").selectOption("ALL");
    await page.getByLabel("Typ financování", { exact: true }).selectOption("LOAN");
    await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Zrušit filtr Náklady projektu: 300000 Kč" })).toHaveCount(0);
  }
});

test("search result actions and feedback remain distinguishable across cards on desktop and mobile", async ({ page, request }) => {
  const intent = "digitalizace obce";
  const response = await request.get(`/api/search?intent=${encodeURIComponent(intent)}`);
  expect(response.status()).toBe(200);
  expect((await response.json() as { results: Array<{ title: string }> }).results.length).toBeGreaterThanOrEqual(2);

  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/hledat?intent=${encodeURIComponent(intent)}`);
    const cards = page.locator(".grant-card");
    await expect(cards).toHaveCount(2);
    const titles = await cards.locator("h3").allTextContents();
    const ids = await cards.locator(".relevance-feedback h4").evaluateAll((headings) => headings.map((heading) => heading.id));
    expect(new Set(ids).size).toBe(2);
    expect(ids.every(Boolean)).toBe(true);
    for (let index = 0; index < titles.length; index += 1) {
      const card = cards.nth(index);
      await expect(card.locator(".relevance-feedback")).toHaveAttribute("aria-labelledby", ids[index]);
      await expect(card.getByRole("region", { name: "Je tato možnost relevantní pro váš projekt?", exact: true })).toBeVisible();
      await expect(card.getByRole("link", { name: `Zobrazit detail: ${titles[index]}`, exact: true })).toBeVisible();
      await expect(card.getByRole("button", { name: `Ano — relevance výzvy ${titles[index]}`, exact: true })).toBeVisible();
      await expect(card.getByRole("link", { name: `Oficiální zdroj: ${titles[index]} (otevře se v nové kartě)`, exact: true })).toBeVisible();
    }
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    const firstDetail = cards.first().getByRole("link", { name: `Zobrazit detail: ${titles[0]}`, exact: true });
    await firstDetail.focus();
    await expect(firstDetail).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: titles[0] })).toBeVisible();
  }
});

test("captured OPEN stays distinct from current submit-ability in real D1 search and detail", async ({ page, request }) => {
  const intent = "digitalizace obce";
  const search = await request.get(`/api/search?intent=${encodeURIComponent(intent)}`);
  expect(search.status()).toBe(200);
  expect((await search.json() as { results: Array<{ grantCallVersionId: string; status: string }> }).results)
    .toContainEqual(expect.objectContaining({ grantCallVersionId: "gcv-e2e-open", status: "OPEN" }));
  const detail = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(detail.status()).toBe(200);
  expect((await detail.json() as { status: string }).status).toBe("OPEN");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const preview = page.locator(".grant-preview");
  await expect(preview.locator(".grant-preview__status")).toHaveText("Otevřeno v zachycené verzi");
  await expect(preview).toContainText("Před podáním ověřte aktuální stav v oficiálním zdroji.");

  await page.goto(`/hledat?intent=${encodeURIComponent(intent)}`);
  const card = page.locator(".grant-card").filter({ has: page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" }) });
  await expect(card).toContainText("Otevřeno v zachycené verzi");
  await expect(card).toContainText("Před podáním ověřte aktuální stav v oficiálním zdroji.");
  await expect(card).not.toContainText("Lze podat žádost");
  await page.locator(".filter-panel summary").click();
  await expect(page.getByLabel("Stav výzvy").locator('option[value="OPEN"]')).toContainText("Otevřeno v zachycené verzi");
  await page.getByLabel("Stav výzvy").selectOption("OPEN");
  await expect(card).toBeVisible();
  await expect(page.getByLabel("Stav výzvy")).toHaveValue("OPEN");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  await card.getByRole("link", { name: "Zobrazit detail" }).click();
  await expect(page.locator(".detail-hero")).toContainText("Otevřeno v zachycené verzi");
  await expect(page.locator(".detail-hero")).toContainText("Před podáním ověřte aktuální stav v oficiálním zdroji.");
  await expect(page.locator(".detail-hero")).not.toContainText("Lze podat žádost");
  await expect(page.locator(".detail-section").filter({ has: page.getByRole("heading", { name: "Rychlý přehled" }) })).toContainText("Otevřeno v zachycené verzi");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const backToResults = page.getByRole("link", { name: "← Zpět na výsledky" });
  await expect(backToResults).toHaveAttribute("href", "/hledat?intent=digitalizace+obce&status=OPEN");
  await backToResults.click();
  await expect(page).toHaveURL(/\/hledat\?intent=digitalizace\+obce&status=OPEN$/);
  await expect(page.getByLabel("Stav výzvy")).toHaveValue("OPEN");
  await expect(card).toBeVisible();
});

test("detail return keeps search intent, but direct deep links fall back safely", async ({ page, request }) => {
  const intent = "digitalizace obce";
  expect((await request.get(`/api/search?intent=${encodeURIComponent(intent)}`)).status()).toBe(200);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`/hledat?intent=${encodeURIComponent(intent)}`);
  const card = page.locator(".grant-card").filter({ has: page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" }) });
  await expect(card).toBeVisible();
  await expect(card.getByRole("link", { name: "Zobrazit detail" }))
    .toHaveAttribute("href", "/dotace/grant%3Ae2e%3Aopen?intent=digitalizace%20obce");
  await card.getByRole("link", { name: "Zobrazit detail" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await page.getByRole("link", { name: "← Zpět na výsledky" }).click();
  await expect(page).toHaveURL(/\/hledat\?intent=digitalizace\+obce$/);
  await expect(card).toBeVisible();
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByRole("link", { name: "← Zpět na výsledky" })).toHaveAttribute("href", "/hledat");
  await page.goto("/dotace/grant%3Ae2e%3Aopen?intent=%20%20");
  await expect(page.getByRole("link", { name: "← Zpět na výsledky" })).toHaveAttribute("href", "/hledat");
});

test("detail return restores all active API filters and sort in the first real D1 search", async ({ page, request }) => {
  const filters = new URLSearchParams({ intent: "digitalizace obce", status: "OPEN", instrument: "GRANT",
    projectBudgetCzk: "300000", provider: "E2E test provider A", deadline: "KNOWN",
    closesFrom: "2027-01-01", closesBy: "2027-12-31", sort: "DEADLINE_LATEST" });
  const expected = await request.get(`/api/search?${filters}`);
  expect(expected.status()).toBe(200);
  expect((await expected.json()).results.map((row: { grantCallVersionId: string }) => row.grantCallVersionId))
    .toEqual(["gcv-e2e-open"]);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/hledat?${filters}`);
    const card = page.locator(".grant-card");
    await expect(card.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
    await expect(page.getByLabel("Stav výzvy")).toHaveValue("OPEN");
    await expect(page.getByLabel("Řazení všech odpovídajících výsledků")).toHaveValue("DEADLINE_LATEST");
    await card.getByRole("link", { name: "Zobrazit detail" }).click();
    const back = page.getByRole("link", { name: "← Zpět na výsledky" });
    const backHref = await back.getAttribute("href");
    expect(backHref?.startsWith("/hledat?")).toBe(true);
    const backParams = new URL(backHref!, "http://localhost").searchParams;
    for (const [key, value] of filters) expect(backParams.get(key)).toBe(value);
    expect(backParams.has("cursor")).toBe(false);
    const searches: string[] = [];
    page.on("request", (request) => { if (request.url().includes("/api/search?")) searches.push(request.url()); });
    await back.click();
    await expect(card.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
    expect(searches.length).toBeGreaterThan(0);
    const first = new URL(searches[0]);
    for (const [key, value] of filters) expect(first.searchParams.get(key)).toBe(value);
    expect(first.searchParams.has("cursor")).toBe(false);
    expect(await card.count()).toBe(1);
  }
});

test("malformed direct detail state falls back to a safe local search URL", async ({ page }) => {
  await page.goto("/dotace/grant%3Ae2e%3Aopen?intent=digitalizace%20obce&status=OPEN&status=PLANNED&provider=x&provider=y&sort=bogus&cursor=bad&return=https%3A%2F%2Fevil.invalid");
  await expect(page.getByRole("link", { name: "← Zpět na výsledky" }))
    .toHaveAttribute("href", "/hledat?intent=digitalizace+obce");
  await page.goto("/dotace/grant%3Ae2e%3Aopen?intent=one&intent=two");
  await expect(page.getByRole("link", { name: "← Zpět na výsledky" })).toHaveAttribute("href", "/hledat");
});

test("detail error return preserves the explicit search intent without a redirect parameter", async ({ page }) => {
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", (route) => route.fulfill({
    status: 404, contentType: "application/json", body: JSON.stringify({ error: "NOT_FOUND" }),
  }));
  await page.goto("/dotace/grant%3Ae2e%3Aopen?intent=digitalizace%20obce&return=https%3A%2F%2Fexample.invalid");
  await expect(page.getByRole("heading", { name: "Tuto dotační výzvu jsme v aktuálním indexu nenašli." })).toBeVisible();
  await expect(page.getByRole("link", { name: "← Zpět na výsledky" })).toHaveAttribute("href", "/hledat?intent=digitalizace+obce");
  await expect(page.getByRole("link", { name: "Zpět na vyhledávání" })).toHaveAttribute("href", "/hledat?intent=digitalizace+obce");
  await page.getByRole("link", { name: "Zpět na vyhledávání" }).click();
  await expect(page).toHaveURL(/\/hledat\?intent=digitalizace\+obce$/);
});

test("detail distinguishes omitted referenced evidence from unattached items at the API cap", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Apage%3A21");
  expect(response.status()).toBe(200);
  const detail = await response.json() as {
    evidence: Array<{ id: string; sourceUrl: string }>;
    deadlines: Array<{ id: string; evidenceId: string | null }>;
    fundingScenarios: Array<{ id: string; evidenceId: string | null }>;
    requirements: Array<{ id: string; evidenceId: string | null }>;
  };
  expect(detail.evidence).toHaveLength(100);
  expect(detail.evidence[0]).toMatchObject({ id: "e2e-fe-page-21-001",
    sourceUrl: "https://example.invalid/e2e/page/21-evidence" });
  expect(detail.evidence[99]?.id).toBe("e2e-fe-page-21-100");
  expect(detail.evidence.map((item) => item.id)).not.toContain("e2e-fe-page-21-101");
  for (const [items, prefix] of [
    [detail.deadlines, "e2e-deadline-page-21"],
    [detail.fundingScenarios, "e2e-funding-page-21"],
    [detail.requirements, "e2e-req-page-21"],
  ] as const) {
    expect(items.find((item) => item.id === `${prefix}-referenced`)?.evidenceId).toBe("e2e-fe-page-21-101");
    expect(items.find((item) => item.id === `${prefix}-unattached`)?.evidenceId).toBeNull();
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Apage%3A21");
  await expect(page.getByRole("heading", { name: "E2E stránkování 21" })).toBeVisible();
  const deadlines = page.getByRole("region", { name: "Termíny podle zdroje" });
  await expect(deadlines.locator("li").filter({ hasText: "E2E termín s odkazem" }))
    .toContainText("Doklad termínu je uveden, ale není dostupný v omezeném seznamu dokladů");
  await expect(deadlines.locator("li").filter({ hasText: "E2E termín bez dokladu" }))
    .toContainText("Samostatný doklad termínu není připojen");
  const finance = page.getByRole("region", { name: "Finance" });
  await expect(finance.locator("article.grant-card").filter({ hasText: "E2E finance s odkazem" }))
    .toContainText("Doklad financování je uveden, ale není dostupný v omezeném seznamu dokladů");
  await expect(finance.locator("article.grant-card").filter({ hasText: "E2E finance bez dokladu" }))
    .toContainText("Samostatný doklad financování není připojen");
  const requirements = page.getByRole("region", { name: "Požadavky a přílohy" });
  await expect(requirements.locator("li").filter({ hasText: "E2E požadavek s odkazem" }))
    .toContainText("Doklad požadavku je uveden, ale není dostupný v omezeném seznamu dokladů");
  await expect(requirements.locator("li").filter({ hasText: "E2E požadavek bez dokladu" }))
    .toContainText("Samostatný doklad požadavku není připojen");
  for (const section of [deadlines, finance, requirements]) {
    await expect(section.getByRole("link", { name: /Doklad (termínu|financování|požadavku):/ })).toHaveCount(0);
  }
  const panel = page.getByRole("complementary", { name: "Oficiální zdroje" });
  await panel.getByText("Konkrétní evidence (100 zobrazených)").click();
  await expect(panel.getByRole("status")).toContainText("Mohou existovat další");
  const evidence = panel.locator("details li");
  await expect(evidence).toHaveCount(100);
  await expect(evidence.nth(99)).toContainText("str. 100");
  await expect(evidence.nth(99).getByRole("link")).toHaveAttribute("href", "https://example.invalid/e2e/page/21-evidence");
  await expect(evidence.getByText("str. 101")).toHaveCount(0);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("detail discloses bounded versions, sources and changes from real D1/API on mobile", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Ahistory");
  expect(response.status()).toBe(200);
  const detail = await response.json() as {
    versionId: string;
    status: string;
    versions: Array<{ id: string; versionNumber: number; isCurrent: boolean }>;
    sources: Array<{ canonicalUrl: string; presenceState: string }>;
    changes: Array<{ id: string; fieldPath: string }>;
  };
  expect(detail.versionId).toBe("gcv-e2e-history-22");
  expect(detail.status).toBe("OPEN");
  expect(detail.sources).toHaveLength(20);
  expect(detail.sources.map((source) => source.canonicalUrl)).toEqual(
    Array.from({ length: 20 }, (_, index) => `https://example.invalid/e2e/history/source/${20 - index}`),
  );
  expect(detail.sources.every((source) => source.presenceState === "CONFIRMED_MISSING")).toBe(true);
  expect(detail.changes).toHaveLength(20);
  expect(detail.changes.map((change) => change.id)).toEqual(
    Array.from({ length: 20 }, (_, index) => `e2e-change-history-${String(21 - index).padStart(2, "0")}`),
  );
  expect(detail.versions).toHaveLength(20);
  expect(detail.versions[0]).toMatchObject({ versionNumber: 22, isCurrent: true });
  expect(detail.versions[19]).toMatchObject({ versionNumber: 3, isCurrent: false });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Ahistory");
  await expect(page.getByRole("heading", { name: "E2E historie verzí" })).toBeVisible();
  await expect(page.locator(".detail-hero").getByText("Otevřeno v zachycené verzi")).toBeVisible();
  await expect(page.locator(".source-presence-caution")).toContainText("Chybění u zdroje samo o sobě neznamená zrušení výzvy.");
  await expect(page.locator(".source-presence-caution")).toContainText("Další zdrojové záznamy mohou být mimo zobrazený seznam.");
  const sources = page.getByRole("complementary", { name: "Oficiální zdroje" });
  await expect(sources.getByRole("status")).toContainText("včetně záznamů se stavem „viděn“");
  await expect(sources.locator(":scope > ul > li")).toHaveCount(20);
  await expect(sources.getByRole("link", { name: "E2E oficiální zdroj A ↗" })).toHaveCount(20);
  const changes = page.locator("section.detail-section").filter({ has: page.getByRole("heading", { name: "Poslední změny (20 zobrazených)" }) });
  await expect(changes.getByRole("status")).toContainText("Mohou existovat další změny");
  await expect(changes.locator("li")).toHaveCount(20);
  await expect(changes.locator("li").first()).toContainText("/e2e/history/change/21");
  await expect(changes.locator("li").last()).toContainText("/e2e/history/change/02");
  await expect(changes.getByText("/e2e/history/change/01")).toHaveCount(0);
  const history = page.locator("details.detail-section").filter({ hasText: "Historie verzí" });
  await history.getByText("Historie verzí (20 zobrazených)").click();
  await expect(history.getByRole("status")).toContainText("Mohou existovat starší verze");
  await expect(history.locator("li")).toHaveCount(20);
  await expect(history.locator("li").first()).toContainText("Verze 22");
  await expect(history.locator("li").last()).toContainText("Verze 3");
  await expect(history.locator("li").filter({ hasText: /^Verze 2 ·/ })).toHaveCount(0);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("grant detail reports source presence without changing OPEN status", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const cases = [
    { id: 21, states: ["MISSING_CANDIDATE"], labels: ["Možná chybí u zdroje (předběžné)"], caution: true },
    { id: 22, states: ["CONFIRMED_MISSING"], labels: ["Potvrzeně chybí u zdroje (neznamená zrušení výzvy)"], caution: true },
    { id: 23, states: ["MISSING_CANDIDATE", "SEEN"], labels: ["Možná chybí u zdroje (předběžné)", "Viděn u zdroje"], caution: false },
    { id: 24, states: [], labels: [], caution: true },
    { id: 20, states: ["SEEN"], labels: ["Viděn u zdroje"], caution: false },
  ];
  for (const scenario of cases) {
    const response = await request.get(`/api/grants/grant%3Ae2e%3Apage%3A${scenario.id}`);
    expect(response.status()).toBe(200);
    const detail = await response.json();
    expect(detail.status).toBe("OPEN");
    expect(detail.sources.map((source: { presenceState: string }) => source.presenceState).sort())
      .toEqual([...scenario.states].sort());

    await page.goto(`/dotace/grant%3Ae2e%3Apage%3A${scenario.id}`);
    await expect(page.getByRole("heading", { name: `E2E stránkování ${scenario.id}` })).toBeVisible();
    await expect(page.locator(".detail-hero").getByText("Otevřeno v zachycené verzi")).toBeVisible();
    const sourcePanel = page.getByRole("complementary", { name: "Oficiální zdroje" });
    for (const label of scenario.labels) await expect(sourcePanel.getByText(label, { exact: true })).toBeVisible();
    await expect(page.locator(".source-presence-caution")).toHaveCount(scenario.caution ? 1 : 0);
    if (scenario.id === 24) {
      await expect(sourcePanel.getByText("Výskyt u zdroje není známý: k výzvě nemáme zdrojový záznam.")).toBeVisible();
    }
    if (scenario.id === 23) {
      await expect(sourcePanel.getByRole("link", { name: "E2E oficiální zdroj A ↗" })).toBeVisible();
      await expect(sourcePanel.getByRole("link", { name: "E2E oficiální zdroj B ↗" })).toBeVisible();
    }
    if (scenario.caution) {
      await expect(page.getByRole("status")).toContainText(scenario.id === 24
        ? "chybějící záznam sám o sobě neznamená zrušení"
        : "Chybění u zdroje samo o sobě neznamená zrušení výzvy.");
      const accessibility = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(accessibility.violations).toEqual([]);
    }
  }
});

test("mobile instrument selector filters real API and D1 before pagination", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce");
  await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
  const summary = page.locator(".filter-panel summary");
  await summary.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Typ financování", { exact: true })).toBeVisible();
  const selector = page.getByLabel("Typ financování", { exact: true });
  await expect(selector.locator("option")).toHaveCount(7);
  await selector.selectOption("LOAN");
  await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByText(/Hledáme v indexovaných výzvách veřejné podpory/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Zrušit filtr Typ financování: LOAN" })).toBeVisible();
  await selector.focus();
  await page.keyboard.press("Escape");
  await expect(page.locator(".filter-panel")).not.toHaveAttribute("open");
  await expect(summary).toBeFocused();
  const api = await request.get("/api/search?intent=digitalizace%20obce&instrument=LOAN");
  expect(api.status()).toBe(200);
  expect((await api.json()).results.map((r: { grantCallVersionId: string }) => r.grantCallVersionId))
    .toEqual(["gcv-e2e-planned"]);
  for (const query of ["instrument=", "instrument=ALL", "instrument=LOAN&instrument=GRANT"]) {
    const invalid = await request.get(`/api/search?intent=digitalizace%20obce&${query}`);
    expect(invalid.status()).toBe(400);
    expect(await invalid.json()).toEqual({ error: "INVALID_INSTRUMENT" });
  }
  await page.getByRole("button", { name: "Zrušit filtr Typ financování: LOAN" }).click();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
});

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
  await expect(page.getByLabel("Stav výzvy").locator('option[value="OPEN"]')).toHaveText("Otevřeno v zachycené verzi (2)");
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(2);
  await expect(page.getByLabel("Stav výzvy").locator('option[value="OPEN"]')).toHaveText("Otevřeno v zachycené verzi (2)");
  await page.getByLabel("Přesný název poskytovatele").fill("Manual provider");
  await page.getByRole("button", { name: "Použít poskytovatele" }).click();
  await expect(page.getByText("Počty pro filtry nejsou dostupné", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Stav výzvy").locator('option[value="OPEN"]')).toHaveText("Otevřeno v zachycené verzi");
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
      await new Promise((resolve) => setTimeout(resolve, 250));
      await route.continue();
    }
  });
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("alert")).toContainText("Dosud načtené výsledky zůstávají zobrazené");
  const retry = page.getByRole("button", { name: "Zkusit načíst další znovu" });
  await expect(retry).toBeFocused();
  await retry.press("Enter");
  const busy = page.getByRole("button", { name: "Načítáme další výsledky…" });
  await expect(busy).toBeFocused();
  await expect(busy).toHaveAttribute("aria-disabled", "true");
  await expect(page.locator(".grant-card")).toHaveCount(25);
  await expect(page.getByRole("status").filter({ hasText: "Načteno 25 výsledků" })).toBeFocused();
  await expect(page.getByRole("button", { name: "Načíst další výsledky" })).toHaveCount(0);
  expect(new Set(await page.locator(".grant-card h3").allTextContents()).size).toBe(25);
});

test("mobile pagination preserves a deliberate focus move during the final page", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  let cursorRequests = 0;
  await page.route("**/api/search?*cursor=*", async (route) => {
    cursorRequests += 1;
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.continue();
  });
  const more = page.getByRole("button", { name: "Načíst další výsledky" });
  await more.focus();
  await more.press("Enter");
  const busy = page.getByRole("button", { name: "Načítáme další výsledky…" });
  await expect(busy).toBeFocused();
  await busy.press("Enter"); // aria-disabled keeps focus but must not dispatch another request.
  const watch = page.getByRole("link", { name: "Pohlídat tento záměr" });
  await watch.focus();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  await expect(watch).toBeFocused();
  expect(cursorRequests).toBe(1);
});

test("global status finds a later-page planned result and rejects a changed cursor", async ({ page, request }) => {
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toHaveCount(0);
  await page.getByLabel("Stav výzvy").selectOption("PLANNED");
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await expect(page.getByText(/Stav, dostupnost termínu, uzávěrka nejdříve, uzávěrka nejpozději, přesný název poskytovatele a typ financování se filtrují napříč/)).toBeVisible();
  await page.goto("/hledat?intent=digitalizace%20obce");
  await page.getByLabel("Přesný název poskytovatele").fill("E2E test provider A");
  await page.getByRole("button", { name: "Použít poskytovatele" }).click();
  await page.getByLabel("Stav výzvy").selectOption("PLANNED");
  await expect(page.locator(".filter-empty")).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toHaveCount(0);
  await expect(page.getByLabel("Přesný název poskytovatele")).toHaveValue("E2E test provider A");
  await expect(page.getByRole("button", { name: "Zrušit filtr Poskytovatel: E2E test provider A" })).toBeVisible();

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

test("status, deadline and provider preserve independent controls across real D1 searches", async ({ page }) => {
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    const searchRequests: URL[] = [];
    const recordSearch = (request: { url: () => string }) => {
      if (request.url().includes("/api/search?")) searchRequests.push(new URL(request.url()));
    };
    page.on("request", recordSearch);
    await page.goto("/hledat?intent=digitalizace%20obce");
    await expect(page.locator(".grant-card")).toHaveCount(2);
    if (width === 390) await page.locator(".filter-panel summary").click();

    await page.getByLabel("Řazení všech odpovídajících výsledků").selectOption("DEADLINE");
    await expect(page.locator(".grant-card")).toHaveCount(2);
    await page.getByLabel("Přesný název poskytovatele").fill("E2E test provider B");
    await page.getByRole("button", { name: "Použít poskytovatele" }).click();
    await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
    await expect(page.getByLabel("Řazení všech odpovídajících výsledků")).toHaveValue("DEADLINE");

    await page.getByLabel("Stav výzvy").selectOption("PLANNED");
    await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
    await page.getByLabel("Termín podání").selectOption("KNOWN");
    await expect(page.locator(".grant-card")).toHaveCount(1);
    await page.getByLabel("Stav výzvy").selectOption("OPEN");
    await expect(page.locator(".filter-empty")).toBeVisible();
    await expect(page.getByRole("button", { name: "Zrušit filtr Poskytovatel: E2E test provider B" })).toBeVisible();
    await page.getByLabel("Přesný název poskytovatele").fill("E2E test provider A");
    await page.getByRole("button", { name: "Použít poskytovatele" }).click();
    await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
    await page.getByLabel("Termín podání").selectOption("UNKNOWN");
    await expect(page.locator(".filter-empty")).toBeVisible();
    await expect(page.getByRole("button", { name: "Zrušit filtr Poskytovatel: E2E test provider A" })).toBeVisible();
    await expect(page.getByLabel("Přesný název poskytovatele")).toHaveValue("E2E test provider A");
    await expect(page.getByLabel("Řazení všech odpovídajících výsledků")).toHaveValue("DEADLINE");
    const last = searchRequests.at(-1)?.searchParams;
    expect(last?.get("status")).toBe("OPEN");
    expect(last?.get("deadline")).toBe("UNKNOWN");
    expect(last?.get("provider")).toBe("E2E test provider A");
    expect(last?.get("sort")).toBe("DEADLINE");
    expect(last?.has("cursor")).toBe(false);
    if (width === 390) {
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    }
    page.off("request", recordSearch);
  }
});

test("global deadline availability finds a later-page call and remains bound to the cursor", async ({ page, request }) => {
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toHaveCount(0);
  await page.getByLabel("Termín podání").selectOption("KNOWN");
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await page.getByLabel("Stav výzvy").selectOption("OPEN");
  await expect(page.locator(".filter-empty")).toContainText("v indexovaných výsledcích shodu pro tento záměr");
  await page.getByRole("button", { name: "Zrušit filtr Stav: Otevřeno v zachycené verzi" }).click();
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
  await expect(page.getByText("E2E test provider B (1)")).toBeHidden();
  await page.locator(".filter-panel summary").click();
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
  await page.locator(".filter-panel summary").click();
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
  await page.locator(".filter-panel summary").click();
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
  await page.locator(".filter-panel summary").click();
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
  await expect(page.locator(".grant-card").getByRole("link", { name: /Oficiální zdroj/ }))
    .toHaveAttribute("href", "https://example.invalid/e2e/open");
  await expect(page.locator(".grant-card").getByRole("note")).toHaveCount(0);
  await page.getByRole("link", { name: "Zobrazit detail" }).click();

  await expect(page).toHaveURL(/\/dotace\/grant%3Ae2e%3Aopen\?intent=digitalizace%20obce&status=OPEN&provider=E2E\+test\+provider\+A$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" }),
  ).toBeVisible();
  await expect(page.getByText("Otevřeno v zachycené verzi").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Oficiální zdroje" })).toBeVisible();
  await expect(page.getByRole("link", { name: /E2E oficiální zdroj A/ })).toHaveAttribute(
    "href",
    "https://example.invalid/e2e/open",
  );

  const deadlines = page.getByRole("region", { name: "Termíny podle zdroje" });
  await expect(deadlines).toContainText("Ukončení příjmu žádostí");
  await expect(deadlines).toContainText("2027-12-31 23:59:59 UTC");
  const overview = page.locator(".detail-section").filter({ has: page.getByRole("heading", { name: "Rychlý přehled" }) });
  await expect(overview.locator("div", { has: page.locator("dt", { hasText: "Ukončení příjmu" }) }).first())
    .toContainText("2027-12-31 23:59:59 UTC");
  await expect(overview.locator("div", { has: page.locator("dt", { hasText: "Zahájení příjmu" }) }).first())
    .toContainText("2026-09-20 08:00:00 UTC");
  await expect(deadlines.getByRole("link", { name: /Doklad termínu: E2E oficiální podmínky, str. 2/ }))
    .toHaveAttribute("href", "https://example.invalid/e2e/open-source");
  await expect(deadlines).toContainText("nikoli potvrzení, že lze právě podat žádost");

  const finance = page.getByRole("region", { name: "Finance" });
  await expect(finance.getByRole("link", { name: /Doklad financování: E2E oficiální podmínky, str. 3/ }))
    .toHaveAttribute("href", "https://example.invalid/e2e/open-source");
  await expect(finance).toContainText("Ověřeno");
  const funded = finance.locator(".grant-card").filter({ has: page.getByRole("heading", { name: "E2E syntetický scénář" }) });
  await expect(funded).toContainText("Minimální náklady projektu podle scénáře");
  await expect(funded).toContainText("200 000");
  await expect(funded).toContainText("Maximální náklady projektu podle scénáře");
  await expect(funded).toContainText("400 000");
  await expect(funded).toContainText("Proplacení po úhradě nákladů");
  await expect(funded).toContainText("Ne, podle scénáře");
  await expect(funded).toContainText("Individuální potřebu vlastních peněz a předfinancování");
  const undocumented = finance.locator(".grant-card").filter({ has: page.getByRole("heading", { name: "E2E scénář bez samostatného dokladu" }) });
  await expect(undocumented).toContainText("Není doložen");
  await expect(undocumented).toContainText("Není doloženo");
  await expect(undocumented).toContainText("Není uvedeno");
  await expect(finance.getByText("Samostatný doklad financování není připojen")).toBeVisible();
  const requirements = page.getByRole("region", { name: "Požadavky a přílohy" });
  await expect(requirements.getByRole("link", { name: /Doklad požadavku: E2E oficiální podmínky, str. 1/ }))
    .toHaveAttribute("href", "https://example.invalid/e2e/open-source");
  await expect(requirements.getByText("Samostatný doklad požadavku není připojen").first()).toBeVisible();
  const evidence = page.getByText("Konkrétní evidence (5)");
  await expect(evidence).toBeVisible();
  await evidence.click();
  await expect(page.getByRole("link", { name: /E2E oficiální podmínky/ }).first()).toHaveAttribute(
    "href",
    "https://example.invalid/e2e/open-source",
  );
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(finance.getByRole("link", { name: /Doklad financování/ })).toBeVisible();
  await expect(requirements.getByRole("link", { name: /Doklad požadavku/ })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("date-only deadline keeps its original precision in real API and mobile overview", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Adate%3Aonly");
  expect(response.status()).toBe(200);
  expect((await response.json() as { submissionCloseAt: string }).submissionCloseAt).toBe("2027-05-01");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Adate%3Aonly");
  const overview = page.locator(".detail-section").filter({ has: page.getByRole("heading", { name: "Rychlý přehled" }) });
  await expect(overview.locator("dd").filter({ hasText: "2027-05-01" })).toBeVisible();
  await expect(overview).not.toContainText("2027-05-01 00:00");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("search cards retain source deadline precision from real D1 and API", async ({ page, request }) => {
  const response = await request.get("/api/search?intent=digitalizace%20obce");
  expect(response.status()).toBe(200);
  const { results } = await response.json() as { results: Array<{ grantCallVersionId: string; submissionCloseAt: string | null }> };
  expect(results.find((row) => row.grantCallVersionId === "gcv-e2e-open")?.submissionCloseAt)
    .toBe("2027-12-31T23:59:59Z");

  await page.goto("/hledat?intent=digitalizace%20obce");
  const open = page.locator(".grant-card").filter({ has: page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" }) });
  await expect(open.locator(".facts dd").nth(1)).toHaveText("2027-12-31 23:59:59 UTC");

  const offsetResponse = await request.get("/api/search?intent=offsetonlyfixture");
  expect(offsetResponse.status()).toBe(200);
  const offsetResults = (await offsetResponse.json() as { results: Array<{ grantCallVersionId: string; submissionCloseAt: string | null }> }).results;
  expect(offsetResults.find((row) => row.grantCallVersionId === "gcv-e2e-date-offset")?.submissionCloseAt)
    .toBe("2027-05-01T16:30:45+02:00");
  await page.goto("/hledat?intent=offsetonlyfixture");
  const offset = page.locator(".grant-card").filter({ has: page.getByRole("heading", { name: "E2E offset výzva" }) });
  await expect(offset.locator(".facts dd").nth(1)).toHaveText("2027-05-01 16:30:45+02:00");

  const dates = await request.get("/api/search?intent=date-boundary");
  expect(dates.status()).toBe(200);
  const dateResults = (await dates.json() as { results: Array<{ grantCallVersionId: string; submissionCloseAt: string | null }> }).results;
  expect(dateResults.find((row) => row.grantCallVersionId === "gcv-e2e-date-only")?.submissionCloseAt).toBe("2027-05-01");
  expect(dateResults.find((row) => row.grantCallVersionId === "gcv-e2e-date-null")?.submissionCloseAt).toBeNull();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=date-boundary");
  const dateOnly = page.locator(".grant-card").filter({ has: page.getByRole("heading", { name: "E2E date only" }) });
  const unknown = page.locator(".grant-card").filter({ has: page.getByRole("heading", { name: "E2E date null" }) });
  await expect(dateOnly.locator(".facts dd").nth(1)).toHaveText("2027-05-01");
  await expect(unknown.locator(".facts dd").nth(1)).toHaveText("Není uvedeno");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
});

test("non-grant instrument remains a loan in real D1/API and mobile detail", async ({ page, request }) => {
  const response = await request.get("http://127.0.0.1:8787/grants/grant%3Ae2e%3Aplanned");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { fundingInstrumentType: string; fundingScenarios: Array<{ instrumentType: string; grantAmountMaxMinor: number }> };
  expect(detail.fundingInstrumentType).toBe("LOAN");
  expect(detail.fundingScenarios).toEqual(expect.arrayContaining([
    expect.objectContaining({ instrumentType: "LOAN", grantAmountMaxMinor: 1234500 }),
    expect.objectContaining({ instrumentType: "GRANT", grantAmountMaxMinor: 9876500 }),
  ]));
  expect(detail.fundingScenarios).toHaveLength(2);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Aplanned");
  const finance = page.getByRole("region", { name: "Finance" });
  await expect(finance.getByText("Typ podpory: Úvěr")).toBeVisible();
  await expect(finance.getByText("Typ podpory: Dotace / příspěvek")).toBeVisible();
  await expect(finance).toContainText("Typ podpory podle verze výzvy: Úvěr");
  await expect(page.locator(".sticky-action").getByRole("link", { name: "Ověřit stav u poskytovatele ↗" })).toBeVisible();
  await expect(page.locator(".next-action")).toContainText("kdy začne příjem žádostí");
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  await expect(finance).toContainText("Grantové částky a procenta nepoužíváme jako výpočet úvěru");
  await expect(finance.getByText("Maximální dotace")).toHaveCount(0);
  await expect(finance).not.toContainText("12 345");
  await expect(finance).not.toContainText("98 765");
  await expect(finance).not.toContainText("70 %");
  await expect(finance.getByText("Samostatný doklad financování není připojen")).toHaveCount(2);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
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

test("detail retry keeps keyboard focus through a delayed outage and hands off to real D1 detail", async ({ page }) => {
  const path = "/dotace/grant%3Ae2e%3Aopen";
  const requestState: { mode: "error" | "pendingError" | "pendingSuccess"; retryRequests: number } = { mode: "error", retryRequests: 0 };
  let releaseError!: () => void;
  let releaseSuccess!: () => void;
  const pendingError = new Promise<void>((resolve) => { releaseError = resolve; });
  const pendingSuccess = new Promise<void>((resolve) => { releaseSuccess = resolve; });
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    const current = requestState.mode;
    if (current !== "error") requestState.retryRequests += 1;
    if (current === "pendingError") await pendingError;
    if (current === "pendingSuccess") await pendingSuccess;
    if (current !== "pendingSuccess") {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "DETAIL_UNAVAILABLE" }) });
    } else {
      await route.continue();
    }
  });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Oficiální zdroje" })).toHaveCount(0);
  const retryButton = page.getByRole("button", { name: "Zkusit načíst detail znovu" });
  requestState.mode = "pendingError";
  await retryButton.focus();
  await retryButton.press("Enter");
  const pendingButton = page.getByRole("button", { name: "Načítáme detail znovu…" });
  await expect(pendingButton).toBeFocused();
  await expect(pendingButton).toHaveAttribute("aria-disabled", "true");
  await pendingButton.press("Enter");
  expect(requestState.retryRequests).toBe(1);
  releaseError();
  await expect(retryButton).toBeFocused();
  requestState.mode = "pendingSuccess";
  await retryButton.press("Enter");
  await expect(pendingButton).toBeFocused();
  releaseSuccess();
  const heading = page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" });
  await expect(heading).toBeFocused();
  await expect(page.getByRole("link", { name: /E2E oficiální zdroj A/ })).toHaveAttribute("href", "https://example.invalid/e2e/open");
  await expect(retryButton).toHaveCount(0);
  expect(requestState.retryRequests).toBe(2);
});

test("mobile detail retry respects a deliberate focus move while waiting for real D1", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const requestState = { retry: false, retryRequests: 0 };
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (!requestState.retry) await route.fulfill({ status: 503, body: '{"error":"DETAIL_UNAVAILABLE"}' });
    else { requestState.retryRequests += 1; await pending; await route.continue(); }
  });
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  const retryButton = page.getByRole("button", { name: "Zkusit načíst detail znovu" });
  await expect(retryButton).toBeVisible();
  requestState.retry = true;
  await retryButton.focus();
  await retryButton.press("Enter");
  await expect(page.getByRole("button", { name: "Načítáme detail znovu…" })).toBeFocused();
  const back = page.getByRole("link", { name: "← Zpět na výsledky" });
  await back.focus();
  release();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(back).toBeFocused();
  expect(requestState.retryRequests).toBe(1);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
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

test("provider homepage fallback never masquerades as evidence for a grant call", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Adate%3Aonly");
  expect(response.status()).toBe(200);
  const detail = await response.json() as {
    sources: unknown[]; officialDetailUrl: string | null;
    provider: { officialUrl: string | null };
  };
  expect(detail.sources).toEqual([]);
  expect(detail.officialDetailUrl).toBeNull();
  expect(detail.provider.officialUrl).toBe("https://example.invalid/provider-a");

  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/dotace/grant%3Ae2e%3Adate%3Aonly");
    await expect(page.getByRole("heading", { level: 1, name: "E2E date only" })).toBeVisible();
    const providerLink = page.getByRole("link", { name: "Web poskytovatele (odkaz na tuto výzvu není doložen) ↗" });
    await expect(providerLink).toHaveCount(2);
    await expect(page.locator(".next-action").getByRole("link", { name: "Přidat k projektu" })).toBeVisible();
    for (const link of await providerLink.all()) {
      await expect(link).toHaveAttribute("href", detail.provider.officialUrl!);
      await expect(link).toHaveAttribute("target", "_blank");
    }
    await expect(page.locator(".evidence-card")).toContainText("Odkaz na konkrétní výzvu nemáme; toto je obecný web poskytovatele.");
    await expect(page.locator(".evidence-card").getByRole("link", { name: /Otevřít oficiální zdroj/ })).toHaveCount(0);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
});

test("detail does not present version capture as a source check when no source record exists", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Adate%3Aonly");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { sources: unknown[]; evidence: unknown[]; capturedAt: string };
  expect(detail.sources).toEqual([]);
  expect(detail.evidence).toEqual([]);
  expect(detail.capturedAt).toBe("2026-09-26T20:00:00Z");

  await page.goto("/dotace/grant%3Ae2e%3Adate%3Aonly");
  await expect(page.locator(".detail-hero").getByText("Výskyt výzvy u zdroje není doložen.")).toBeVisible();
  await expect(page.locator(".evidence-card")).toContainText("Ke výzvě nemáme zdrojový záznam ani samostatné doklady.");
  await expect(page.locator(".evidence-card")).not.toContainText("Máme zdrojový záznam");
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
  const filterToggle = page.locator(".filter-panel summary");
  await expect(page.getByLabel("Stav výzvy")).toBeHidden();
  await filterToggle.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Stav výzvy")).toBeVisible();
  await page.getByLabel("Stav výzvy").focus();
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Stav výzvy")).toBeHidden();
  await expect(filterToggle).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Stav výzvy")).toBeVisible();
  await page.setViewportSize({ width: 1024, height: 844 });
  await expect(page.getByLabel("Stav výzvy")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Stav výzvy")).toBeHidden();
  await filterToggle.click();
  await expect(page.locator(".results-list .grant-card h3").first()).toContainText("E2E plánovaná výzva");
  await page.getByLabel("Řazení všech odpovídajících výsledků").selectOption("DEADLINE_LATEST");
  await expect(page.locator(".results-list .grant-card h3").first()).toContainText("E2E otevřená výzva");
  await expect(page.getByLabel("Řazení všech odpovídajících výsledků")).toBeVisible();
  await page.getByLabel("Řazení všech odpovídajících výsledků").selectOption("DEADLINE");
  await expect(page.locator(".results-list .grant-card h3").first()).toContainText("E2E plánovaná výzva");
  await page.getByLabel("Termín podání").selectOption("UNKNOWN");
  await expect(page.locator(".filter-empty")).toContainText("v indexovaných výsledcích shodu pro tento záměr");
  await expect(page.getByRole("button", { name: "Zrušit filtr Termín: neuveden" })).toBeVisible();
  await page.getByRole("button", { name: "Zrušit filtr Termín: neuveden" }).click();
  await page.getByLabel("Stav výzvy").selectOption("PLANNED");
  await expect(planned).toBeVisible();
  await expect(open).toHaveCount(0);
  await page.getByRole("button", { name: "Zrušit všechny filtry" }).click();
  await expect(open).toBeVisible();
  await filterToggle.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Stav výzvy")).toBeHidden();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Stav výzvy")).toBeVisible();
  await expect(page.getByText(/Stav, dostupnost termínu, uzávěrka nejdříve, uzávěrka nejpozději, přesný název poskytovatele a typ financování se filtrují napříč/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
});

test("mobile filter keyboard focus survives real D1 searches, chip removal, reset and failure", async ({ page, request }) => {
  const intent = "digitalizace obce";
  const api = await request.get(`/api/search?intent=${encodeURIComponent(intent)}&status=OPEN`);
  expect(api.status()).toBe(200);
  expect((await api.json() as { results: Array<{ grantCallVersionId: string }> }).results.map((row) => row.grantCallVersionId))
    .toEqual(["gcv-e2e-open"]);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/hledat?intent=${encodeURIComponent(intent)}`);
  await expect(page.locator(".grant-card")).toHaveCount(2);
  const panel = page.locator(".filter-panel");
  await panel.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(panel).toHaveAttribute("open");

  let releaseSearch!: () => void;
  const heldSearch = new Promise<void>((resolve) => { releaseSearch = resolve; });
  await page.route("**/api/search?*", async (route) => {
    if (new URL(route.request().url()).searchParams.get("status") === "OPEN") await heldSearch;
    await route.continue();
  });
  const status = page.getByLabel("Stav výzvy");
  await status.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByText("Porovnáváme váš záměr s dostupnými výzvami.")).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(0);
  releaseSearch();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(panel).toHaveAttribute("open");
  await expect(status).toBeFocused();
  await expect(status).toHaveValue("OPEN");
  await page.unroute("**/api/search?*");

  const instrument = page.getByLabel("Typ financování", { exact: true });
  let releaseInstrument!: () => void;
  const heldInstrument = new Promise<void>((resolve) => { releaseInstrument = resolve; });
  await page.route("**/api/search?*", async (route) => {
    if (new URL(route.request().url()).searchParams.get("instrument") === "GRANT") await heldInstrument;
    await route.continue();
  });
  await instrument.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByText("Porovnáváme váš záměr s dostupnými výzvami.")).toBeVisible();
  const navigationLink = page.getByRole("navigation", { name: "Hlavní navigace" }).getByRole("link").first();
  await navigationLink.focus();
  await expect(navigationLink).toBeFocused();
  releaseInstrument();
  await expect(instrument).toHaveValue("GRANT");
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(navigationLink).toBeFocused();
  await page.unroute("**/api/search?*");
  await instrument.focus();
  await page.keyboard.press("ArrowDown");
  await expect(instrument).toHaveValue("LOAN");
  await expect(instrument).toBeFocused();
  await expect(panel).toHaveAttribute("open");
  const statusChip = page.getByRole("button", { name: "Zrušit filtr Stav: Otevřeno v zachycené verzi" });
  await statusChip.focus();
  await page.keyboard.press("Enter");
  await expect(statusChip).toHaveCount(0);
  await expect(panel.locator("summary")).toBeFocused();
  await expect(panel).toHaveAttribute("open");
  const reset = page.getByRole("button", { name: "Zrušit všechny filtry" });
  await reset.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".grant-card")).toHaveCount(2);
  await expect(panel.locator("summary")).toBeFocused();

  await page.route("**/api/search?*", (route) => route.abort("failed"));
  await instrument.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit.");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  const retry = page.getByRole("button", { name: "Zkusit vyhledávání znovu" });
  await expect(retry).toBeFocused();
  await page.unroute("**/api/search?*");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(panel.locator("summary")).toBeFocused();
  await expect(panel).toHaveAttribute("open");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
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

test("search API failure is fail-closed and retries the same intent against real D1", async ({ page }) => {
  let allowRecovery = false;
  await page.route("**/api/search?*", async (route) => {
    if (!allowRecovery) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: "SEARCH_UNAVAILABLE" }),
      });
    } else {
      await route.continue();
    }
  });

  await page.goto("/hledat?intent=digitalizace%20obce");
  await expect(
    page.getByRole("heading", { name: "Výsledky teď neumíme bezpečně zobrazit." }),
  ).toBeVisible();
  await expect(page.getByText(/Vyhledávací index není dostupný/)).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" }),
  ).toHaveCount(0);

  allowRecovery = true;
  const retry = page.waitForResponse((response) => response.url().includes("/api/search?") && response.status() === 200);
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  expect(new URL((await retry).url()).searchParams.get("intent")).toBe("digitalizace obce");
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Výsledky teď neumíme bezpečně zobrazit." })).toHaveCount(0);
});

test("search retry keeps keyboard focus through delayed failures and real D1 recovery", async ({ page }) => {
  const state: { mode: "error" | "pendingError" | "pendingSuccess"; retries: number } = { mode: "error", retries: 0 };
  let releaseError!: () => void;
  let releaseSuccess!: () => void;
  const pendingError = new Promise<void>((resolve) => { releaseError = resolve; });
  const pendingSuccess = new Promise<void>((resolve) => { releaseSuccess = resolve; });
  await page.route("**/api/search?*", async (route) => {
    const mode = state.mode;
    if (mode !== "error") state.retries += 1;
    if (mode === "pendingError") await pendingError;
    if (mode === "pendingSuccess") await pendingSuccess;
    if (mode === "pendingSuccess") await route.continue();
    else await route.fulfill({ status: 503, contentType: "application/json",
      body: JSON.stringify({ error: "SEARCH_UNAVAILABLE" }) });
  });
  await page.goto("/hledat?intent=digitalizace%20obce");
  const retry = page.getByRole("button", { name: "Zkusit vyhledávání znovu" });
  await expect(retry).toBeVisible();
  state.mode = "pendingError";
  await retry.focus();
  await retry.press("Enter");
  const busy = page.getByRole("button", { name: "Vyhledáváme znovu…" });
  await expect(busy).toBeFocused();
  await expect(busy).toHaveAttribute("aria-disabled", "true");
  await busy.press("Enter");
  expect(state.retries).toBe(1);
  await expect(page.locator(".grant-card")).toHaveCount(0);
  releaseError();
  await expect(retry).toBeFocused();
  state.mode = "pendingSuccess";
  await retry.press("Enter");
  await expect(busy).toBeFocused();
  releaseSuccess();
  await expect(page.getByRole("heading", { name: "Nalezené možnosti" })).toBeFocused();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  expect(state.retries).toBe(2);
});

test("search retry hands focus to the watch action when real D1 has no results", async ({ page }) => {
  let recover = false;
  await page.route("**/api/search?*", async (route) => {
    if (recover) await route.continue();
    else await route.fulfill({ status: 503, body: '{"error":"SEARCH_UNAVAILABLE"}' });
  });
  await page.goto("/hledat?intent=rekonstrukce%20tenisov%C3%BDch%20kurt%C5%AF");
  const retry = page.getByRole("button", { name: "Zkusit vyhledávání znovu" });
  await expect(retry).toBeVisible();
  recover = true;
  await retry.focus();
  await retry.press("Enter");
  await expect(page.getByRole("heading", { name: "Maják může hledat dál." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Pohlídat tento záměr" })).toBeFocused();
  await expect(page.locator(".grant-card")).toHaveCount(0);
});

test("mobile search retry respects deliberate focus move during real D1 recovery", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let retrying = false;
  let requests = 0;
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/search?*", async (route) => {
    if (!retrying) await route.fulfill({ status: 503, body: '{"error":"SEARCH_UNAVAILABLE"}' });
    else { requests += 1; await pending; await route.continue(); }
  });
  await page.goto("/hledat?intent=digitalizace%20obce");
  const retry = page.getByRole("button", { name: "Zkusit vyhledávání znovu" });
  await expect(retry).toBeVisible();
  retrying = true;
  await retry.focus();
  await retry.press("Enter");
  await expect(page.getByRole("button", { name: "Vyhledáváme znovu…" })).toBeFocused();
  const navigation = page.getByRole("navigation", { name: "Hlavní navigace" }).getByRole("link").first();
  await navigation.focus();
  release();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(navigation).toBeFocused();
  expect(requests).toBe(1);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
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

test("public OPEN detail separates relevance from personal eligibility and leads to project evaluation", async ({ page, request }) => {
  const id = "grant:e2e:open";
  const response = await request.get(`/api/grants/${encodeURIComponent(id)}`);
  expect(response.status()).toBe(200);
  const detail = await response.json() as { status: string; title: string; versionId: string };
  expect(detail.status).toBe("OPEN");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/dotace/${encodeURIComponent(id)}`);
  const eligibility = page.getByRole("region", { name: "Způsobilost pro váš projekt" });
  await expect(eligibility.getByText("Osobní způsobilost zde není posouzena")).toBeVisible();
  await expect(eligibility).toContainText("UNKNOWN");
  const link = eligibility.getByRole("link", { name: "Přejít k projektu a ověřit známé podmínky" });
  await expect(link).toHaveAttribute("href", `/projekty?intent=${encodeURIComponent(detail.title)}&grantCallId=${encodeURIComponent(id)}`);
  expect(await link.getAttribute("href")).not.toMatch(/capability|token|secret/i);
  await link.focus();
  await expect(link).toBeFocused();
  await link.click();
  await page.getByRole("button", { name: "Vytvořit projekt" }).click();
  const projectEligibility = page.getByRole("region", { name: "Způsobilost pro vybranou výzvu" });
  await expect(projectEligibility).toBeVisible();
  await expect(projectEligibility.getByRole("status")).toContainText("Chybí údaj pro posouzení (UNKNOWN)");
  await expect(projectEligibility).toContainText(detail.versionId);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("canonical paused/closed/cancelled and pre-open detail never offer an active application", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const status of ["PAUSED", "CLOSED", "CANCELLED", "ANNOUNCED", "ARCHIVED", "PLANNED"]) {
    const id = status === "PLANNED" ? "grant:e2e:planned" : `grant:e2e:status:${status.toLowerCase()}`;
    const response = await request.get(`/api/grants/${encodeURIComponent(id)}`);
    expect(response.status()).toBe(200);
    const detail = await response.json() as { status: string; officialDetailUrl: string | null };
    expect(detail.status).toBe(status);
    await page.goto(`/dotace/${encodeURIComponent(id)}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const eligibility = page.getByRole("region", { name: "Způsobilost pro váš projekt" });
    await expect(eligibility.getByText("Osobní způsobilost zde není posouzena")).toBeVisible();
    await expect(eligibility.getByRole("link", { name: "Přejít k projektu a ověřit známé podmínky" })).toHaveCount(0);
    await expect(eligibility).toContainText("ověřte aktuální stav a podmínky u poskytovatele");
    await expect(page.locator(".next-action")).toContainText("poskytovatele");
    await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
    if (status === "ARCHIVED") {
      expect(detail.officialDetailUrl).toBeNull();
      await expect(page.locator(".next-action").getByRole("link", { name: "Hledat další výzvy" }))
        .toHaveAttribute("href", "/hledat");
      await expect(page.locator(".sticky-action").getByRole("link", { name: "Hledat další výzvy" }))
        .toHaveAttribute("href", "/hledat");
    } else {
      expect(detail.officialDetailUrl).toBeTruthy();
      const officialUrl = detail.officialDetailUrl!;
      await expect(page.locator(".next-action").getByRole("link", { name: "Ověřit stav u poskytovatele ↗" }))
        .toHaveAttribute("href", officialUrl);
      await expect(page.locator(".sticky-action").getByRole("link", { name: "Ověřit stav u poskytovatele ↗" }))
        .toHaveAttribute("href", officialUrl);
    }
    await expect(page.locator(".next-action").getByRole("link", { name: /projekt|žádost/i })).toHaveCount(0);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  }
  // Missing source-record presence is not a canonical cancellation: existing OPEN call stays actionable.
  const missing = await request.get("/api/grants/grant%3Ae2e%3Apage%3A22");
  expect((await missing.json()).status).toBe("OPEN");
  await page.goto("/dotace/grant%3Ae2e%3Apage%3A22");
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toBeVisible();
});
