import { chromium } from "@playwright/test";

const START_URL = "https://jdp2.mf.gov.cz/";

function safeCandidate(urlString, method, resourceType) {
  try {
    const url = new URL(urlString);
    if (url.protocol !== "https:") return null;
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

const SAFE_PUBLIC_LITERAL_KEYS = new Set([
  "filterTree",
  "fixedFilterId",
  "fkName",
  "fkValue",
  "pageIndex",
  "pageSize",
  "sort",
  "operator",
  "propName",
  "value",
  "isDescending",
  "treatNullLowest",
]);

function shape(value, depth = 0, parentKey = "") {
  if (depth > 4) return "<max-depth>";
  if (value === null) return null;
  if (Array.isArray(value)) {
    return {
      type: "array",
      length: value.length,
      sample: value.length ? shape(value[0], depth + 1, parentKey) : null,
    };
  }
  if (typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, shape(value[key], depth + 1, key)]),
    );
  }
  if (
    SAFE_PUBLIC_LITERAL_KEYS.has(parentKey) &&
    (typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean")
  ) {
    return value;
  }
  if (typeof value === "string") return "<string>";
  if (typeof value === "number") return "<number>";
  if (typeof value === "boolean") return "<boolean>";
  return `<${typeof value}>`;
}

function requestBodyShape(request) {
  const raw = request.postData();
  if (!raw) return null;
  try {
    return { encoding: "json", shape: shape(JSON.parse(raw)) };
  } catch {
    const params = new URLSearchParams(raw);
    if ([...params.keys()].length) {
      return {
        encoding: "form",
        fields: [...new Set([...params.keys()])].sort(),
      };
    }
    return {
      encoding: "opaque",
      byteLength: Buffer.byteLength(raw, "utf8"),
    };
  }
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  locale: "cs-CZ",
  userAgent:
    "DotacniMajak-SourceResearch/0.2 (+https://github.com/Bbambaaamm/dotacni-majak)",
});

const page = await context.newPage();
const candidates = new Map();
const publicDashboardContracts = new Map();
const responseTasks = [];

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

  if (looksDataLike) {
    const key = JSON.stringify(candidate);
    candidates.set(key, candidate);
  }

  if (
    candidate.pathname
      .toLowerCase()
      .includes("/jdp_api/api/nxwebedppublicdashboard/")
  ) {
    const key = `${candidate.method} ${candidate.pathname}`;
    const existing = publicDashboardContracts.get(key) ?? {};
    publicDashboardContracts.set(key, {
      ...existing,
      method: candidate.method,
      pathname: candidate.pathname,
      requestContentType: request.headers()["content-type"] ?? null,
      requestBody: requestBodyShape(request),
    });
  }
});

page.on("response", (response) => {
  const task = (async () => {
    const request = response.request();
    const candidate = safeCandidate(
      request.url(),
      request.method(),
      request.resourceType(),
    );
    if (
      !candidate ||
      !candidate.pathname
        .toLowerCase()
        .includes("/jdp_api/api/nxwebedppublicdashboard/")
    ) {
      return;
    }

    const key = `${candidate.method} ${candidate.pathname}`;
    const existing = publicDashboardContracts.get(key) ?? {};
    let responseShape = null;
    const contentType = response.headers()["content-type"] ?? "";

    if (contentType.includes("application/json")) {
      try {
        responseShape = shape(await response.json());
      } catch {
        responseShape = "<json-unreadable>";
      }
    }

    publicDashboardContracts.set(key, {
      ...existing,
      method: candidate.method,
      pathname: candidate.pathname,
      responseStatus: response.status(),
      responseContentType: contentType,
      responseShape,
    });
  })();
  responseTasks.push(task);
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
  await page.waitForTimeout(12_000);
  title = await page.title();
  bodyPreview = (await page.locator("body").innerText())
    .replace(/\s+/g, " ")
    .slice(0, 1200);

  const detailLink = page.getByText("Detail", { exact: true }).first();
  if (await detailLink.count()) {
    await detailLink.click();
    await page.waitForTimeout(5_000);
  }

  await Promise.allSettled(responseTasks);
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
      publicDashboardContracts: [...publicDashboardContracts.values()].sort(
        (a, b) =>
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

if (error) process.exitCode = 2;
