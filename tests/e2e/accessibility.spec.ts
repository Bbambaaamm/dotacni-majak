import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const routes = [
  ["/", "homepage"],
  ["/hledat", "výsledky hledání"],
  ["/dotace/regiony-2026", "detail výzvy"],
] as const;

for (const [path, label] of routes) {
  test(label + " nemá automaticky detekované WCAG A/AA violations", async ({ page }) => {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();

    expect(results.violations).toEqual([]);
  });
}

test("skip link funguje z klávesnice", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: /přeskočit na hlavní obsah/i });
  await expect(skip).toBeFocused();
  await skip.press("Enter");
  await expect(page.locator("main")).toBeFocused();
});
