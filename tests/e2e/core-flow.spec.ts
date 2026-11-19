import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";

test("non-sport intent -> real API results -> filters -> detail -> provenance", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Co chcete uskutečnit?").first().fill("digitalizace obce");
  await page.getByRole("button", { name: "Najít možnosti" }).first().click();

  await expect(page).toHaveURL(/\/hledat\?intent=digitalizace\+obce/);
  await expect(page.getByRole("heading", { name: "Nalezené možnosti" })).toBeVisible();
  await expect(page.getByText("2 výsledků.")).toBeVisible();

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
