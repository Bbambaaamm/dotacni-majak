import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const storageKey = "dotacni-majak:applicant-profile:v1";

test("profile can be saved, restored, exported and explicitly deleted without registration", async ({ page }) => {
  const apiRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) apiRequests.push(request.url());
  });
  await page.goto("/profil");
  await page.getByLabel("Typ žadatele").selectOption("MUNICIPALITY");
  await page.getByLabel("Kód obce (volitelné)").fill("123456");
  await page.getByLabel("Počet obyvatel obce (volitelné)").fill("3200");
  await page.getByRole("button", { name: "Uložit místně" }).click();
  await expect(page.getByRole("status")).toContainText("uložen pouze v tomto prohlížeči");
  const stored = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? "null"), storageKey);
  expect(stored.applicantType).toBe("MUNICIPALITY");
  expect(stored.municipalityPopulation).toBe(3200);
  expect(stored.fieldSources.municipalityPopulation.verificationStatus).toBe("USER_DECLARED");
  expect(stored.fieldSources.municipalityPopulation.verifiedAt).toBeNull();

  await page.reload();
  await expect(page.getByLabel("Počet obyvatel obce (volitelné)")).toHaveValue("3200");
  await page.getByLabel("Kód obce (volitelné)").fill("654321");
  await page.getByRole("button", { name: "Uložit místně" }).click();
  await expect(page.getByRole("status")).toContainText("Nepřenášíme starý údaj");
  expect(await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? "null").municipalityCode, storageKey)).toBe("123456");
  await page.getByLabel("Kód obce (volitelné)").fill("123456");
  await page.getByRole("button", { name: "Zobrazit export JSON" }).click();
  const exported = await page.getByLabel("Export profilu (obsahuje vámi uvedené údaje)").inputValue();
  expect(JSON.parse(exported).municipalityPopulation).toBe(3200);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Smazat místní profil" }).click();
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBeNull();
  await page.getByLabel("Obnovit profil z JSON").fill(exported);
  await page.getByRole("button", { name: "Obnovit místně" }).click();
  await expect(page.getByRole("status")).toContainText("Profil byl obnoven");
  await page.reload();
  await expect(page.getByLabel("Typ žadatele")).toHaveValue("MUNICIPALITY");
  expect(apiRequests).toEqual([]);
});

test("editing applicant type and municipality removes dependent imported facts and provenance", async ({ page }) => {
  await page.goto("/profil");
  await page.getByLabel("Typ žadatele").selectOption("BUSINESS");
  await page.getByLabel("Kód obce (volitelné)").fill("123456");
  await page.getByLabel("Počet obyvatel obce (volitelné)").fill("3200");
  await page.getByRole("button", { name: "Uložit místně" }).click();
  await page.evaluate((key) => {
    const profile = JSON.parse(localStorage.getItem(key)!);
    profile.applicantTypeId = "business-hierarchy";
    profile.municipalityName = "Původní obec";
    profile.regionCode = "OLD";
    profile.seatGeographyId = "old-seat";
    profile.municipalityPopulationAsOf = "2026-01-01";
    for (const field of ["applicantTypeId", "municipalityName", "regionCode", "seatGeographyId", "municipalityPopulationAsOf"]) {
      profile.fieldSources[field] = profile.fieldSources.applicantType;
    }
    localStorage.setItem(key, JSON.stringify(profile));
  }, storageKey);
  await page.reload();
  await page.getByLabel("Typ žadatele").selectOption("NATURAL_PERSON");
  await page.getByLabel("Kód obce (volitelné)").fill("654321");
  await page.getByLabel("Počet obyvatel obce (volitelné)").fill("3300");
  await page.getByRole("button", { name: "Uložit místně" }).click();
  await expect(page.getByRole("status")).toContainText("uložen pouze");
  const stored = await page.evaluate((key) => JSON.parse(localStorage.getItem(key)!), storageKey);
  expect(stored.applicantType).toBe("NATURAL_PERSON");
  expect(stored.municipalityCode).toBe("654321");
  expect(stored.municipalityPopulation).toBe(3300);
  for (const field of ["applicantTypeId", "municipalityName", "regionCode", "seatGeographyId", "municipalityPopulationAsOf"]) {
    expect(stored[field]).toBeNull();
    expect(stored.fieldSources[field]).toBeUndefined();
  }
});

test("unknown-version profile is preserved and cannot be silently overwritten", async ({ page }) => {
  await page.goto("/profil");
  await page.evaluate((key) => localStorage.setItem(key, '{"schemaVersion":"99.0.0","future":"recover-me"}'), storageKey);
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Nejsou automaticky smazána");
  await expect(page.getByRole("button", { name: "Uložit místně" })).toBeDisabled();
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toContain("recover-me");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Smazat místní profil" }).click();
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toContain("recover-me");
});

test("profile mobile reflow and automated accessibility", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/profil");
  await expect(page.getByRole("heading", { name: "Údaje pro posouzení výzev" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations).toEqual([]);
});
