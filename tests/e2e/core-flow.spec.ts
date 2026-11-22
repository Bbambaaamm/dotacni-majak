import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";

test("mobile filter sheet locks background gestures and restores document scrolling", async ({ page, request }) => {
  const api = await request.get("/api/search?intent=strankovani");
  expect(api.status()).toBe(200);
  expect((await api.json() as { results: unknown[] }).results.length).toBe(20);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  const previousStyles = await page.evaluate(() => {
    document.documentElement.style.setProperty("overflow", "auto", "important");
    document.body.style.setProperty("position", "relative");
    document.body.style.setProperty("top", "7px");
    document.body.style.setProperty("left", "3px");
    document.body.style.setProperty("width", "calc(100% - 3px)");
    document.body.style.setProperty("overflow", "visible");
    return { root: document.documentElement.style.cssText, body: document.body.style.cssText };
  });
  await page.evaluate(() => window.scrollTo(0, 500));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(500);
  const trigger = page.locator(".filter-panel summary");
  const dialog = page.getByRole("dialog", { name: "Upravit filtry a řazení" });
  await trigger.focus();
  const beforeOpenY = await page.evaluate(() => window.scrollY);
  expect(beforeOpenY).toBeGreaterThan(0);
  await page.keyboard.press("Enter");
  await expect(dialog).toBeVisible();
  const locked = await page.evaluate(() => ({
    y: window.scrollY, top: document.body.getBoundingClientRect().top,
    position: getComputedStyle(document.body).position,
    overflow: getComputedStyle(document.documentElement).overflow,
  }));
  expect(locked.position).toBe("fixed");
  expect(locked.overflow).toBe("hidden");
  await page.mouse.move(180, 40);
  await page.mouse.wheel(0, 400);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Input.synthesizeScrollGesture", {
    x: 180, y: 40, yDistance: -400, gestureSourceType: "touch", speed: 1000,
  });
  await expect.poll(() => page.evaluate(() => ({
    y: window.scrollY, top: document.body.getBoundingClientRect().top,
  }))).toEqual({ y: locked.y, top: locked.top });

  const sheet = page.locator(".filter-panel-shell");
  expect(await sheet.evaluate((node) => node.scrollHeight > node.clientHeight)).toBe(true);
  const box = await sheet.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.wheel(0, 350);
  await expect.poll(() => sheet.evaluate((node) => node.scrollTop)).toBeGreaterThan(0);
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Řazení všech odpovídajících výsledků").selectOption("DEADLINE");
  await expect(page).toHaveURL(/sort=DEADLINE/);
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(dialog).toBeVisible();
  expect(await page.evaluate(() => getComputedStyle(document.body).position)).toBe("fixed");
  // The loading view can shorten the document and clamp its scroll position;
  // closing must restore the position at the latest successful lock.
  const afterSearchY = await page.evaluate(() => -parseFloat(document.body.style.top));

  await dialog.getByRole("button", { name: "Zavřít filtry" }).click();
  await expect(dialog).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(afterSearchY);
  expect(await page.evaluate(() => ({ root: document.documentElement.style.cssText, body: document.body.style.cssText })))
    .toEqual(previousStyles);
  await page.mouse.move(180, 40);
  await page.mouse.wheel(0, 350);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(beforeOpenY);

  await trigger.click();
  await expect(dialog).toBeVisible();
  await page.setViewportSize({ width: 801, height: 844 });
  await expect(dialog).toHaveCount(0);
  expect(await page.evaluate(() => ({ root: document.documentElement.style.cssText, body: document.body.style.cssText })))
    .toEqual(previousStyles);
  const desktopY = await page.evaluate(() => window.scrollY);
  await page.mouse.move(180, 40);
  await page.mouse.wheel(0, 350);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(desktopY);
});

test("failed mobile filter search unlocks scrolling and real D1 retry reopens the sheet", async ({ page, request }) => {
  const api = await request.get("/api/search?intent=strankovani");
  expect(api.status()).toBe(200);
  expect((await api.json() as { results: unknown[] }).results).toHaveLength(20);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await page.evaluate(() => {
    // Keep the error view scrollable so this checks behavior as well as styles.
    document.querySelector<HTMLElement>(".results-page")!.style.minHeight = "2000px";
    window.scrollTo(0, 500);
  });
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(500);

  const dialog = page.getByRole("dialog", { name: "Upravit filtry a řazení" });
  await page.locator(".filter-panel summary").click();
  await expect(dialog).toBeVisible();
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).position)).toBe("fixed");

  let releaseFailure!: () => void;
  const heldFailure = new Promise<void>((resolve) => { releaseFailure = resolve; });
  let recover = false;
  await page.route("**/api/search?*", async (route) => {
    if (new URL(route.request().url()).searchParams.get("sort") !== "DEADLINE" || recover) {
      await route.continue();
      return;
    }
    await heldFailure;
    await route.fulfill({ status: 503, contentType: "application/json",
      body: JSON.stringify({ error: "SEARCH_UNAVAILABLE" }) });
  });
  await dialog.getByLabel("Řazení všech odpovídajících výsledků").selectOption("DEADLINE");
  await expect(page.getByText("Porovnáváme váš záměr s dostupnými výzvami.")).toBeVisible();
  await expect(dialog).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => ({
    position: getComputedStyle(document.body).position,
    overflow: getComputedStyle(document.documentElement).overflow,
  }))).toEqual({ position: "static", overflow: "visible" });

  releaseFailure();
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit.");
  const retry = page.getByRole("button", { name: "Zkusit vyhledávání znovu" });
  await expect(retry).toBeVisible();
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).position)).toBe("static");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.mouse.move(180, 400);
  await page.mouse.wheel(0, 350);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);

  recover = true;
  const response = page.waitForResponse((result) => result.url().includes("/api/search?") && result.status() === 200);
  await retry.click();
  expect(new URL((await response).url()).searchParams.get("sort")).toBe("DEADLINE");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(dialog).toBeVisible();
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).position)).toBe("fixed");
  const beforeCloseY = await page.evaluate(() => -parseFloat(document.body.style.top));
  await dialog.getByRole("button", { name: "Zavřít filtry" }).click();
  await expect(dialog).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(beforeCloseY);
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).position)).toBe("static");
});

test("mobile filters form a keyboard-contained sheet over real D1 search", async ({ page, request }) => {
  const api = await request.get("/api/search?intent=digitalizace%20obce");
  expect(api.status()).toBe(200);
  expect((await api.json() as { results: unknown[] }).results.length).toBeGreaterThan(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce");
  await expect(page.locator(".grant-card")).toHaveCount(2);
  const trigger = page.locator(".filter-panel summary");
  const dialog = page.getByRole("dialog", { name: "Upravit filtry a řazení" });
  await expect(dialog).toHaveCount(0);
  await expect(page.getByLabel("Stav výzvy")).toBeHidden();
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  await expect(dialog.getByRole("button", { name: "Zavřít filtry" })).toBeFocused();
  await dialog.locator("summary").focus();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByLabel("Řazení všech odpovídajících výsledků")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.locator("summary")).toBeFocused();
  await page.evaluate(() => document.querySelector<HTMLElement>(".grant-card a")?.focus());
  expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  await dialog.getByLabel("Stav výzvy").selectOption("OPEN");
  await expect(page).toHaveURL(/status=OPEN/);
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Zavřít filtry" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(page.getByLabel("Stav výzvy")).toBeHidden();
  await page.keyboard.press("Tab");
  expect(await page.locator(".filter-panel").evaluate((node) => node.contains(document.activeElement))).toBe(false);
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.setViewportSize({ width: 800, height: 844 });
  await trigger.click();
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  const closeOnResize = dialog.getByRole("button", { name: "Zavřít filtry" });
  await closeOnResize.focus();
  await expect(closeOnResize).toBeFocused();
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).position)).toBe("fixed");
  await page.setViewportSize({ width: 801, height: 844 });
  await expect(page.locator(".filter-panel")).toHaveAttribute("open");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(page.getByRole("button", { name: "Zavřít filtry" })).toBeHidden();
  expect(await page.locator(".results-list").evaluate((node) => (node as HTMLElement).inert)).toBe(false);
  await expect.poll(() => page.evaluate(() => ({
    position: getComputedStyle(document.body).position,
    overflow: getComputedStyle(document.documentElement).overflow,
  }))).toEqual({ position: "static", overflow: "visible" });
  await page.setViewportSize({ width: 800, height: 844 });
  await expect(page.locator(".filter-panel")).not.toHaveAttribute("open");
  await trigger.click();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("real search keeps decision cautions visible and filter mechanics accessible", async ({ page, request }) => {
  const api = await request.get("/api/search?intent=digitalizace%20obce");
  expect(api.status()).toBe(200);
  const response = await api.json() as { results: unknown[] };
  expect(response.results.length).toBeGreaterThan(0);

  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/hledat?intent=digitalizace%20obce");
    const heading = page.getByRole("heading", { name: "Nalezené možnosti" });
    await expect(heading).toBeVisible();
    const section = page.getByRole("region", { name: "Nalezené možnosti" });
    await expect(section.getByText(`Načtené výsledky: ${response.results.length}.`, { exact: false })).toBeVisible();
    await expect(section.getByText("Relevance není posouzením způsobilosti ani výše podpory.", { exact: false })).toBeVisible();
    await expect(section.getByText("před podáním ověřte aktuální příjem žádostí", { exact: false })).toBeVisible();
    const explanation = section.locator("details.detail-section");
    await expect(explanation).not.toHaveAttribute("open");
    await expect(explanation.getByText("Počet načtených výsledků není počet všech odpovídajících výzev.", { exact: false })).toBeHidden();
    await explanation.locator("summary").focus();
    await page.keyboard.press("Enter");
    await expect(explanation).toHaveAttribute("open");
    await expect(explanation.getByText("Počet načtených výsledků není počet všech odpovídajících výzev.", { exact: false })).toBeVisible();
    await expect(page.locator(".grant-card")).toHaveCount(response.results.length);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
});

test("mobile search rejects blank decision identities and retries the real D1/API", async ({ page, request }) => {
  const path = "/hledat?intent=digitalizace%20obce";
  const api = await request.get("/api/search?intent=digitalizace%20obce");
  expect(api.status()).toBe(200);
  const actual = await api.json() as { results: Array<{ grantCallVersionId: string; grantCallId: string }> };
  expect(actual.results.length).toBeGreaterThan(0);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const field of ["grantCallVersionId", "grantCallId"] as const) {
    let corrupt = true;
    const corruptIdentity = async (route: import("@playwright/test").Route) => {
      if (!corrupt) return route.continue();
      const response = await route.fetch();
      const body = await response.json() as typeof actual;
      expect(response.ok()).toBe(true);
      await route.fulfill({ response, json: { ...body, results: [
        { ...body.results[0], [field]: "   " }, ...body.results.slice(1),
      ] } });
    };
    await page.route("**/api/search?*", corruptIdentity);
    await page.goto(path);
    await expect(page.getByRole("heading", { name: "Výsledky teď neumíme bezpečně zobrazit." })).toBeVisible();
    await expect(page.locator(".grant-card")).toHaveCount(0);
    corrupt = false;
    await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
    await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.unroute("**/api/search?*", corruptIdentity);
  }
});

