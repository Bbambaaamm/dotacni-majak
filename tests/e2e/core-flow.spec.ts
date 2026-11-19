import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";

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
  expect(second.nextCursor).toBeNull();
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
  await expect(page.getByText("1 z 2 výsledků.")).toBeVisible();

  await page.getByLabel("Poskytovatel").selectOption("E2E test provider A");
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

  const evidence = page.getByText("Konkrétní evidence (2)");
  await expect(evidence).toBeVisible();
  await evidence.click();
  await expect(page.getByRole("link", { name: /E2E oficiální podmínky/ }).first()).toHaveAttribute(
    "href",
    "https://example.invalid/e2e/open-source",
  );
  await expect(page.getByRole("link", { name: "Chci tuto dotaci" })).toBeVisible();
});

test("mobile result filters, deadline order and chips use the real API without implying eligibility", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/hledat?intent=digitalizace%20obce");
  const planned = page.getByRole("heading", { name: "E2E plánovaná výzva — digitalizace obce" });
  const open = page.getByRole("heading", { name: "E2E otevřená výzva — digitalizace obce" });
  await expect(planned).toBeVisible();
  await expect(open).toBeVisible();
  expect(await page.locator(".results-list .grant-card h3").first().textContent()).toContain("E2E plánovaná výzva");
  await page.getByLabel("Řazení načtených výsledků").selectOption("DEADLINE_LATEST");
  expect(await page.locator(".results-list .grant-card h3").first().textContent()).toContain("E2E otevřená výzva");
  await page.getByLabel("Řazení načtených výsledků").selectOption("DEADLINE");
  expect(await page.locator(".results-list .grant-card h3").first().textContent()).toContain("E2E plánovaná výzva");
  await page.getByLabel("Termín podání").selectOption("UNKNOWN");
  await expect(page.getByText("Tomuto filtru neodpovídá žádný z načtených výsledků.")).toBeVisible();
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
  await expect(page.getByText(/Filtry a řazení se vztahují pouze na tuto sadu/)).toBeVisible();
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
