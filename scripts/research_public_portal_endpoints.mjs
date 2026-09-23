import { chromium } from "@playwright/test";

const START_URL = process.env.START_URL;
const LABEL = process.env.SOURCE_LABEL ?? START_URL;
const PATH_HINT = new RegExp(
  process.env.PATH_HINT ?? "api|grant|dotac|vyzv|program|fond|search|catalog",
  "i",
);
const CLICK_TEXT = process.env.CLICK_TEXT?.trim() || null;

if (!START_URL) {
  throw new Error("START_URL is required");
}

function shape(value, depth = 0) {
  if (depth > 4) return "<max-depth>";
  if (value === null) return null;
  if (Array.isArray(value)) {
    return {
      type: "array",
      length: value.length,
      sample: value.length ? shape(value[0], depth + 1) : null,
    };
  }
  if (typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, shape(value[key], depth + 1)]),
    );
  }
  if (typeof value === "string") return "<string>";
  if (typeof value === "number") return "<number>";
  if (typeof value === "boolean") return "<boolean>";
  return `<${typeof value}>`;
}

function publicRequest(urlString, method, resourceType) {
  try {
    const url = new URL(urlString);
    if (url.protocol !== "https:") return null;
    return {
      method,
      resourceType,
      origin: url.origin,
      pathname: url.pathname,
      queryKeys: [...new Set([...url.searchParams.keys()])].sort(),
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

const requests = new Map();
const contracts = new Map();
const responseTasks = [];

page.on("request", (request) => {
  const item = publicRequest(
    request.url(),
    request.method(),
    request.resourceType(),
  );
  if (!item) return;
  if (
    item.resourceType === "xhr" ||
    item.resourceType === "fetch" ||
    PATH_HINT.test(item.pathname)
  ) {
    requests.set(JSON.stringify(item), item);
  }
});

page.on("response", (response) => {
  const task = (async () => {
    const request = response.request();
    const item = publicRequest(
      request.url(),
      request.method(),
      request.resourceType(),
    );
    if (!item) return;
    if (!(item.resourceType === "xhr" || item.resourceType === "fetch")) return;

    const contentType = response.headers()["content-type"] ?? "";
    let responseShape = null;
    if (contentType.includes("application/json")) {
      try {
        responseShape = shape(await response.json());
      } catch {
        responseShape = "<json-unreadable>";
      }
    }

    const key = `${item.method} ${item.origin}${item.pathname}`;
    contracts.set(key, {
      ...item,
      status: response.status(),
      contentType,
      responseShape,
      requestHasBody: Boolean(request.postData()),
    });
  })();
  responseTasks.push(task);
});

let status = null;
let title = null;
let bodyPreview = null;
let error = null;

try {
  const response = await page.goto(START_URL, {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });
  status = response?.status() ?? null;
  await page.waitForTimeout(12_000);
  title = await page.title();
  bodyPreview = (await page.locator("body").innerText())
    .replace(/\s+/g, " ")
    .slice(0, 1600);

  if (CLICK_TEXT) {
    const target = page.getByText(CLICK_TEXT, { exact: true }).first();
    if (await target.count()) {
      await target.click();
      await page.waitForTimeout(8_000);
      bodyPreview = (await page.locator("body").innerText())
        .replace(/\s+/g, " ")
        .slice(0, 2200);
    }
  }

  await Promise.allSettled(responseTasks);
} catch (exc) {
  error = exc instanceof Error ? exc.message : String(exc);
}

console.log(
  JSON.stringify(
    {
      label: LABEL,
      startUrl: START_URL,
      pageStatus: status,
      title,
      bodyPreview,
      error,
      clickedText: CLICK_TEXT,
      requestCandidates: [...requests.values()].sort((a, b) =>
        JSON.stringify(a).localeCompare(JSON.stringify(b)),
      ),
      xhrContracts: [...contracts.values()].sort((a, b) =>
        `${a.method} ${a.pathname}`.localeCompare(
          `${b.method} ${b.pathname}`,
        ),
      ),
    },
    null,
    2,
  ),
);

await context.close();
await browser.close();

// A blocked/unavailable portal is itself a valid research result. We keep the
// evidence in the log and do not turn source availability into a code failure.