test("mobile search rejects reordered provider counts and retries actual D1/API", async ({ page, request }) => {
  const path = "/hledat?intent=digitalizace%20obce";
  const api = await request.get("/api/search?intent=digitalizace%20obce");
  expect(api.status()).toBe(200);
  const actual = await api.json() as { facets: { providers: Array<{ name: string; count: number }> } | null };
  expect(actual.facets?.providers.length).toBeGreaterThanOrEqual(2);
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const fresh = await route.fetch();
    const body = await fresh.json() as typeof actual;
    expect(body.facets?.providers.length).toBeGreaterThanOrEqual(2);
    await route.fulfill({ response: fresh, json: { ...body, facets: {
      ...body.facets, providers: [...body.facets!.providers].reverse(),
    } } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Výsledky teď neumíme bezpečně zobrazit." })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(2);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("mobile search rejects phantom continuation cursor and retries real D1/API", async ({ page, request }) => {
  const path = "/hledat?intent=digitalizace%20obce";
  const api = await request.get("/api/search?intent=digitalizace%20obce");
  expect(api.status()).toBe(200);
  const actual = await api.json() as { results: unknown[]; facets: { status: Record<string, number> } | null; nextCursor: string | null };
  expect(actual.nextCursor).toBeNull();
  expect(actual.facets).not.toBeNull();
  expect(Object.values(actual.facets!.status).reduce((total, count) => total + count, 0)).toBe(actual.results.length);
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const fresh = await route.fetch();
    const body = await fresh.json() as typeof actual;
    await route.fulfill({ response: fresh, json: { ...body, nextCursor: "phantom-page" } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Výsledky teď neumíme bezpečně zobrazit." })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(actual.results.length);
  await expect(page.getByRole("button", { name: "Načíst další výsledky" })).toHaveCount(0);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("mobile search rejects unsupported ontology claim then retries real D1/API results", async ({ page, request }) => {
  const path = "/hledat?intent=digitalizace%20obce";
  const response = await request.get("/api/search?intent=digitalizace%20obce");
  expect(response.status()).toBe(200);
  const actual = await response.json() as { results: Array<{ matchKind: string }> };
  expect(actual.results.some((item) => item.matchKind === "DIRECT")).toBe(true);
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const fresh = await route.fetch();
    const body = await fresh.json() as typeof actual;
    await route.fulfill({ response: fresh, json: { ...body, expandedTerms: [],
      results: body.results.map((item) => ({ ...item, matchKind: "ONTOLOGY" })) } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Výsledky teď neumíme bezpečně zobrazit." })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.locator(".grant-card").first()).toContainText("Přímá tematická shoda");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("mobile continuation rejects changed ontology explanation and retries real D1 page", async ({ page, request }) => {
  const path = "/hledat?intent=strankovani";
  const first = await request.get("/api/search?intent=strankovani");
  expect(first.status()).toBe(200);
  const initial = await first.json() as { expandedTerms: string[]; nextCursor: string | null };
  expect(initial.nextCursor).toBeTruthy();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.locator(".grant-card")).toHaveCount(20);
  let corrupt = true;
  await page.route("**/api/search?*cursor=*", async (route) => {
    if (!corrupt) return route.continue();
    const fresh = await route.fetch();
    const body = await fresh.json() as { expandedTerms: string[]; results: Array<{ matchKind: string }> };
    expect(body.expandedTerms).toEqual(initial.expandedTerms);
    await route.fulfill({ response: fresh, json: { ...body,
      expandedTerms: [...body.expandedTerms, "nepodložený pojem"],
      results: body.results.map((item) => ({ ...item, matchKind: "ONTOLOGY" })) } });
  });
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("alert")).toContainText("Dosud načtené výsledky zůstávají zobrazené");
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit načíst další znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("mobile continuation rejects injected facet counts and retries real D1/API page", async ({ page, request }) => {
  const path = "/hledat?intent=strankovani";
  const first = await request.get("/api/search?intent=strankovani");
  expect(first.status()).toBe(200);
  const initial = await first.json() as { facets: unknown; nextCursor: string | null };
  expect(initial.facets).not.toBeNull();
  expect(initial.nextCursor).toBeTruthy();
  const next = await request.get(`/api/search?intent=strankovani&cursor=${encodeURIComponent(initial.nextCursor!)}`);
  expect(next.status()).toBe(200);
  const continuation = await next.json() as { facets: unknown; results: unknown[] };
  expect(continuation.facets).toBeNull();
  expect(continuation.results.length).toBe(5);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.locator(".grant-card")).toHaveCount(20);
  let corrupt = true;
  await page.route("**/api/search?*cursor=*", async (route) => {
    if (!corrupt) return route.continue();
    const fresh = await route.fetch();
    const body = await fresh.json() as typeof continuation;
    expect(body.facets).toBeNull();
    await route.fulfill({ response: fresh, json: { ...body, facets: initial.facets } });
  });
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("alert")).toContainText("Dosud načtené výsledky zůstávají zobrazené");
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit načíst další znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("search cards show current indexed version provenance and freshness limits from real D1/API", async ({ page, request }) => {
  for (const sort of ["RELEVANCE", "DEADLINE"] as const) {
    const query = new URLSearchParams({ intent: "digitalizace obce", status: "OPEN", sort });
    const api = await request.get(`/api/search?${query}`);
    expect(api.status()).toBe(200);
    const body = await api.json() as { results: Array<{ grantCallVersionId: string; capturedAt: string; verificationStatus: string }> };
    expect(body.results.map((row) => row.grantCallVersionId)).not.toContain("gcv-e2e-open-stale");
    expect(body.results).toContainEqual(expect.objectContaining({ grantCallVersionId: "gcv-e2e-open",
      capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED" }));
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto(`/hledat?${query}`);
      const card = page.locator(".grant-card").filter({ has: page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" }) });
      await expect(card).toBeVisible();
      await expect(page.getByRole("heading", { name: "E2E zastaralá výzva — digitalizace obce" })).toHaveCount(0);
      await expect(card.locator(".facts")).toContainText("Verze zachycena26. září 2026");
      await expect(card.locator(".facts")).toContainText("Ověření zachycené verzeOvěřeno");
      await expect(card.getByRole("note")).toContainText("nepotvrzují aktuální podmínky nebo příjem žádostí");
      await expect(card).toContainText("Otevřeno v zachycené verzi");
    }
  }
});

test("detail excludes colliding foreign evidence identities from real D1/API on mobile", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { evidence: Array<{ id: string }> };
  expect(detail.evidence.map((item) => item.id)).toEqual(expect.arrayContaining([
    "e2e-fe-title", "e2e-fe-summary", "e2e-fe-deadline", "e2e-fe-funding",
  ]));
  expect(detail.evidence.map((item) => item.id)).not.toContain("e2e-fe-collision-call");
  expect(detail.evidence.map((item) => item.id)).not.toContain("e2e-fe-collision-version");
  expect(detail.evidence).toHaveLength(5);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  const evidence = page.getByRole("complementary", { name: "Oficiální zdroje" });
  await evidence.getByText("Konkrétní evidence (5)").click();
  await expect(evidence.locator("details li")).toHaveCount(5);
  await expect(page.getByRole("link", { name: /Doklad termínu.*str\. 2/ })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("detail marks only malformed source deadline from real D1/API at mobile width", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Aunsafe-url";
  const response = await request.get("/api/grants/grant%3Ae2e%3Aunsafe-url");
  expect(response.status()).toBe(200);
  const detail = await response.json() as {
    submissionCloseAt: string | null;
    deadlines: Array<{ id: string; startsAt: string | null; endsAt: string | null; evidenceId: string | null }>;
  };
  expect(detail.submissionCloseAt).toBeNull();
  expect(detail.deadlines.find((item) => item.id === "e2e-deadline-uncertain"))
    .toMatchObject({ startsAt: "2027-06-01", endsAt: "datum-nejasne", evidenceId: null });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  const quickFacts = page.getByRole("heading", { name: "Rychlý přehled" }).locator("..");
  await expect(quickFacts.getByText("Není uvedeno")).toHaveCount(2);
  await expect(quickFacts.getByRole("note")).toHaveCount(0);
  const deadline = page.getByRole("region", { name: "Termíny podle zdroje" })
    .locator("li").filter({ hasText: "Syntetický neověřený termín" });
  await expect(deadline).toContainText("datum-nejasne");
  await expect(deadline.getByRole("note")).toContainText("Formát termínu není ověřen");
  await expect(deadline.getByRole("note")).toHaveCount(1);
  await expect(deadline).toContainText("Samostatný doklad termínu není připojen");
  await expect(deadline).not.toContainText("Ověření doloženého údaje:");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("detail warns on a reversed deadline from real D1/API without inventing a valid window", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Aunsafe-url");
  expect(response.status()).toBe(200);
  const detail = await response.json() as {
    deadlines: Array<{ id: string; startsAt: string | null; endsAt: string | null }>;
  };
  expect(detail.deadlines.find((item) => item.id === "e2e-deadline-reversed"))
    .toMatchObject({ startsAt: "2027-06-02", endsAt: "2027-06-01" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Aunsafe-url");
  const row = page.getByRole("region", { name: "Termíny podle zdroje" })
    .locator("li").filter({ hasText: "Syntetický obrácený interval" });
  await expect(row.getByRole("note")).toContainText("Interval nelze bezpečně vyložit");
  await expect(row).toContainText("2027-06-02");
  await expect(row).toContainText("2027-06-01");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("unverifiable document retrieval date from real D1/API is cautioned on mobile detail", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Aunsafe-url";
  const response = await request.get("/api/grants/grant%3Ae2e%3Aunsafe-url");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { evidence: Array<{ id: string; retrievedAt: string; documentTitle: string | null; fieldPath: string; sourceUrl: string }> };
  expect(detail.evidence.find((item) => item.id === "e2e-fe-uncertain"))
    .toMatchObject({ retrievedAt: "2026-02-30T12:00:00Z", documentTitle: null,
      fieldPath: "/summary", sourceUrl: "https://example.invalid/e2e/uncertain-source" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: "E2E výzva — bezpečnost odkazu" })).toBeVisible();
  const evidence = page.getByRole("complementary", { name: "Oficiální zdroje" });
  await evidence.getByText("Konkrétní evidence (1)").click();
  const row = evidence.locator("details li").filter({ hasText: "Doklad bez uvedeného názvu dokumentu" });
  await expect(row.getByRole("link", { name: "Doklad bez uvedeného názvu dokumentu ↗" }))
    .toHaveAttribute("href", "https://example.invalid/e2e/uncertain-source");
  await expect(row).not.toContainText("/summary");
  await expect(row).toContainText("str. 1");
  await expect(row).toContainText("Dokument stažen: 2026-02-30T12:00:00Z");
  await expect(row.getByRole("note")).toContainText("nepovažujte jej za doloženou aktuálnost");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("JPY minor units from real D1/API render as major JPY on mobile detail", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Ajpy");
  expect(response.status()).toBe(200);
  const detail = await response.json() as {
    fundingScenarios: Array<{ id: string; currencyCode: string; grantAmountMaxMinor: number }>;
  };
  expect(detail.fundingScenarios).toEqual([expect.objectContaining({
    id: "e2e-funding-jpy", currencyCode: "JPY", grantAmountMaxMinor: 1234,
  })]);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Ajpy");
  await expect(page.getByRole("heading", { level: 1, name: "E2E měnová přesnost JPY" })).toBeVisible();
  const finance = page.getByRole("region", { name: "Finance" });
  await expect(finance.getByText("Maximální dotace", { exact: true }).locator(".."))
    .toContainText(new Intl.NumberFormat("cs-CZ", { style: "currency", currency: "JPY" }).format(1234));
  await expect(finance).toContainText("vlastních peněz");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("unknown call status in a 200 detail fails closed then retries real D1 status", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Aopen";
  const actual = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { status: string; versions: Array<{ status: string; isCurrent: boolean }> };
  expect(valid.status).toBe("OPEN");
  expect(valid.versions.find((item) => item.isCurrent)?.status).toBe("OPEN");
  let corrupt = true;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    await route.fulfill({ response, json: { ...body, status: "OPENED",
      versions: body.versions.map((item) => item.isCurrent ? { ...item, status: "OPENED" } : item),
    } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByText("Otevřeno v zachycené verzi").first()).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("blank provider in a successful detail fails closed then retries real D1/API identity", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Aopen";
  const actual = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { provider: { name: string }; title: string };
  expect(valid.provider.name.trim()).not.toBe("");
  let corrupt = true;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    await route.fulfill({ response, json: { ...body, provider: { ...body.provider, name: "  " } } });
  });
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    corrupt = true;
    await page.goto(path);
    await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
    await expect(page.locator(".detail-hero")).toHaveCount(0);
    corrupt = false;
    await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
    await expect(page.getByRole("heading", { level: 1, name: valid.title })).toBeVisible();
    await expect(page.locator(".detail-hero")).toContainText(valid.provider.name);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
});

test("mobile detail rejects oversized evidence and retries actual D1/API provenance", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Aopen";
  const actual = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { evidence: Array<{ id: string }> };
  expect(valid.evidence.length).toBeGreaterThan(0);
  expect(valid.evidence.length).toBeLessThan(100);
  let corrupt = true;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    await route.fulfill({ response, json: { ...body,
      evidence: Array.from({ length: 101 }, (_, index) => ({ ...body.evidence[0], id: `oversize-${index}` })),
    } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Doklad termínu.*str\. 2/ })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("mobile detail shows unfamiliar source payment mode without calling it undocumented, then safely retries malformed data", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Aopen";
  const actual = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { fundingScenarios: Array<{ paymentMode: string | null }> };
  expect(valid.fundingScenarios.some((item) => item.paymentMode === "REIMBURSEMENT")).toBe(true);
  let paymentMode: unknown = "CASH";
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (paymentMode === null) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    await route.fulfill({ response, json: { ...body, fundingScenarios: body.fundingScenarios.map((item, index) =>
      index === 0 ? { ...item, paymentMode } : item) } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByText("Jiný režim uvedený u scénáře: CASH. Ověřte způsob platby u poskytovatele.")).toBeVisible();
  paymentMode = 7;
  await page.reload();
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Finance" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  paymentMode = null;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByText("Proplacení po úhradě nákladů")).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("unknown requirement necessity in a 200 detail fails closed then retries real D1 requirement", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Aopen";
  const actual = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { requirements: Array<{ necessity: string }> };
  expect(valid.requirements.some((item) => item.necessity === "REQUIRED")).toBe(true);
  let corrupt = true;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    await route.fulfill({ response, json: { ...body, requirements: body.requirements.map((item, index) =>
      index === 0 ? { ...item, necessity: "MANDATORY" } : item) } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Požadavky a přílohy" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Požadavky a přílohy" })).toBeVisible();
  await expect(page.getByText(/Povinné:/).first()).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("unknown source presence in a 200 detail fails closed then retries real D1 source", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Aopen";
  const actual = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { sources: Array<{ presenceState: string }> };
  expect(valid.sources.some((source) => source.presenceState === "SEEN")).toBe(true);
  let corrupt = true;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    await route.fulfill({ response, json: { ...body, sources: body.sources.map((source, index) =>
      index === 0 ? { ...source, presenceState: "CANCELLED" } : source) } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByText("Poslední pozorování záznamu u zdroje")).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("invalid provenance page in a 200 detail fails closed, then retries real D1 evidence", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Aopen";
  const actual = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { evidence: Array<{ id: string; pageFrom: number | null; pageTo: number | null }> };
  const deadline = valid.evidence.find((item) => item.id === "e2e-fe-deadline");
  expect(deadline).toMatchObject({ pageFrom: 2, pageTo: 2 });
  let corrupt = true;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    await route.fulfill({ response, json: { ...body, evidence: body.evidence.map((item) =>
      item.id === "e2e-fe-deadline" ? { ...item, pageFrom: 3, pageTo: 2 } : item) } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("link", { name: /Doklad termínu/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Doklad termínu.*str\. 2/ })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("contradictory detail availability fails closed then recovers from real D1 API", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Aopen";
  const actual = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { requirements: unknown[]; availability: { requirements: string } };
  expect(valid.requirements.length).toBeGreaterThan(0);
  expect(valid.availability.requirements).toBe("AVAILABLE");
  let corrupt = true;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ response, json: { ...body, availability: { ...body.availability, requirements: "UNKNOWN" } } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Požadavky a přílohy" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Přidat k projektu" })).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Požadavky a přílohy" })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("contradictory current-version history fails closed then retries real D1 detail", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Ahistory";
  const actual = await request.get("/api/grants/grant%3Ae2e%3Ahistory");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { versionId: string; versions: Array<{ id: string; isCurrent: boolean }> };
  expect(valid.versions.find((version) => version.isCurrent)?.id).toBe(valid.versionId);
  let corrupt = true;
  await page.route("**/api/grants/grant%3Ae2e%3Ahistory", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    await route.fulfill({ response, json: { ...body, versions: body.versions.map((version) =>
      version.isCurrent ? { ...version, status: "CANCELLED" } : version) } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E historie verzí" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E historie verzí" })).toBeVisible();
  await expect(page.locator(".detail-hero")).toContainText("Otevřeno v zachycené verzi");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("out-of-order historical versions fail closed, then retry real D1 detail on mobile", async ({ page, request }) => {
  const path = "/dotace/grant%3Ae2e%3Areactivated";
  const actual = await request.get("/api/grants/grant%3Ae2e%3Areactivated");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as {
    versionId: string;
    versions: Array<{ id: string; versionNumber: number; isCurrent: boolean }>;
  };
  expect(valid.versions[0]).toMatchObject({ id: valid.versionId, isCurrent: true, versionNumber: 1 });
  expect(valid.versions[1].versionNumber).toBeGreaterThan(valid.versions[2].versionNumber);
  let corrupt = true;
  await page.route("**/api/grants/grant%3Ae2e%3Areactivated", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    const versions = [...body.versions];
    [versions[1], versions[2]] = [versions[2], versions[1]];
    await route.fulfill({ response, json: { ...body, versions } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E reaktivovaná verze" })).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E reaktivovaná verze" })).toBeVisible();
  const history = page.locator("details.detail-section").filter({ hasText: "Historie verzí" });
  await history.getByText("Historie verzí (20 zobrazených)").click();
  await expect(history.locator("li").first()).toContainText("Verze 1 ·");
  await expect(history.locator("li").nth(1)).toContainText("Verze 22 ·");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("reactivated older version remains current outside the newest 20 D1 versions", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Areactivated");
  expect(response.status()).toBe(200);
  const detail = await response.json() as {
    versionId: string;
    versionNumber: number;
    versions: Array<{ id: string; versionNumber: number; isCurrent: boolean }>;
  };
  expect(detail.versionId).toBe("gcv-e2e-reactivated-1");
  expect(detail.versionNumber).toBe(1);
  expect(detail.versions).toHaveLength(20);
  expect(detail.versions[0]).toMatchObject({ id: detail.versionId, isCurrent: true });
  expect(detail.versions[1]).toMatchObject({ versionNumber: 22, isCurrent: false });
  expect(detail.versions[19]).toMatchObject({ versionNumber: 4, isCurrent: false });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Areactivated");
  await expect(page.getByRole("heading", { level: 1, name: "E2E reaktivovaná verze" })).toBeVisible();
  const history = page.locator("details.detail-section").filter({ hasText: "Historie verzí" });
  await history.getByText("Historie verzí (20 zobrazených)").click();
  await expect(history.locator("li")).toHaveCount(20);
  await expect(history.locator("li").first()).toContainText("Verze 1 ·");
  await expect(history.locator("li").first()).toContainText("aktuální");
  await expect(history.locator("li").nth(1)).toContainText("Verze 22 ·");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

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
    await expect(card.getByRole("note").filter({ hasText: "chybějící odkaz neznamená zrušení výzvy" }))
      .toHaveCount(1);
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

test("unfiltered facet totals agree across status and deadline in real D1 search and fail closed on contradiction", async ({ page, request }) => {
  const intent = "digitalizace obce";
  const response = await request.get(`/api/search?intent=${encodeURIComponent(intent)}`);
  expect(response.status()).toBe(200);
  const body = await response.json() as {
    results: Array<{ grantCallId: string }>;
    facets: { status: Record<string, number>; deadline: Record<string, number> } | null;
  };
  expect(body.results).toHaveLength(2);
  expect(body.facets).not.toBeNull();
  expect(Object.values(body.facets!.status).reduce((sum, count) => sum + count, 0))
    .toBe(Object.values(body.facets!.deadline).reduce((sum, count) => sum + count, 0));
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/hledat?intent=${encodeURIComponent(intent)}`);
    await expect(page.locator(".grant-card")).toHaveCount(body.results.length);
    if (width === 390) await page.locator(".filter-panel summary").click();
    await expect(page.getByLabel("Stav výzvy")).toBeVisible();
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const actual = await route.fetch();
    const real = await actual.json() as typeof body;
    expect(actual.ok()).toBe(true);
    expect(real.facets).not.toBeNull();
    await route.fulfill({ response: actual, json: { ...real, facets: {
      ...real.facets!, status: { ...real.facets!.status, OPEN: real.facets!.status.OPEN + 1 },
    } } });
  });
  await page.goto(`/hledat?intent=${encodeURIComponent(intent)}`);
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(body.results.length);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
});

test("complete provider facet totals agree with real D1 and contradictions fail closed", async ({ page, request }) => {
  const intent = "digitalizace obce";
  const path = `/hledat?intent=${encodeURIComponent(intent)}`;
  const actual = await request.get(`/api/search?intent=${encodeURIComponent(intent)}`);
  expect(actual.status()).toBe(200);
  const body = await actual.json() as { results: unknown[]; facets: {
    status: Record<string, number>; providers: Array<{ name: string; count: number }>;
    providersTruncated: boolean;
  } | null };
  expect(body.results.length).toBeGreaterThan(0);
  expect(body.facets).not.toBeNull();
  expect(body.facets!.providersTruncated).toBe(false);
  expect(body.facets!.providers.length).toBeGreaterThan(0);
  expect(body.facets!.providers.reduce((sum, item) => sum + item.count, 0))
    .toBe(Object.values(body.facets!.status).reduce((sum, count) => sum + count, 0));
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(path);
    await expect(page.locator(".grant-card")).toHaveCount(body.results.length);
    if (width === 390) await page.locator(".filter-panel summary").click();
    await expect(page.getByLabel("Přesný název poskytovatele")).toBeVisible();
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const real = await response.json() as typeof body;
    expect(response.ok()).toBe(true);
    expect(real.facets).not.toBeNull();
    await route.fulfill({ response, json: { ...real, facets: { ...real.facets!,
      providers: real.facets!.providers.map((item, index) => index === 0
        ? { ...item, count: item.count + 1 } : item),
    } } });
  });
  await page.goto(path);
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(body.results.length);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
});

test("applied results filters survive refresh and link sharing against real D1", async ({ page, request, browser }) => {
  const intent = "digitalizace obce";
  const filtered = await request.get(`/api/search?intent=${encodeURIComponent(intent)}&status=OPEN&sort=DEADLINE`);
  expect(filtered.status()).toBe(200);
  expect((await filtered.json() as { results: Array<{ grantCallVersionId: string }> }).results.map((row) => row.grantCallVersionId))
    .toEqual(["gcv-e2e-open"]);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/hledat?intent=${encodeURIComponent(intent)}`);
    await expect(page.locator(".grant-card")).toHaveCount(2);
    if (width === 390) await page.locator(".filter-panel summary").click();
    await page.getByLabel("Stav výzvy").selectOption("OPEN");
    await expect(page.locator(".grant-card")).toHaveCount(1);
    await page.getByLabel("Řazení všech odpovídajících výsledků").selectOption("DEADLINE");
    await expect(page.locator(".grant-card").getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
    const savedUrl = new URL(page.url());
    expect(savedUrl.searchParams.get("status")).toBe("OPEN");
    expect(savedUrl.searchParams.get("sort")).toBe("DEADLINE");
    expect(savedUrl.searchParams.has("cursor")).toBe(false);
    await page.reload();
    await expect(page.getByLabel("Stav výzvy")).toHaveValue("OPEN");
    await expect(page.getByLabel("Řazení všech odpovídajících výsledků")).toHaveValue("DEADLINE");
    await expect(page.locator(".grant-card")).toHaveCount(1);
    const sharedContext = await browser.newContext({ viewport: { width, height: 844 } });
    try {
      const shared = await sharedContext.newPage();
      await shared.goto(savedUrl.toString());
      await expect(shared.locator(".grant-card")).toHaveCount(1);
      await expect(shared.getByLabel("Stav výzvy")).toHaveValue("OPEN");
      expect((await new AxeBuilder({ page: shared }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
      expect(await shared.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    } finally {
      await sharedContext.close();
    }
  }
});

test("filtered empty state can clear all controls and retry real D1 search", async ({ page, request }) => {
  const intent = "digitalizace obce";
  const filteredUrl = `/hledat?${new URLSearchParams({ intent, status: "OPEN", provider: "E2E test provider B", sort: "DEADLINE" })}`;
  const filtered = await request.get(`/api/search?${new URL(filteredUrl, "http://localhost").searchParams}`);
  expect(filtered.status()).toBe(200);
  expect((await filtered.json()).results).toHaveLength(0);
  const unfiltered = await request.get(`/api/search?intent=${encodeURIComponent(intent)}&sort=DEADLINE`);
  expect(unfiltered.status()).toBe(200);
  expect((await unfiltered.json()).results).toHaveLength(2);

  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(filteredUrl);
    const empty = page.locator(".filter-empty");
    await expect(empty).toContainText("Zkuste některý filtr upravit nebo zrušit");
    await expect(page.locator(".grant-card")).toHaveCount(0);
    const clear = empty.getByRole("button", { name: "Zrušit všechny filtry a hledat znovu" });
    await clear.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator(".grant-card")).toHaveCount(2);
    await expect(empty).toHaveCount(0);
    await expect(page.locator(".filter-panel summary")).toBeFocused();
    const params = new URL(page.url()).searchParams;
    expect(params.get("intent")).toBe(intent);
    expect(params.get("sort")).toBe("DEADLINE");
    expect(params.has("status")).toBe(false);
    expect(params.has("provider")).toBe(false);
    await expect(page.getByLabel("Řazení všech odpovídajících výsledků")).toHaveValue("DEADLINE");
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
});

test("editing a filtered search intent starts a new real D1 search without stale filters", async ({ page, request }) => {
  const nextIntent = "bezpecnost odkazu";
  const next = await request.get(`/api/search?intent=${encodeURIComponent(nextIntent)}`);
  expect(next.status()).toBe(200);
  expect((await next.json() as { results: Array<{ grantCallVersionId: string }> }).results.map((row) => row.grantCallVersionId))
    .toEqual(["gcv-e2e-unsafe-url"]);

  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/hledat?${new URLSearchParams({ intent: "digitalizace obce", status: "OPEN", provider: "E2E test provider B" })}`);
    await expect(page.locator(".filter-empty")).toBeVisible();
    await page.getByText("Upravit záměr", { exact: true }).click();
    const input = page.getByRole("textbox", { name: "Popis záměru" });
    await expect(input).toHaveValue("digitalizace obce");
    await input.fill(nextIntent);
    await page.getByRole("button", { name: "Hledat upravený záměr" }).click();
    await expect(page.locator(".grant-card").getByRole("heading", { name: "E2E výzva — bezpečnost odkazu" })).toBeVisible();
    const params = new URL(page.url()).searchParams;
    expect(params.get("intent")).toBe(nextIntent);
    expect(params.has("status")).toBe(false);
    expect(params.has("provider")).toBe(false);
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
    if (width === 390) await page.getByRole("button", { name: "Zavřít filtry" }).click();
    await clearBudget.click();
    await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toHaveCount(0);
    await expect(page.getByLabel("Stav výzvy")).toHaveValue("OPEN");
    await expect(page.getByLabel("Typ financování", { exact: true })).toHaveValue("GRANT");
    await expect(page.getByRole("button", { name: "Zrušit filtr Náklady projektu: 500000 Kč" })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    if (width === 390) await page.locator(".filter-panel summary").click();
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

  await page.getByRole("button", { name: "Zavřít filtry" }).click();
  await card.getByRole("link", { name: "Zobrazit detail" }).click();
  const why = page.getByRole("region", { name: "Proč ji vidíte" });
  await expect(why).toContainText("kontext hledání záměru „digitalizace obce“");
  await expect(why).toContainText("Tematická relevance není posouzení způsobilosti");
  await expect(page.locator(".detail-hero")).toContainText("Otevřeno v zachycené verzi");
  await expect(page.locator(".detail-hero")).toContainText("Před podáním ověřte aktuální stav v oficiálním zdroji.");
  await expect(page.locator(".detail-hero")).not.toContainText("Lze podat žádost");
  await expect(page.locator(".detail-section").filter({ has: page.getByRole("heading", { name: "Rychlý přehled" }) })).toContainText("Otevřeno v zachycené verzi");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const backToResults = page.getByRole("link", { name: "← Zpět na výsledky" });
  await expect(backToResults).toHaveAttribute("href", "/hledat?intent=digitalizace+obce&status=OPEN&returnResult=gcv-e2e-open");
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
    .toHaveAttribute("href", "/dotace/grant%3Ae2e%3Aopen?intent=digitalizace%20obce&returnResult=gcv-e2e-open");
  await card.getByRole("link", { name: "Zobrazit detail" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  const why = page.getByRole("region", { name: "Proč ji vidíte" });
  await expect(why).toContainText("kontext hledání záměru „digitalizace obce“");
  await expect(why).toContainText("Samotný odkaz ani tento detail nepotvrzují konkrétní tematickou shodu");
  await expect(why).toContainText("Tematická relevance není posouzení způsobilosti");
  await expect(why.getByRole("link", { name: "výsledcích hledání" })).toHaveAttribute("href", "/hledat?intent=digitalizace+obce&returnResult=gcv-e2e-open");
  await page.getByRole("link", { name: "← Zpět na výsledky" }).click();
  await expect(page).toHaveURL(/\/hledat\?intent=digitalizace\+obce$/);
  await expect(card).toBeVisible();
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByRole("link", { name: "← Zpět na výsledky" })).toHaveAttribute("href", "/hledat");
  await expect(page.getByRole("region", { name: "Proč ji vidíte" })).toContainText("Tento detail neobsahuje individuální vysvětlení");
  await page.goto("/dotace/grant%3Ae2e%3Aopen?intent=%20%20");
  await expect(page.getByRole("link", { name: "← Zpět na výsledky" })).toHaveAttribute("href", "/hledat");
  await expect(page.getByRole("region", { name: "Proč ji vidíte" })).toContainText("Tento detail neobsahuje individuální vysvětlení");
  await page.goto("/dotace/grant%3Ae2e%3Aopen?intent=libovolny&returnResult=cizi-verze");
  await expect(page.getByRole("region", { name: "Proč ji vidíte" })).toContainText("Tento detail neobsahuje individuální vysvětlení");
  const unrelated = "neexistujici-zamer-xyz";
  const noMatch = await request.get(`/api/search?intent=${unrelated}`);
  expect(noMatch.status()).toBe(200);
  expect((await noMatch.json()).results).toEqual([]);
  await page.goto(`/dotace/grant%3Ae2e%3Aopen?intent=${unrelated}&returnResult=gcv-e2e-open`);
  const untrustedContext = page.getByRole("region", { name: "Proč ji vidíte" });
  await expect(untrustedContext).toContainText("Pokud se výzva stále objevuje");
  await expect(untrustedContext).toContainText("jinak upravte hledání");
  await untrustedContext.getByRole("link", { name: "výsledcích hledání" }).click();
  await expect(page.getByRole("heading", { name: "Maják může hledat dál." })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(0);
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

test("unverified change date from real D1/API remains visible with caution on mobile", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Areactivated");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { changes: Array<{ id: string; changeType: string; severity: string; fieldPath: string; createdAt: string; oldValue: unknown; newValue: unknown }> };
  expect(detail.changes).toHaveLength(2);
  expect(detail.changes).toContainEqual(expect.objectContaining({
    id: "e2e-change-unverified-date", changeType: "OTHER", severity: "CRITICAL", fieldPath: "/e2e/unverified-date",
    createdAt: "2026-02-30T12:00:00Z",
  }));
  expect(detail.changes).toContainEqual(expect.objectContaining({
    id: "e2e-change-status", changeType: "STATUS_CHANGED", fieldPath: "/status",
    oldValue: "CLOSED", newValue: "OPEN",
  }));

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Areactivated");
  await expect(page.getByRole("heading", { level: 1, name: "E2E reaktivovaná verze" })).toBeVisible();
  const changes = page.locator("section.detail-section").filter({ has: page.getByRole("heading", { name: "Poslední změny (2)" }) });
  const unverified = changes.locator("li").filter({ hasText: "Jiná zaznamenaná změna" });
  const transition = changes.locator("li").filter({ hasText: "Změna stavu výzvy" });
  await expect(transition).toContainText("Dříve zaznamenáno: Příjem žádostí skončil");
  await expect(transition).toContainText("nově zaznamenáno: Otevřeno v zachycené verzi");
  await expect(transition).toContainText("nikoli potvrzení současného stavu");
  await expect(unverified).toContainText("Závažnost: Kritická");
  await expect(unverified).not.toContainText("CRITICAL");
  await expect(changes.getByText(/Závažnost je klasifikace zaznamenané změny/)).toContainText("nikoli potvrzení aktuálních podmínek nebo vaší způsobilosti");
  await expect(unverified).not.toContainText("OTHER");
  await expect(unverified).toContainText("Dotčený údaj: Jiný údaj (přesné pole zde není ověřeno)");
  await expect(unverified).not.toContainText("/e2e/unverified-date");
  await expect(transition).toContainText("Dotčený údaj: Stav výzvy");
  await expect(transition).not.toContainText("Interní označení pole");
  expect(await unverified.evaluate((element) => getComputedStyle(element).display)).toBe("block");
  expect(await unverified.locator("span").last().evaluate((element) => getComputedStyle(element).flexBasis)).toBe("auto");
  await expect(unverified).toContainText("2026-02-30T12:00:00Z");
  await expect(unverified.getByRole("note")).toContainText("Pořadí změn ani datum události nejsou ověřené");
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
  expect(detail.changes.map((change) => change.fieldPath)).toEqual(
    Array.from({ length: 20 }, (_, index) => `/e2e/history/change/${String(21 - index).padStart(2, "0")}`),
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
  await expect(changes.locator("li").first()).toContainText("Dotčený údaj: Jiný údaj (přesné pole zde není ověřeno)");
  await expect(changes.locator("li").last()).toContainText("Dotčený údaj: Jiný údaj (přesné pole zde není ověřeno)");
  await expect(changes).not.toContainText("/e2e/history/change/");
  const history = page.locator("details.detail-section").filter({ hasText: "Historie verzí" });
  await history.getByText("Historie verzí (20 zobrazených)").click();
  await expect(history.getByRole("status")).toContainText("Další verze mohou existovat");
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
    { id: 23, states: ["MISSING_CANDIDATE", "SEEN"], labels: ["Možná chybí u zdroje (předběžné)", "Viděn u zdroje"], caution: true },
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
    const heroAction = page.locator(".next-action");
    const stickyAction = page.locator(".sticky-action");
    for (const region of [heroAction, stickyAction]) {
      if (scenario.id === 20) {
        await expect(region.getByRole("link", { name: "Přidat k projektu" })).toHaveClass(/button--primary/);
      } else {
        const verify = region.getByRole("link", { name: "Ověřit výzvu v oficiálním zdroji ↗" });
        await expect(verify).toHaveClass(/button--primary/);
        await expect(verify).toHaveAttribute("href", `https://example.invalid/e2e/page/${scenario.id}${scenario.id === 23 ? "-b" : ""}`);
        await expect(region.getByRole("link", { name: "Přidat k projektu" })).toHaveClass(/button--secondary/);
        await expect(region.locator(".button--primary")).toHaveCount(1);
      }
    }
    if (scenario.id === 24) {
      await expect(sourcePanel.getByText("Výskyt u zdroje není známý: k výzvě nemáme zdrojový záznam.")).toBeVisible();
      await expect(heroAction).toContainText("Výskyt u zdroje není doložen");
      await expect(stickyAction).not.toContainText("způsobilost potvrzena");
    }
    if (scenario.id === 23) {
      await expect(sourcePanel.getByRole("link", { name: "E2E oficiální zdroj A ↗" })).toBeVisible();
      await expect(sourcePanel.getByRole("link", { name: "E2E oficiální zdroj B ↗" })).toBeVisible();
      await expect(page.locator(".source-presence-caution")).toContainText("stav „viděn“ i předběžné nebo potvrzené chybění");
      await expect(page.locator(".source-presence-caution")).toContainText("chybění jiného záznamu samo o sobě neznamená zrušení výzvy");
      await expect(page.locator(".source-presence-caution")).not.toContainText("V žádném zobrazeném zdrojovém záznamu není stav „viděn“");
    }
    if (scenario.caution) {
      await expect(page.locator(".source-presence-caution")).toContainText(scenario.id === 24
        ? "chybějící záznam sám o sobě neznamená zrušení"
        : scenario.id === 23
          ? "chybění jiného záznamu samo o sobě neznamená zrušení výzvy"
          : "Chybění u zdroje samo o sobě neznamená zrušení výzvy.");
      const accessibility = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(accessibility.violations).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    }
  }
});

test("mixed source caution remains accurate on desktop with real D1/API", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Apage%3A23");
  expect(response.status()).toBe(200);
  const detail = await response.json() as {
    status: string; officialDetailUrl: string;
    sources: Array<{ presenceState: string; canonicalUrl: string }>;
  };
  expect(detail.status).toBe("OPEN");
  expect(detail.officialDetailUrl).toBe("https://example.invalid/e2e/page/23");
  expect(detail.sources.map((source) => source.presenceState).sort()).toEqual(["MISSING_CANDIDATE", "SEEN"]);
  expect(detail.sources.find((source) => source.presenceState === "SEEN")?.canonicalUrl)
    .toBe("https://example.invalid/e2e/page/23-b");

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/dotace/grant%3Ae2e%3Apage%3A23");
  await expect(page.getByRole("heading", { name: "E2E stránkování 23" })).toBeVisible();
  await expect(page.locator(".detail-hero").getByText("Otevřeno v zachycené verzi")).toBeVisible();
  await expect(page.locator(".source-presence-caution")).toContainText("stav „viděn“ i předběžné nebo potvrzené chybění");
  await expect(page.locator(".source-presence-caution")).not.toContainText("V žádném zobrazeném zdrojovém záznamu není stav „viděn“");
  for (const region of [page.locator(".next-action"), page.locator(".sticky-action")]) {
    const verify = region.getByRole("link", { name: "Ověřit výzvu v oficiálním zdroji ↗" });
    await expect(verify).toHaveClass(/button--primary/);
    await expect(verify).toHaveAttribute("href", "https://example.invalid/e2e/page/23-b");
    await expect(region.getByRole("link", { name: "Přidat k projektu" })).toHaveClass(/button--secondary/);
  }
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1280);

  await page.route("**/api/grants/**", async (route) => {
    await route.fulfill({ json: {
      ...detail,
      sources: detail.sources.map((source) => source.presenceState === "SEEN"
        ? { ...source, canonicalUrl: "javascript:alert(1)" }
        : source),
    } });
  });
  await page.reload();
  for (const region of [page.locator(".next-action"), page.locator(".sticky-action")]) {
    await expect(region.getByRole("note")).toContainText("Ověřte aktuální stav přímo u poskytovatele");
    await expect(region.getByRole("link", { name: "Přidat k projektu" })).toHaveClass(/button--secondary/);
    await expect(region.getByRole("link", { name: "Ověřit výzvu v oficiálním zdroji ↗" })).toHaveCount(0);
    await expect(region.locator(".button--primary")).toHaveCount(0);
  }
});

test("missing source offers offline verification when no call URL is safe", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Apage%3A21");
  expect(response.status()).toBe(200);
  const detail = await response.json();
  expect(detail.status).toBe("OPEN");
  await page.setViewportSize({ width: 390, height: 844 });
  for (const providerUrl of ["https://example.invalid/provider", null]) {
    await page.route("**/api/grants/**", async (route) => {
      await route.fulfill({ json: {
        ...detail,
        officialDetailUrl: null,
        sources: detail.sources.map((source: object) => ({ ...source, canonicalUrl: "javascript:alert(1)" })),
        provider: { ...detail.provider, officialUrl: providerUrl },
      } });
    });
    await page.goto("/dotace/grant%3Ae2e%3Apage%3A21");
    await expect(page.getByRole("heading", { name: "E2E stránkování 21" })).toBeVisible();
    for (const region of [page.locator(".next-action"), page.locator(".sticky-action")]) {
      await expect(region.getByRole("note")).toContainText("Ověřte aktuální stav přímo u poskytovatele");
      await expect(region.getByRole("link", { name: "Přidat k projektu" })).toHaveClass(/button--secondary/);
      await expect(region.locator("a[href*='example.invalid/provider'], a[href^='javascript:']")).toHaveCount(0);
      await expect(region.locator(".button--primary")).toHaveCount(0);
    }
    await page.unroute("**/api/grants/**");
  }
});

test("malformed source observation is cautioned through real Detail API and mobile browser", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const response = await request.get("/api/grants/grant%3Ae2e%3Apage%3A20");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { sources: Array<{ lastSeenAt: string }> };
  expect(detail.sources.map((source) => source.lastSeenAt)).toEqual(["2026-02-30T12:00:00Z"]);
  await page.goto("/dotace/grant%3Ae2e%3Apage%3A20");
  await expect(page.getByRole("heading", { level: 1, name: "E2E stránkování 20" })).toBeVisible();
  const observed = page.locator(".detail-section .facts").first().locator("div")
    .filter({ has: page.locator("dt", { hasText: "Poslední pozorování záznamu u zdroje" }) }).first();
  await expect(observed).toContainText("Není doložena");
  await expect(observed.getByRole("note")).toContainText("zobrazené datum nemusí být nejnovější");
  const source = page.getByRole("complementary", { name: "Oficiální zdroje" });
  await expect(source.getByRole("note")).toContainText("Formát data pozorování není ověřen");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("source observation uses the latest instant across offsets in detail and workspace", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const response = await request.get("/api/grants/grant%3Ae2e%3Apage%3A23");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { status: string; sources: Array<{ lastSeenAt: string }> };
  expect(detail.status).toBe("OPEN");
  expect(detail.sources.map((source) => source.lastSeenAt)).toEqual([
    "2026-10-01T23:30:00-10:00",
    "2026-10-02T00:30:00+14:00",
  ]);
  await page.goto("/dotace/grant%3Ae2e%3Apage%3A23");
  await expect(page.getByRole("heading", { level: 1, name: "E2E stránkování 23" })).toBeVisible();
  const observed = page.locator(".detail-section .facts").first().locator("div")
    .filter({ has: page.locator("dt", { hasText: "Poslední pozorování záznamu u zdroje" }) }).first();
  await expect(observed).toContainText("1. října 2026");
  await expect(page.locator(".source-presence-caution"))
    .toContainText("Výskyt jednoho záznamu nepotvrzuje aktuální dostupnost výzvy");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  await page.locator(".next-action").getByRole("link", { name: "Přidat k projektu" }).click();
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
  expect((await workspace.json()).versionReview.sourceCheckedAt).toBe("2026-10-01T23:30:00-10:00");
});

test("detail preserves source calendar dates for a viewer in another timezone", async ({ browser, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Apage%3A23");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { sources: Array<{ lastSeenAt: string }> };
  expect(detail.sources.map((source) => source.lastSeenAt)).toEqual([
    "2026-10-01T23:30:00-10:00", "2026-10-02T00:30:00+14:00",
  ]);

  const context = await browser.newContext({ timezoneId: "Pacific/Honolulu", viewport: { width: 390, height: 844 } });
  try {
    const page = await context.newPage();
    await page.goto("/dotace/grant%3Ae2e%3Apage%3A23");
    await expect(page.getByRole("heading", { level: 1, name: "E2E stránkování 23" })).toBeVisible();
    const sources = page.getByRole("complementary", { name: "Oficiální zdroje" });
    await expect(sources.locator("li").filter({ has: page.getByRole("link", { name: "E2E oficiální zdroj B ↗" }) }))
      .toContainText("Pozorováno 2. října 2026");
    await expect(sources.locator("li").filter({ has: page.getByRole("link", { name: "E2E oficiální zdroj A ↗" }) }))
      .toContainText("Pozorováno 1. října 2026");
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  } finally {
    await context.close();
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
  await expect(selector.locator("option")).toHaveText([
    "Všechny typy", "Dotace / příspěvek", "Úvěr", "Záruka",
    "Kapitálový nástroj", "Kombinovaný nástroj", "Jiný nástroj podpory",
  ]);
  await selector.selectOption("LOAN");
  await expect(page).toHaveURL(/instrument=LOAN/);
  await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByText(/Hledáme v indexovaných výzvách veřejné podpory/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Zrušit filtr Typ financování: Úvěr" })).toBeVisible();
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
  await page.getByRole("button", { name: "Zrušit filtr Typ financování: Úvěr" }).click();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
});

test("unavailable facets show no counts, allow manual filters, and preserve first-page facets on load-more", async ({ page }) => {
  const result = (id: string) => ({ grantCallVersionId: id, grantCallId: id,
    title: `Facet test ${id}`, summary: "", status: "OPEN", submissionCloseAt: null,
    providerName: "Manual provider", officialDetailUrl: null,
    capturedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED", matchKind: "DIRECT" });
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
  await expect(page.getByLabel("Termín podání").locator('option[value="UNKNOWN"]')).toHaveText("Termín neuveden");
  await expect(page.locator("#search-providers option")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Zrušit filtr Poskytovatel: Manual provider" })).toBeVisible();
});

test("relevance phase inversion in real D1 response fails closed and mobile retry restores order", async ({ page, request }) => {
  const actual = await request.get("/api/search?intent=digitalizace%20obce");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { results: Array<{ matchKind: string }>; expandedTerms: string[] };
  expect(valid.results.length).toBeGreaterThanOrEqual(2);
  expect(valid.expandedTerms.length).toBeGreaterThan(0);
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    expect(response.ok()).toBe(true);
    await route.fulfill({ response, json: { ...body, results: body.results.map((item, index) =>
      index === 0 ? { ...item, matchKind: "ONTOLOGY" } : index === 1
        ? { ...item, matchKind: "DIRECT" } : item) } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce");
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("filtered real D1 response with off-filter card fails closed and retries on mobile", async ({ page, request }) => {
  const actual = await request.get("/api/search?intent=digitalizace%20obce&status=OPEN");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { results: Array<{ status: string }> };
  expect(valid.results.length).toBeGreaterThan(0);
  expect(valid.results.every((result) => result.status === "OPEN")).toBe(true);
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    expect(response.ok()).toBe(true);
    // A null facet is allowed when counts are unavailable; it cannot prove the
    // off-filter result wrong. The applied status must be checked on the card.
    await route.fulfill({ response, json: { ...body, facets: null, results: [
      { ...body.results[0], status: "PLANNED" }, ...body.results.slice(1),
    ] } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce&status=OPEN");
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByLabel("Stav výzvy")).toHaveValue("OPEN");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("contradictory real D1 facet count fails closed then retries unmodified API on mobile", async ({ page, request }) => {
  const actual = await request.get("/api/search?intent=digitalizace%20obce");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { results: Array<{ status: string }>; facets: {
    status: { OPEN: number }; deadline: { KNOWN: number; UNKNOWN: number } } | null };
  expect(valid.results.some((result) => result.status === "OPEN")).toBe(true);
  expect(valid.facets?.status.OPEN).toBeGreaterThan(0);
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    expect(response.ok()).toBe(true);
    expect(body.facets).not.toBeNull();
    await route.fulfill({ response, json: { ...body,
      facets: { ...body.facets!, status: { ...body.facets!.status, OPEN: 0 } } } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce");
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("empty-index claim without zero-count facets fails closed on real D1/API and mobile retry restores results", async ({ page, request }) => {
  const actual = await request.get("/api/search?intent=digitalizace%20obce");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { results: unknown[]; facets: unknown };
  expect(valid.results.length).toBeGreaterThan(0);
  expect(valid.facets).not.toBeNull();
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    expect(response.ok()).toBe(true);
    await route.fulfill({ response, json: { ...body, indexState: "EMPTY", results: [],
      nextCursor: null, facets: null } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce");
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.getByText("Lokální index je prázdný")).toHaveCount(0);
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("empty-index claim with positive real D1 facets fails closed and retry restores results", async ({ page, request }) => {
  const actual = await request.get("/api/search?intent=digitalizace%20obce");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { results: unknown[]; facets: {
    status: { OPEN: number } } | null };
  expect(valid.results.length).toBeGreaterThan(0);
  expect(valid.facets?.status.OPEN).toBeGreaterThan(0);
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    expect(response.ok()).toBe(true);
    await route.fulfill({ response, json: { ...body, indexState: "EMPTY", results: [], nextCursor: null } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce");
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.getByText("Lokální index je prázdný")).toHaveCount(0);
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("duplicate provider facet from real D1/API fails closed and mobile retry restores real results", async ({ page, request }) => {
  const actual = await request.get("/api/search?intent=digitalizace%20obce");
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { facets: {
    providers: Array<{ name: string; count: number }> } | null };
  expect(valid.facets?.providers.length).toBeGreaterThan(0);
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    const body = await response.json() as typeof valid;
    expect(response.ok()).toBe(true);
    expect(body.facets?.providers.length).toBeGreaterThan(0);
    await route.fulfill({ response, json: { ...body, facets: { ...body.facets!,
      providers: [...body.facets!.providers, body.facets!.providers[0]] } } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce");
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("mobile detail return replays fresh D1 cursor and focuses its original result", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  const link = page.locator(".grant-card").last().getByRole("link", { name: /Zobrazit detail/ });
  const targetId = await link.getAttribute("data-result-id");
  await link.click();
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
  await page.getByRole("link", { name: "Zpět na výsledky" }).first().click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  await expect(page.locator("a[data-result-id]").last()).toHaveAttribute("data-result-id", targetId!);
  await expect(page.locator("a[data-result-id]").last()).toBeFocused();
  await expect(page.getByText("Výsledek z detailu je znovu načtený", { exact: false })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("mobile detail return restores a third fresh D1 cursor page", async ({ page, request }) => {
  const first = await request.get("/api/search?intent=zzq45x");
  expect(first.status()).toBe(200);
  const firstBody = await first.json() as { results: unknown[]; nextCursor: string | null };
  expect(firstBody.results).toHaveLength(20);
  const second = await request.get(`/api/search?intent=zzq45x&cursor=${encodeURIComponent(firstBody.nextCursor!)}`);
  expect(second.status()).toBe(200);
  const secondBody = await second.json() as { results: unknown[]; nextCursor: string | null };
  expect(secondBody.results).toHaveLength(20);
  const third = await request.get(`/api/search?intent=zzq45x&cursor=${encodeURIComponent(secondBody.nextCursor!)}`);
  expect(third.status()).toBe(200);
  const thirdBody = await third.json() as { results: unknown[]; nextCursor: string | null };
  expect(thirdBody.results).toHaveLength(5);
  expect(thirdBody.nextCursor).toBeNull();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=zzq45x");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(40);
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(45);
  const link = page.locator(".grant-card").last().getByRole("link", { name: /Zobrazit detail/ });
  const targetId = await link.getAttribute("data-result-id");
  await link.click();
  await expect(page.locator(".detail-hero h1")).toBeVisible();
  await page.getByRole("link", { name: "Zpět na výsledky" }).first().click();
  await expect(page.locator(`a[data-result-id='${targetId}']`)).toBeFocused();
  await expect(page.locator(".grant-card")).toHaveCount(45);
  await expect(page).toHaveURL(/\/hledat\?intent=zzq45x$/);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("detail return absent from fresh D1 pages does not claim cancellation", async ({ page }) => {
  await page.goto("/hledat?intent=zzq45x&returnResult=gcv-e2e-long-missing");
  await expect(page.locator(".grant-card")).toHaveCount(45);
  await expect(page.getByRole("status").filter({ hasText: "Původní výsledek se v načtených stránkách nepodařilo obnovit" })).toBeVisible();
  await expect(page).toHaveURL(/\/hledat\?intent=zzq45x$/);
  await expect(page.getByRole("button", { name: "Načíst další výsledky" })).toHaveCount(0);
  expect(await page.getByRole("status").filter({ hasText: "Původní výsledek" }).textContent()).not.toContain("zrušen");
});

test("refresh during detail return keeps the target until fresh cursor replay completes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let cursorRequests = 0;
  await page.route("**/api/search?*cursor=*", async (route) => {
    cursorRequests += 1;
    await new Promise((resolve) => setTimeout(resolve, 700));
    try { await route.continue(); } catch { /* navigation may abort the old request */ }
  });
  await page.goto("/hledat?intent=strankovani&returnResult=gcv-e2e-page-25");
  await expect(page.getByRole("button", { name: "Načítáme další výsledky…" })).toBeVisible();
  await expect(page).toHaveURL(/returnResult=gcv-e2e-page-25$/);
  await page.reload();
  await expect(page.locator("a[data-result-id='gcv-e2e-page-25']")).toBeFocused();
  await expect(page).toHaveURL(/\/hledat\?intent=strankovani$/);
  expect(cursorRequests).toBeGreaterThanOrEqual(2);
});

test("detail return cursor failure preserves first page without claiming cancellation", async ({ page }) => {
  await page.route("**/api/search?*cursor=*", (route) => route.fulfill({ status: 503,
    contentType: "application/json", body: JSON.stringify({ error: "SEARCH_UNAVAILABLE" }) }));
  await page.goto("/hledat?intent=strankovani&returnResult=gcv-e2e-page-25");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByText("Původní výsledek se v načtených stránkách nepodařilo obnovit", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Zkusit načíst další znovu" })).toBeVisible();
  await expect(page.getByText("Dosud načtené výsledky zůstávají zobrazené", { exact: false })).toBeVisible();
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

test("a terminal first page cannot hide real D1 matches counted by facets", async ({ page, request }) => {
  const intent = "strankovani";
  const actual = await request.get(`/api/search?intent=${intent}`);
  expect(actual.status()).toBe(200);
  const body = await actual.json() as { results: unknown[]; nextCursor: string | null;
    facets: { status: Record<string, number>; deadline: Record<string, number> } | null };
  expect(body.results).toHaveLength(20);
  expect(body.nextCursor).toBeTruthy();
  expect(body.facets).not.toBeNull();
  const total = Object.values(body.facets!.status).reduce((sum, count) => sum + count, 0);
  expect(total).toBe(25);
  expect(Object.values(body.facets!.deadline).reduce((sum, count) => sum + count, 0)).toBe(total);

  await page.setViewportSize({ width: 390, height: 844 });
  const corruptPage = async (route: import("@playwright/test").Route) => {
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    const real = await response.json() as typeof body;
    await route.fulfill({ response, json: { ...real, nextCursor: null } });
  };
  await page.route("**/api/search?*", corruptPage);
  await page.goto(`/hledat?intent=${intent}`);
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  await page.unroute("**/api/search?*", corruptPage);
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(total);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
});

test("mobile status filter rejects a terminal page hiding matches and retries real D1/API", async ({ page, request }) => {
  const url = "/api/search?intent=strankovani&status=PLANNED";
  const actual = await request.get(url);
  expect(actual.status()).toBe(200);
  const body = await actual.json() as { results: unknown[]; nextCursor: string | null;
    facets: { deadline: { KNOWN: number; UNKNOWN: number };
      providers: Array<{ name: string; count: number }> } | null };
  expect(body.results).toHaveLength(1);
  expect(body.nextCursor).toBeNull();
  expect(body.facets?.deadline.KNOWN).toBe(1);
  expect(body.facets?.providers).toHaveLength(1);

  await page.setViewportSize({ width: 390, height: 844 });
  const corruptPage = async (route: import("@playwright/test").Route) => {
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    const real = await response.json() as typeof body;
    await route.fulfill({ response, json: { ...real, facets: { ...real.facets!,
      deadline: { ...real.facets!.deadline, KNOWN: 2 },
      providers: real.facets!.providers.map((item) => ({ ...item, count: 2 })),
    } } });
  };
  await page.route("**/api/search?*", corruptPage);
  await page.goto("/hledat?intent=strankovani&status=PLANNED");
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  await page.unroute("**/api/search?*", corruptPage);
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
});

test("oversized continuation from real D1/API keeps old cards and retries the original cursor", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  let corruptOnce = true;
  await page.route("**/api/search?*cursor=*", async (route) => {
    if (!corruptOnce) {
      await route.continue();
      return;
    }
    corruptOnce = false;
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.results).toHaveLength(5);
    const extra = Array.from({ length: 16 }, (_, i) => ({ ...body.results[0],
      grantCallVersionId: `oversized-version-${i}`, grantCallId: `oversized-call-${i}` }));
    await route.fulfill({ response, json: { ...body, results: [...body.results, ...extra] } });
  });
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("alert")).toContainText("Dosud načtené výsledky zůstávají zobrazené");
  await page.getByRole("button", { name: "Zkusit načíst další znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  await expect(page.getByRole("button", { name: "Načíst další výsledky" })).toHaveCount(0);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("non-advancing cursor keeps real D1 results and retry recovers from real API", async ({ page }) => {
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  let corruptOnce = true;
  await page.route("**/api/search?*cursor=*", async (route) => {
    if (!corruptOnce) {
      await route.continue();
      return;
    }
    corruptOnce = false;
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ response, json: { ...body,
      nextCursor: new URL(route.request().url()).searchParams.get("cursor") } });
  });
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("alert")).toContainText("Dosud načtené výsledky zůstávají zobrazené");
  await page.getByRole("button", { name: "Zkusit načíst další znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  await expect(page.getByRole("button", { name: "Načíst další výsledky" })).toHaveCount(0);
});

test("empty READY first page with a cursor fails closed and retry uses real D1/API", async ({ page }) => {
  const corruptPage = async (route: import("@playwright/test").Route) => {
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.nextCursor).toBeTruthy();
    await route.fulfill({ response, json: { ...body, results: [] } });
  };
  await page.route("**/api/search?*", corruptPage);
  await page.goto("/hledat?intent=strankovani");
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  await expect(page.getByText("Žádné výsledky", { exact: false })).toHaveCount(0);
  await page.unroute("**/api/search?*", corruptPage);
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("button", { name: "Načíst další výsledky" })).toBeVisible();
});

test("empty READY continuation with cursor retains real D1 cards and retry recovers", async ({ page }) => {
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  let corruptOnce = true;
  await page.route("**/api/search?*cursor=*", async (route) => {
    if (!corruptOnce) {
      await route.continue();
      return;
    }
    corruptOnce = false;
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    await route.fulfill({ response, json: { ...body, results: [], nextCursor: "another-page" } });
  });
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("alert")).toContainText("Dosud načtené výsledky zůstávají zobrazené");
  await page.getByRole("button", { name: "Zkusit načíst další znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
});

test("empty index on continuation retains real D1 cards and retry recovers from real API", async ({ page }) => {
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  let corruptOnce = true;
  await page.route("**/api/search?*cursor=*", async (route) => {
    if (!corruptOnce) {
      await route.continue();
      return;
    }
    corruptOnce = false;
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    await route.fulfill({ response, json: { ...body, indexState: "EMPTY", results: [], nextCursor: null } });
  });
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("alert")).toContainText("Dosud načtené výsledky zůstávají zobrazené");
  await expect(page.getByRole("button", { name: "Zkusit načíst další znovu" })).toBeVisible();
  await page.getByRole("button", { name: "Zkusit načíst další znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
});

test("duplicate continuation identity retains real D1 cards and retry recovers from real API on mobile", async ({ page, request }) => {
  const first = await request.get("/api/search?intent=strankovani");
  expect(first.status()).toBe(200);
  const { results } = await first.json() as { results: Array<{ grantCallVersionId: string }> };
  expect(results).toHaveLength(20);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  let corruptOnce = true;
  await page.route("**/api/search?*cursor=*", async (route) => {
    if (!corruptOnce) {
      await route.continue();
      return;
    }
    corruptOnce = false;
    const response = await route.fetch();
    const body = await response.json() as { results: Array<{ grantCallVersionId: string }> };
    expect(body.results.length).toBeGreaterThan(0);
    await route.fulfill({ response, json: { ...body, results: [
      { ...body.results[0], grantCallVersionId: results[0].grantCallVersionId },
      ...body.results.slice(1),
    ] } });
  });
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("alert")).toContainText("Dosud načtené výsledky zůstávají zobrazené");
  await expect(page.getByRole("button", { name: "Zkusit načíst další znovu" })).toBeFocused();
  await page.getByRole("button", { name: "Zkusit načíst další znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  expect(new Set(await page.locator(".grant-card h3").allTextContents()).size).toBe(25);
});

test("different version of an already loaded call fails closed on mobile then real D1 retry recovers", async ({ page, request }) => {
  const first = await request.get("/api/search?intent=strankovani");
  expect(first.status()).toBe(200);
  const { results } = await first.json() as { results: Array<{ grantCallId: string; grantCallVersionId: string }> };
  expect(results).toHaveLength(20);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  let corruptOnce = true;
  await page.route("**/api/search?*cursor=*", async (route) => {
    if (!corruptOnce) return route.continue();
    corruptOnce = false;
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    const body = await response.json() as { results: Array<{ grantCallId: string; grantCallVersionId: string }> };
    expect(body.results.length).toBeGreaterThan(0);
    expect(body.results[0].grantCallVersionId).not.toBe(results[0].grantCallVersionId);
    await route.fulfill({ response, json: { ...body, results: [
      { ...body.results[0], grantCallId: results[0].grantCallId }, ...body.results.slice(1),
    ] } });
  });
  await page.getByRole("button", { name: "Načíst další výsledky" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("alert")).toContainText("Dosud načtené výsledky zůstávají zobrazené");
  await page.getByRole("button", { name: "Zkusit načíst další znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(25);
  expect(new Set(await page.locator(".grant-card").evaluateAll((cards) => cards.map((card) =>
    card.querySelector("a[aria-label^='Zobrazit detail']")?.getAttribute("href")))).size).toBe(25);
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

test("unchanged status and deadline filters preserve loaded results without a redundant search", async ({ page, request }) => {
  const initial = await request.get("/api/search?intent=digitalizace%20obce&status=OPEN&deadline=KNOWN");
  expect(initial.status()).toBe(200);
  expect((await initial.json() as { results: unknown[] }).results.length).toBeGreaterThan(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce&status=OPEN&deadline=KNOWN");
  await expect(page.locator(".grant-card").first()).toBeVisible();
  const count = await page.locator(".grant-card").count();
  const filters = page.locator(".filter-panel");
  await filters.locator("summary").click();
  let searches = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/search?")) searches += 1;
  });
  await page.getByLabel("Stav výzvy").focus();
  await page.getByLabel("Stav výzvy").selectOption("OPEN");
  await expect(page.getByLabel("Stav výzvy")).toBeFocused();
  await page.getByLabel("Termín podání").focus();
  await page.getByLabel("Termín podání").selectOption("KNOWN");
  await expect(page.getByLabel("Termín podání")).toBeFocused();
  await expect(page.locator(".grant-card")).toHaveCount(count);
  await expect(filters).toHaveAttribute("open", "");
  expect(searches).toBe(0);
});

test("global status finds a later-page planned result and rejects a changed cursor", async ({ page, request }) => {
  await page.goto("/hledat?intent=strankovani");
  await expect(page.locator(".grant-card")).toHaveCount(20);
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toHaveCount(0);
  await page.getByLabel("Stav výzvy").selectOption("PLANNED");
  await expect(page.getByRole("heading", { name: "E2E pozdější plánovaná výzva" })).toBeVisible();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  const filterExplanation = page.getByRole("region", { name: "Nalezené možnosti" }).locator("details.detail-section");
  await filterExplanation.locator("summary").click();
  await expect(filterExplanation.getByText(/Stav, dostupnost termínu, uzávěrka nejdříve, uzávěrka nejpozději, přesný název poskytovatele a typ financování se filtrují napříč/)).toBeVisible();
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
  await page.getByRole("button", { name: "Zavřít filtry" }).click();
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
  await page.getByRole("button", { name: "Zavřít filtry" }).click();
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

test("real D1 search keeps malformed source deadlines visible but warns on each card", async ({ page, request }) => {
  const actual = await request.get("/api/search?intent=date-boundary");
  expect(actual.status()).toBe(200);
  const body = await actual.json() as { results: Array<{ submissionCloseAt: string | null }> };
  expect(body.results.map((result) => result.submissionCloseAt)).toEqual(expect.arrayContaining([
    "2027-05-01", "2027-02-30", "not-a-date", null,
  ]));
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/hledat?intent=date-boundary");
    await expect(page.locator(".grant-card")).toHaveCount(4);
    for (const kind of ["invalid", "malformed"]) {
      const card = page.locator(".grant-card").filter({ has: page.getByRole("heading", { name: `E2E date ${kind}` }) });
      await expect(card.getByRole("note").filter({ hasText: "formát nelze automaticky ověřit" })).toContainText("nejde o potvrzené datum");
    }
    for (const kind of ["only", "null"]) {
      const card = page.locator(".grant-card").filter({ has: page.getByRole("heading", { name: `E2E date ${kind}` }) });
      await expect(card.getByRole("note").filter({ hasText: "formát nelze automaticky ověřit" })).toHaveCount(0);
    }
    await expect(page.locator(".grant-card").filter({ hasText: "2027-02-30" })).toHaveCount(1);
    await expect(page.locator(".grant-card").filter({ hasText: "not-a-date" })).toHaveCount(1);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
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

test("bounded real D1 search rejects an off-window response and mobile retry restores source date", async ({ page, request }) => {
  const url = "/api/search?intent=date-boundary&closesFrom=2027-05-01&closesBy=2027-05-01";
  const actual = await request.get(url);
  expect(actual.status()).toBe(200);
  const valid = await actual.json() as { results: Array<{ submissionCloseAt: string | null }> };
  expect(valid.results).toHaveLength(1);
  expect(valid.results[0].submissionCloseAt).toBe("2027-05-01");
  let corrupt = true;
  await page.route("**/api/search?*", async (route) => {
    if (!corrupt) return route.continue();
    const response = await route.fetch();
    expect(response.ok()).toBe(true);
    const body = await response.json() as typeof valid;
    await route.fulfill({ response, json: { ...body, facets: null,
      results: [{ ...body.results[0], submissionCloseAt: "2027-06-01" }] } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/hledat?intent=date-boundary&closesFrom=2027-05-01&closesBy=2027-05-01`);
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  corrupt = false;
  await page.getByRole("button", { name: "Zkusit vyhledávání znovu" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await expect(page.locator(".grant-card")).toContainText("2027-05-01");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("SQLite end-of-day source timestamp remains visible in bounded real D1/API search", async ({ page, request }) => {
  const url = "/api/search?intent=endofday-boundary&closesFrom=2027-05-01&closesBy=2027-05-01";
  const response = await request.get(url);
  expect(response.status()).toBe(200);
  const body = await response.json() as { results: Array<{ submissionCloseAt: string }> };
  expect(body.results).toEqual([expect.objectContaining({ submissionCloseAt: "2027-05-01T24:00:00Z" })]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=endofday-boundary&closesFrom=2027-05-01&closesBy=2027-05-01");
  await expect(page.getByRole("heading", { name: "E2E end-of-day výzva" })).toBeVisible();
  await expect(page.locator(".grant-card")).toContainText("2027-05-01 24:00:00 UTC");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("lowercase UTC suffix from real D1/API remains visible inside a bounded search", async ({ page, request }) => {
  const url = "/api/search?intent=lowerz-boundary&closesFrom=2027-05-01&closesBy=2027-05-01";
  const response = await request.get(url);
  expect(response.status()).toBe(200);
  const body = await response.json() as { results: Array<{ submissionCloseAt: string }> };
  expect(body.results).toEqual([expect.objectContaining({ submissionCloseAt: "2027-05-01T12:00:00z" })]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=lowerz-boundary&closesFrom=2027-05-01&closesBy=2027-05-01");
  await expect(page.getByRole("heading", { name: "E2E lowercase UTC výzva" })).toBeVisible();
  await expect(page.locator(".grant-card")).toContainText("2027-05-01 12:00:00z");
  await expect(page.locator(".grant-card").getByRole("note").filter({ hasText: "formát nelze automaticky ověřit" })).toHaveCount(0);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
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
  await page.getByRole("button", { name: "Zavřít filtry" }).click();
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

test("both date sorts keep real D1 cursor pages usable in Chromium", async ({ page, request }) => {
  for (const sort of ["DEADLINE", "DEADLINE_LATEST"] as const) {
    const firstResponse = await request.get(`/api/search?intent=strankovani&sort=${sort}`);
    expect(firstResponse.status()).toBe(200);
    const first = await firstResponse.json() as { results: Array<{ grantCallVersionId: string; submissionCloseAt: string | null }>; nextCursor: string | null };
    expect(first.results).toHaveLength(20);
    expect(first.results[0]).toMatchObject({ grantCallVersionId: "gcv-e2e-page-25",
      submissionCloseAt: "2027-05-01T00:00:00Z" });
    expect(first.nextCursor).toBeTruthy();
    const nextResponse = await request.get(`/api/search?intent=strankovani&sort=${sort}&cursor=${encodeURIComponent(first.nextCursor!)}`);
    expect(nextResponse.status()).toBe(200);
    const next = await nextResponse.json() as { results: Array<{ submissionCloseAt: string | null }>; nextCursor: string | null };
    expect(next.results).toHaveLength(5);
    expect(next.results.every((result) => result.submissionCloseAt === null)).toBe(true);
    expect(next.nextCursor).toBeNull();

    await page.goto(`/hledat?intent=strankovani&sort=${sort}`);
    await expect(page.locator(".grant-card")).toHaveCount(20);
    await expect(page.locator(".grant-card h3").first()).toHaveText("E2E pozdější plánovaná výzva");
    await page.getByRole("button", { name: "Načíst další výsledky" }).click();
    await expect(page.locator(".grant-card")).toHaveCount(25);
    await expect(page.getByRole("alert")).toHaveCount(0);
    expect(new Set(await page.locator(".grant-card h3").allTextContents()).size).toBe(25);
  }
});

test("real D1 dates order by UTC instant in both directions, with nulls last across cursors and browser cards", async ({ page, request }) => {
  const earlySource = "2027-05-01T23:00:00+04:00";
  const lateSource = "2027-05-01T20:30:00Z";
  expect(earlySource > lateSource).toBe(true); // Lexical sort would choose the wrong first row.
  expect(Date.parse(earlySource)).toBeLessThan(Date.parse(lateSource));
  const expected = [
    { sort: "DEADLINE", ids: ["gcv-e2e-chronology-1", "gcv-e2e-chronology-2", "gcv-e2e-chronology-3"],
      titles: ["E2E chronologie dříve", "E2E chronologie později", "E2E chronologie bez termínu"] },
    { sort: "DEADLINE_LATEST", ids: ["gcv-e2e-chronology-2", "gcv-e2e-chronology-1", "gcv-e2e-chronology-3"],
      titles: ["E2E chronologie později", "E2E chronologie dříve", "E2E chronologie bez termínu"] },
  ];
  for (const { sort, ids, titles } of expected) {
    let cursor: string | null = null;
    const seen: Array<{ grantCallVersionId: string; submissionCloseAt: string | null }> = [];
    do {
      const response = await request.get(`/api/search?intent=chronotestfixture&sort=${sort}&limit=1${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
      expect(response.status()).toBe(200);
      const body = await response.json() as { results: typeof seen; nextCursor: string | null };
      expect(body.results).toHaveLength(1);
      seen.push(...body.results);
      cursor = body.nextCursor;
      expect(seen.length).toBeLessThanOrEqual(3);
    } while (cursor);
    expect(seen.map((row) => row.grantCallVersionId)).toEqual(ids);
    expect(seen[2].submissionCloseAt).toBeNull();
    expect(seen.find((row) => row.grantCallVersionId === "gcv-e2e-chronology-1")?.submissionCloseAt).toBe(earlySource);
    expect(seen.find((row) => row.grantCallVersionId === "gcv-e2e-chronology-2")?.submissionCloseAt).toBe(lateSource);

    await page.goto(`/hledat?intent=chronotestfixture&sort=${sort}`);
    await expect(page.locator(".grant-card h3")).toHaveText(titles);
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
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

test("non-sport intent -> real API results -> filters -> detail -> provenance", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(response.status()).toBe(200);
  const body = await response.json() as { fundingScenarios: Array<{ id: string; vatRule: string | null }> };
  expect(body.fundingScenarios.find((scenario) => scenario.id === "e2e-funding-open")?.vatRule)
    .toBe("DPH je nezpůsobilá pouze při možnosti odpočtu");
  expect(body.fundingScenarios.find((scenario) => scenario.id === "e2e-funding-undocumented")?.vatRule)
    .toBeNull();
  await page.goto("/");

  await page.getByLabel("Co chcete uskutečnit?").first().fill("digitalizace obce");
  await page.getByRole("button", { name: "Najít možnosti" }).first().click();

  await expect(page).toHaveURL(/\/hledat\?intent=digitalizace\+obce/);
  await expect(page.getByRole("heading", { name: "Nalezené možnosti" })).toBeVisible();
  await expect(page.locator(".section-heading").getByText("Načtené výsledky: 2.", { exact: false })).toBeVisible();

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
  await expect(page.locator(".section-heading").getByText("Načtené výsledky: 1.", { exact: false })).toBeVisible();

  await page.getByLabel("Přesný název poskytovatele").fill("E2E test provider A");
  await page.getByRole("button", { name: "Použít poskytovatele" }).click();
  await expect(page.locator(".grant-card")).toHaveCount(1);
  await expect(page.locator(".grant-card").getByRole("link", { name: /Oficiální zdroj/ }))
    .toHaveAttribute("href", "https://example.invalid/e2e/open");
  await expect(page.locator(".grant-card").getByRole("note")
    .filter({ hasText: "Přímý odkaz na oficiální stránku" })).toHaveCount(0);
  await page.getByRole("link", { name: "Zobrazit detail" }).click();

  await expect(page).toHaveURL(/\/dotace\/grant%3Ae2e%3Aopen\?intent=digitalizace%20obce&status=OPEN&provider=E2E\+test\+provider\+A&returnResult=gcv-e2e-open$/);
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
  const deadlineResponse = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(deadlineResponse.status()).toBe(200);
  const deadlineDetail = await deadlineResponse.json() as {
    deadlines: Array<{ id: string; evidenceId: string | null }>;
    evidence: Array<{ id: string; verificationStatus: string }>;
  };
  const closingEvidenceId = deadlineDetail.deadlines.find((item) => item.id === "e2e-deadline-open")?.evidenceId;
  expect(deadlineDetail.evidence.find((item) => item.id === closingEvidenceId)?.verificationStatus).toBe("VERIFIED");
  await expect(deadlines).toContainText("Ukončení příjmu žádostí");
  await expect(deadlines).toContainText("2027-12-31 23:59:59 UTC");
  const overview = page.locator(".detail-section").filter({ has: page.getByRole("heading", { name: "Rychlý přehled" }) });
  await expect(overview.locator("div", { has: page.locator("dt", { hasText: "Ukončení příjmu" }) }).first())
    .toContainText("2027-12-31 23:59:59 UTC");
  await expect(overview.locator("div", { has: page.locator("dt", { hasText: "Zahájení příjmu" }) }).first())
    .toContainText("2026-09-20 08:00:00 UTC");
  await expect(deadlines.getByRole("link", { name: /Doklad termínu: E2E oficiální podmínky, str. 2/ }))
    .toHaveAttribute("href", "https://example.invalid/e2e/open-source");
  await expect(deadlines.locator("li").filter({ hasText: "Ukončení příjmu žádostí" }))
    .toContainText("Ověření doloženého údaje: Ověřeno");
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
  await expect(funded.getByText("Pravidlo DPH podle scénáře").locator("..").locator("dd"))
    .toHaveText("Údaj ze scénáře: DPH je nezpůsobilá pouze při možnosti odpočtu. Ověřte u poskytovatele, zda platí pro váš projekt.");
  await expect(funded).toContainText("Ne, podle scénáře");
  await expect(funded).toContainText("Individuální potřebu vlastních peněz a předfinancování");
  const undocumented = finance.locator(".grant-card").filter({ has: page.getByRole("heading", { name: "E2E scénář bez samostatného dokladu" }) });
  await expect(undocumented).toContainText("Není doložen");
  await expect(undocumented.getByText("Pravidlo DPH podle scénáře").locator("..").locator("dd"))
    .toHaveText("Není doloženo; nevyvozujte z toho nárok na odpočet ani výši DPH.");
  await expect(undocumented).toContainText("Není doloženo");
  await expect(undocumented).toContainText("Není uvedeno");
  await expect(undocumented.getByText("Samostatný doklad financování není připojen")).toBeVisible();
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
  await expect(page.locator(".sticky-action").getByRole("link", { name: "Přidat k projektu" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(finance.getByRole("link", { name: /Doklad financování/ })).toBeVisible();
  await expect(requirements.getByRole("link", { name: /Doklad požadavku/ })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("min-only support rate stays a lower bound in real API and mobile detail", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(response.status()).toBe(200);
  const { fundingScenarios } = await response.json() as { fundingScenarios: Array<{
    id: string; supportRateMinBps: number | null; supportRateMaxBps: number | null;
    grantAmountMinMinor: number | null; grantAmountMaxMinor: number | null;
  }> };
  expect(fundingScenarios.find((scenario) => scenario.id === "e2e-funding-min-only"))
    .toMatchObject({ supportRateMinBps: 2500, supportRateMaxBps: null,
      grantAmountMinMinor: 5000000, grantAmountMaxMinor: null });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  const scenario = page.getByRole("region", { name: "Finance" }).locator(".grant-card")
    .filter({ has: page.getByRole("heading", { name: "E2E pouze minimální míra" }) });
  await expect(scenario.locator(".facts div").filter({ has: page.locator("dt", { hasText: "Míra podpory" }) }).locator("dd"))
    .toHaveText("min. 25 %; horní mez není uvedena");
  await expect(scenario).toContainText("min. 25 %; horní mez není uvedena");
  await expect(scenario.locator(".facts div").filter({ has: page.locator("dt", { hasText: "Spodní mez dotace" }) }).locator("dd"))
    .toContainText("50 000");
  await expect(scenario.locator(".facts div").filter({ has: page.locator("dt", { hasText: "Maximální dotace" }) }).locator("dd"))
    .toHaveText("Horní mez není uvedena");
  await expect(scenario).toContainText("min. 50");
  await expect(scenario).not.toContainText("Částka nebo míra podpory není v normalizovaných datech uvedena");
  await expect(scenario).not.toContainText("max. 25 %");
  await expect(scenario).toContainText("Individuální potřebu vlastních peněz");
  const maxOnly = page.getByRole("region", { name: "Finance" }).locator(".grant-card")
    .filter({ has: page.getByRole("heading", { name: "E2E syntetický scénář" }) });
  await expect(maxOnly.locator(".facts div").filter({ has: page.locator("dt", { hasText: "Spodní mez dotace" }) }).locator("dd"))
    .toContainText("50 000");
  await expect(maxOnly.locator(".facts div").filter({ has: page.locator("dt", { hasText: "Maximální dotace" }) }).locator("dd"))
    .toContainText("100 000");
  await expect(maxOnly.locator(".facts div").filter({ has: page.locator("dt", { hasText: "Míra podpory" }) }).locator("dd"))
    .toHaveText("max. 60 %; dolní mez není uvedena");
  const unknown = page.getByRole("region", { name: "Finance" }).locator(".grant-card")
    .filter({ has: page.getByRole("heading", { name: "E2E scénář bez samostatného dokladu" }) });
  await expect(unknown.locator(".facts div").filter({ has: page.locator("dt", { hasText: "Míra podpory" }) }).locator("dd"))
    .toHaveText("Není uvedeno");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("date-only and offset deadlines preserve source precision without inventing a timezone in real API and mobile detail", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Adate%3Aonly");
  expect(response.status()).toBe(200);
  const dateOnly = await response.json() as { submissionCloseAt: string; deadlines: Array<{ endsAt: string; timezone: string | null }> };
  expect(dateOnly.submissionCloseAt).toBe("2027-05-01");
  expect(dateOnly.deadlines).toEqual([expect.objectContaining({ endsAt: "2027-05-01", timezone: null })]);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Adate%3Aonly");
  const overview = page.locator(".detail-section").filter({ has: page.getByRole("heading", { name: "Rychlý přehled" }) });
  await expect(overview.locator("dd").filter({ hasText: "2027-05-01" })).toBeVisible();
  await expect(overview).not.toContainText("2027-05-01 00:00");
  const deadlines = page.getByRole("region", { name: "Termíny podle zdroje" });
  await expect(deadlines).toContainText("2027-05-01");
  await expect(deadlines).not.toContainText("Zóna uvedená zdrojem");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  const offsetResponse = await request.get("/api/grants/grant%3Ae2e%3Adate%3Aoffset");
  expect(offsetResponse.status()).toBe(200);
  const offset = await offsetResponse.json() as { deadlines: Array<{ endsAt: string; timezone: string | null }> };
  expect(offset.deadlines).toEqual([expect.objectContaining({ endsAt: "2027-05-01T16:30:45+02:00", timezone: null })]);
  await page.goto("/dotace/grant%3Ae2e%3Adate%3Aoffset");
  const offsetDeadlines = page.getByRole("region", { name: "Termíny podle zdroje" });
  await expect(offsetDeadlines).toContainText("2027-05-01 16:30:45+02:00");
  await expect(offsetDeadlines).not.toContainText("Zóna uvedená zdrojem");
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

test("OPEN non-grant detail offers project verification, not a grant promise", async ({ page, request }) => {
  const response = await request.get("http://127.0.0.1:8787/grants/grant%3Ae2e%3Apage%3A24");
  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({ status: "OPEN", fundingInstrumentType: "LOAN" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Apage%3A24");
  const projectLink = page.locator(".sticky-action").getByRole("link", { name: "Přidat k projektu" });
  await expect(projectLink).toBeVisible();
  await expect(projectLink).toHaveClass(/button--secondary/);
  await expect(projectLink).toHaveAttribute("href", /grantCallId=grant%3Ae2e%3Apage%3A24/);
  for (const region of [page.locator(".next-action"), page.locator(".sticky-action")]) {
    await expect(region.getByRole("link", { name: "Ověřit výzvu v oficiálním zdroji ↗" }))
      .toHaveAttribute("href", "https://example.invalid/e2e/page/24");
    await expect(region.getByRole("link", { name: "Přidat k projektu" })).toHaveClass(/button--secondary/);
  }
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Způsobilost pro váš projekt" })).toContainText("Osobní způsobilost zde není posouzena");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("UNKNOWN applicant type -> one answer -> fresh D1 reevaluation stays non-definitive", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await page.locator(".next-action").getByRole("link", { name: "Přidat k projektu" }).click();
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
  await page.locator(".next-action").getByRole("link", { name: "Přidat k projektu" }).click();
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
  await page.locator(".next-action").getByRole("link", { name: "Přidat k projektu" }).click();
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

test("mobile detail rejects duplicate evidence identity and retries real D1/API", async ({ page, request }) => {
  const original = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(original.status()).toBe(200);
  const detail = await original.json() as { evidence: Array<{ id: string }> };
  expect(detail.evidence.length).toBeGreaterThan(0);
  let servedDuplicate = false;
  let retryWithOriginal = false;
  await page.route("**/api/grants/grant%3Ae2e%3Aopen", async (route) => {
    if (retryWithOriginal) return route.continue();
    servedDuplicate = true;
    await route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ ...detail, evidence: [...detail.evidence, { ...detail.evidence[0] }] }) });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dotace/grant%3Ae2e%3Aopen");
  await expect(page.getByRole("heading", { name: "Detail výzvy se teď nepodařilo bezpečně načíst." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toHaveCount(0);
  retryWithOriginal = true;
  await page.getByRole("button", { name: "Zkusit načíst detail znovu" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  expect(servedDuplicate).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("detail exposes document retrieval and field verification from real D1/API without implying a fresh source check", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { evidence: Array<{
    id: string; sourceUrl: string; retrievedAt: string; verificationStatus: string;
  }> };
  const evidence = detail.evidence.find((item) => item.id === "e2e-fe-title");
  expect(evidence).toMatchObject({
    sourceUrl: "https://example.invalid/e2e/open-source",
    retrievedAt: "2026-09-26T20:00:00Z", verificationStatus: "VERIFIED",
  });

  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/dotace/grant%3Ae2e%3Aopen");
    await expect(page.getByRole("heading", { level: 1, name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
    const provenance = page.locator(".evidence-card details");
    await provenance.locator("summary").click();
    await expect(provenance).toContainText("Datum stažení dokumentu není datum opětovného ověření podmínek výzvy.");
    const items = provenance.locator("li");
    await expect(items).toHaveCount(detail.evidence.length);
    for (const item of await items.all()) {
      await expect(item).toContainText("Dokument stažen: 26. září 2026");
      await expect(item).toContainText("Ověření doloženého údaje: Ověřeno");
      await expect(item.getByRole("link")).toHaveAttribute("href", evidence!.sourceUrl);
    }
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
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

test("detail retains application window alongside a normalized project deadline", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Aplanned");
  expect(response.status()).toBe(200);
  const detail = await response.json() as { deadlines: { type: string; evidenceId: string | null }[] };
  expect(detail.deadlines.map((deadline) => deadline.type)).toEqual(["PROJECT_FINISH", "APPLICATION_WINDOW"]);
  expect(detail.deadlines[1]?.evidenceId).toBeNull();
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/dotace/grant%3Ae2e%3Aplanned");
    const deadlines = page.getByRole("region", { name: "Termíny podle zdroje" });
    await expect(deadlines).toContainText("Dokončení projektu");
    await expect(deadlines).toContainText("Příjem žádostí (souhrn výzvy)");
    await expect(deadlines).toContainText("2027-10-31 23:59:59 UTC");
    await expect(deadlines).toContainText("Samostatný doklad termínu není připojen");
  }
});

test("detail retains version opening beside an evidenced normalized closing", async ({ page, request }) => {
  const response = await request.get("/api/grants/grant%3Ae2e%3Aopen");
  expect(response.status()).toBe(200);
  const detail = await response.json() as {
    deadlines: { id: string; type: string; startsAt: string | null; endsAt: string | null; evidenceId: string | null }[];
  };
  expect(detail.deadlines).toEqual([
    expect.objectContaining({ id: "e2e-deadline-open", type: "APPLICATION_CLOSE", endsAt: "2027-12-31T23:59:59Z" }),
    expect.objectContaining({ id: "gcv-e2e-open:submission-open", type: "APPLICATION_OPEN", startsAt: "2026-09-20T08:00:00Z", endsAt: null, evidenceId: null }),
  ]);
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/dotace/grant%3Ae2e%3Aopen");
    const deadlines = page.getByRole("region", { name: "Termíny podle zdroje" });
    await expect(deadlines).toContainText("Ukončení příjmu žádostí");
    await expect(deadlines).toContainText("Zahájení ze souhrnu zachycené verze");
    await expect(deadlines).toContainText("2026-09-20 08:00:00 UTC");
    const opening = deadlines.locator("li").filter({ hasText: "Zahájení příjmu žádostí" });
    const closing = deadlines.locator("li").filter({ hasText: "Ukončení příjmu žádostí" });
    await expect(opening.locator("dt")).toHaveText(["Od"]);
    await expect(opening.locator("dd")).toContainText(["2026-09-20 08:00:00 UTC"]);
    await expect(closing.locator("dt")).toHaveText(["Do"]);
    await expect(closing.locator("dd")).toContainText(["2027-12-31 23:59:59 UTC"]);
    await expect(deadlines).toContainText("Samostatný doklad termínu není připojen");
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
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
    await expect(providerLink).toHaveCount(1);
    for (const region of [page.locator(".next-action"), page.locator(".sticky-action")]) {
      await expect(region.getByRole("note")).toContainText("Ověřte aktuální stav přímo u poskytovatele");
      await expect(region.getByRole("link", { name: "Přidat k projektu" })).toHaveClass(/button--secondary/);
      await expect(region.getByRole("link", { name: /Web poskytovatele/ })).toHaveCount(0);
    }
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

  await page.locator(".next-action").getByRole("link", { name: "Přidat k projektu" }).click();
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
  await page.getByRole("button", { name: "Zavřít filtry" }).click();
  await page.getByRole("button", { name: "Zrušit filtr Termín: neuveden" }).click();
  await filterToggle.click();
  await page.getByLabel("Stav výzvy").selectOption("PLANNED");
  await expect(planned).toBeVisible();
  await expect(open).toHaveCount(0);
  await page.getByRole("button", { name: "Zavřít filtry" }).click();
  await page.getByRole("button", { name: "Zrušit všechny filtry" }).click();
  await expect(open).toBeVisible();
  await filterToggle.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Stav výzvy")).toBeVisible();
  await page.getByRole("button", { name: "Zavřít filtry" }).click();
  const filterExplanation = page.getByRole("region", { name: "Nalezené možnosti" }).locator("details.detail-section");
  await filterExplanation.locator("summary").click();
  await expect(filterExplanation.getByText(/Stav, dostupnost termínu, uzávěrka nejdříve, uzávěrka nejpozději, přesný název poskytovatele a typ financování se filtrují napříč/)).toBeVisible();
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
  const closeFilters = page.getByRole("button", { name: "Zavřít filtry" });
  releaseInstrument();
  await expect(instrument).toHaveValue("GRANT");
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(instrument).toBeFocused();
  await page.unroute("**/api/search?*");
  await instrument.focus();
  await page.keyboard.press("ArrowDown");
  await expect(instrument).toHaveValue("LOAN");
  await expect(instrument).toBeFocused();
  await expect(panel).toHaveAttribute("open");
  await closeFilters.click();
  const statusChip = page.getByRole("button", { name: "Zrušit filtr Stav: Otevřeno v zachycené verzi" });
  await statusChip.focus();
  await page.keyboard.press("Enter");
  await expect(statusChip).toHaveCount(0);
  await expect(panel.locator("summary")).toBeFocused();
  await expect(panel).not.toHaveAttribute("open");
  const reset = page.getByRole("button", { name: "Zrušit všechny filtry" });
  await reset.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".grant-card")).toHaveCount(2);
  await expect(panel.locator("summary")).toBeFocused();

  await page.route("**/api/search?*", (route) => route.abort("failed"));
  await panel.locator("summary").click();
  await instrument.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit.");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  const retry = page.getByRole("button", { name: "Zkusit vyhledávání znovu" });
  await expect(retry).toBeFocused();
  await page.unroute("**/api/search?*");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(panel).toHaveAttribute("open");
  await expect.poll(() => panel.evaluate((node) => node.contains(document.activeElement))).toBe(true);
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

test("failed filtered search offers a clean intent-only retry against real D1 on mobile", async ({ page, request }) => {
  const intent = "digitalizace obce";
  const unfiltered = await request.get(`/api/search?intent=${encodeURIComponent(intent)}`);
  expect(unfiltered.status()).toBe(200);
  expect((await unfiltered.json() as { results: unknown[] }).results.length).toBeGreaterThan(0);
  await page.route("**/api/search?*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.has("status") || url.searchParams.has("sort")) {
      await route.fulfill({ status: 503, contentType: "application/json",
        body: JSON.stringify({ error: "SEARCH_UNAVAILABLE" }) });
    } else {
      await route.continue();
    }
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/hledat?intent=${encodeURIComponent(intent)}&status=OPEN`);
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  const reset = page.getByRole("link", { name: "Zrušit filtry a zkusit hledání znovu" });
  await expect(reset).toBeVisible();
  await reset.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL((url) => url.pathname === "/hledat"
    && [...url.searchParams.entries()].length === 1 && url.searchParams.get("intent") === intent);
  await expect(page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Zrušit filtry a zkusit hledání znovu" })).toHaveCount(0);
  await page.goto(`/hledat?intent=${encodeURIComponent(intent)}&sort=DEADLINE`);
  await expect(page.getByRole("alert")).toContainText("Výsledky teď neumíme bezpečně zobrazit");
  await expect(page.locator(".grant-card")).toHaveCount(0);
  await page.getByRole("link", { name: "Zrušit filtry a zkusit hledání znovu" }).click();
  await expect(page).toHaveURL((url) => url.pathname === "/hledat"
    && [...url.searchParams.entries()].length === 1 && url.searchParams.get("intent") === intent);
  await expect(page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
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
      const label = "Archivní záznam výzvy (příjem není potvrzen)";
      await expect(page.locator(".detail-hero")).toContainText(label);
      await expect(page.locator(".detail-section").filter({ has: page.getByRole("heading", { name: "Rychlý přehled" }) }).locator("dd").filter({ hasText: label })).toBeVisible();
      await expect(page.locator(".detail-hero")).not.toContainText("Otevřeno v zachycené verzi");
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
  await expect(page.locator(".sticky-action").getByRole("link", { name: "Přidat k projektu" })).toBeVisible();
});
