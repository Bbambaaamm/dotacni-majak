import { chromium } from "@playwright/test";

const START_URL = "https://dotace.khk.cz/";

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
    "DotacniMajak-SourceResearch/0.2 (+https://github.com/Bbambaaamm/dotacni-majak)",
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

let error = null;
let initialUrl = null;
let finalUrl = null;
let clicked = false;
let bodyPreview = null;
let anchors = [];

try {
  await page.goto(START_URL, {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });
  initialUrl = page.url();
  await page.waitForTimeout(8_000);

  const target = page.getByText("DOTAČNÍ OBLASTI", { exact: true }).first();
  if (await target.count()) {
    clicked = true;
    await target.click();
    await page.waitForTimeout(8_000);
  }

  finalUrl = page.url();
  bodyPreview = (await page.locator("body").innerText())
    .replace(/\s+/g, " ")
    .slice(0, 5000);

  anchors = await page.locator("a").evaluateAll((nodes) =>
    nodes
      .map((node) => ({
        text: (node.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 180),
        href: node.href,
      }))
      .filter((item) => item.href.startsWith("https://dotace.khk.cz/"))
      .filter(
        (item, index, all) =>
          all.findIndex((other) => other.href === item.href && other.text === item.text) ===
          index,
      )
      .slice(0, 250),
  );

  await Promise.allSettled(responseTasks);
} catch (exc) {
  error = exc instanceof Error ? exc.message : String(exc);
}

console.log(
  JSON.stringify(
    {
      startUrl: START_URL,
      initialUrl,
      clicked,
      finalUrl,
      bodyPreview,
      anchors,
      xhrContracts: [...contracts.values()].sort((a, b) =>
        `${a.method} ${a.pathname}`.localeCompare(`${b.method} ${b.pathname}`),
      ),
      note:
        "No cookies/auth headers/request bodies/response bodies are logged; output contains public URLs, link text and JSON shapes only.",
      error,
    },
    null,
    2,
  ),
);

await context.close();
await browser.close();
