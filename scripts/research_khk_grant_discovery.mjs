import { chromium } from "@playwright/test";

const ROOT_URL = "https://dotace.khk.cz/";
const LIST_URL = "https://dotace.khk.cz/grantProgram?year=2027&year=2026";

function shape(value, depth = 0) {
  if (depth > 5) return "<max-depth>";
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

function sanitizeRequest(request) {
  try {
    const u = new URL(request.url());
    if (u.protocol !== "https:") return null;
    return {
      method: request.method(),
      resourceType: request.resourceType(),
      origin: u.origin,
      pathname: u.pathname,
      queryKeys: [...new Set([...u.searchParams.keys()])].sort(),
      requestHasBody: Boolean(request.postData()),
    };
  } catch {
    return null;
  }
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  locale: "cs-CZ",
  userAgent:
    "DotacniMajak-SourceResearch/0.3 (+https://github.com/Bbambaaamm/dotacni-majak)",
});
const page = await context.newPage();

const contracts = new Map();
const responseTasks = [];

page.on("response", (response) => {
  const task = (async () => {
    const request = response.request();
    const item = sanitizeRequest(request);
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

    contracts.set(`${item.method} ${item.origin}${item.pathname}`, {
      ...item,
      status: response.status(),
      contentType,
      responseShape,
    });
  })();
  responseTasks.push(task);
});

async function publicProgramLinks() {
  return await page.locator('a[href*="/grantProgram/"]').evaluateAll((nodes) =>
    nodes
      .map((node) => ({
        text: (node.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 220),
        href: node.href,
      }))
      .filter((item) => /^https:\/\/dotace\.khk\.cz\/grantProgram\/[A-Za-z0-9_-]+\/?$/.test(item.href))
      .filter(
        (item, index, all) =>
          all.findIndex((other) => other.href === item.href) === index,
      )
      .slice(0, 80),
  );
}

let error = null;
let listStatus = null;
let listBodyPreview = null;
let links = [];
let detailUrl = null;
let detailBodyPreview = null;

try {
  const response = await page.goto(LIST_URL, {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });
  listStatus = response?.status() ?? null;
  await page.waitForTimeout(10_000);

  listBodyPreview = (await page.locator("body").innerText())
    .replace(/\s+/g, " ")
    .slice(0, 6000);
  links = await publicProgramLinks();

  if (links.length) {
    detailUrl = links[0].href;
    await page.goto(detailUrl, {
      waitUntil: "domcontentloaded",
      timeout: 45_000,
    });
    await page.waitForTimeout(8_000);
    detailBodyPreview = (await page.locator("body").innerText())
      .replace(/\s+/g, " ")
      .slice(0, 6500);
  }

  await Promise.allSettled(responseTasks);
} catch (exc) {
  error = exc instanceof Error ? exc.message : String(exc);
}

console.log(
  JSON.stringify(
    {
      rootUrl: ROOT_URL,
      listUrl: LIST_URL,
      listStatus,
      listBodyPreview,
      programLinks: links,
      detailUrl,
      detailBodyPreview,
      xhrContracts: [...contracts.values()].sort((a, b) =>
        `${a.method} ${a.origin}${a.pathname}`.localeCompare(
          `${b.method} ${b.origin}${b.pathname}`,
        ),
      ),
      note:
        "No cookies/auth headers/request bodies/response bodies are logged; output contains public URLs, rendered public text and JSON shapes only.",
      error,
    },
    null,
    2,
  ),
);

await context.close();
await browser.close();
