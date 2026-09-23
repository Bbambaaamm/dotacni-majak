import { chromium } from "@playwright/test";

const SEARCH_URL = "https://stredoceskykraj.cz/web/urad/vyhledavani";
const QUERY = "Program 2026";
const ALLOWED = new Set(["stredoceskykraj.cz", "www.stredoceskykraj.cz"]);

function safeUrl(raw, base) {
  try {
    const u = new URL(raw, base);
    if (u.protocol !== "https:" || !ALLOWED.has(u.hostname.toLowerCase())) {
      return null;
    }
    return {
      href: u.href,
      origin: u.origin,
      pathname: u.pathname,
      queryKeys: [...new Set([...u.searchParams.keys()])].sort(),
    };
  } catch {
    return null;
  }
}

function clean(v) {
  return (v ?? "").replace(/\s+/g, " ").trim();
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  locale: "cs-CZ",
  userAgent:
    "DotacniMajak-SourceResearch/0.5 (+https://github.com/Bbambaaamm/dotacni-majak)",
});
const page = await context.newPage();

let error = null;
let initialStatus = null;
let finalUrl = null;
let formContracts = [];
let resultLinks = [];
let bodyPreview = null;

try {
  const response = await page.goto(SEARCH_URL, {
    waitUntil: "commit",
    timeout: 30_000,
  });
  initialStatus = response?.status() ?? null;
  await page.waitForTimeout(6_000);

  formContracts = await page.locator("form").evaluateAll((forms) =>
    forms.slice(0, 40).map((form) => ({
      action: form.action,
      method: (form.method || "get").toUpperCase(),
      controls: [...form.querySelectorAll("input,select,button")]
        .slice(0, 80)
        .map((el) => ({
          tag: el.tagName,
          type: el.getAttribute("type"),
          name: el.getAttribute("name"),
          valueHint:
            el.tagName === "BUTTON"
              ? (el.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 120)
              : null,
        })),
    })),
  );

  const textboxes = page.getByRole("textbox");
  const count = await textboxes.count();
  let submitted = false;

  for (let i = 0; i < count && !submitted; i += 1) {
    const input = textboxes.nth(i);
    if (!(await input.isVisible().catch(() => false))) continue;
    await input.fill(QUERY);
    await input.press("Enter").catch(() => null);
    submitted = true;
  }

  if (submitted) {
    await page.waitForTimeout(8_000);
  }

  finalUrl = page.url();
  bodyPreview = clean(await page.locator("body").innerText()).slice(0, 8000);

  const raw = await page.locator("a[href]").evaluateAll((nodes) =>
    nodes.slice(0, 5000).map((node) => ({
      text: (node.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 350),
      href: node.getAttribute("href") ?? "",
    })),
  );

  const seen = new Set();
  for (const item of raw) {
    const safe = safeUrl(item.href, finalUrl || SEARCH_URL);
    if (!safe || seen.has(safe.href)) continue;
    seen.add(safe.href);
    const haystack = (item.text + " " + safe.href).toLowerCase();
    if (
      /\/web\/dotace\//i.test(safe.pathname) ||
      /\/documents\//i.test(safe.pathname) ||
      /program.{0,15}2026|dotac|fond/i.test(haystack)
    ) {
      resultLinks.push({ text: item.text, ...safe });
      if (resultLinks.length >= 200) break;
    }
  }
} catch (exc) {
  error = exc instanceof Error ? exc.message : String(exc);
}

console.log(
  JSON.stringify(
    {
      searchUrl: SEARCH_URL,
      query: QUERY,
      initialStatus,
      finalUrl,
      formContracts,
      resultLinks,
      bodyPreview,
      note:
        "Public unauthenticated county search only. No cookies, auth headers, " +
        "private request bodies, CAPTCHA bypass or protected grant portal access.",
      error,
    },
    null,
    2,
  ),
);

await context.close();
await browser.close();
