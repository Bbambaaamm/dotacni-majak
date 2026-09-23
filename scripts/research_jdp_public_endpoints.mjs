import { chromium } from "@playwright/test";

const START_URL = "https://jdp2.mf.gov.cz/";

function safeCandidate(urlString, method, resourceType) {
  try {
    const url = new URL(urlString);
    if (url.protocol !== "https:") return null;

    // Public research only: never log query values which could later contain
    // identifiers/tokens. We keep hostname + path + parameter names.
    const queryKeys = [...new Set([...url.searchParams.keys()])].sort();

    return {
      method,
      resourceType,
      origin: url.origin,
      pathname: url.pathname,
      queryKeys,
    };
  } catch {
    return null;
  }
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  locale: "cs-CZ",
  userAgent:
    "DotacniMajak-SourceResearch/0.1 (+https://github.com/Bbambaaamm/dotacni-majak)",
});

const page = await context.newPage();
const candidates = new Map();

page.on("request", (request) => {
  const candidate = safeCandidate(
    request.url(),
    request.method(),
    request.resourceType(),
  );
  if (!candidate) return;

  const looksDataLike =
    candidate.resourceType === "xhr" ||
    candidate.resourceType === "fetch" ||
    /api|grant|dotac|vyzv|call|search|catalog|program/i.test(candidate.pathname);

  if (!looksDataLike) return;

  const key = JSON.stringify(candidate);
  candidates.set(key, candidate);
});

let pageStatus = null;
let title = null;
let bodyPreview = null;
let error = null;

try {
  const response = await page.goto(START_URL, {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });
  pageStatus = response?.status() ?? null;

  // Give the public application time to load its catalog/bootstrap data.
  await page.waitForTimeout(12_000);

  title = await page.title();
  bodyPreview = (await page.locator("body").innerText())
    .replace(/\s+/g, " ")
    .slice(0, 1200);
} catch (exc) {
  error = exc instanceof Error ? exc.message : String(exc);
}

console.log(
  JSON.stringify(
    {
      startUrl: START_URL,
      pageStatus,
      title,
      bodyPreview,
      error,
      networkCandidates: [...candidates.values()].sort((a, b) =>
        JSON.stringify(a).localeCompare(JSON.stringify(b)),
      ),
    },
    null,
    2,
  ),
);

await context.close();
await browser.close();

// This is a research probe: inability to access the public portal is useful
// evidence and must be visible in logs, not hidden by invented endpoints.
if (error) process.exitCode = 2;
