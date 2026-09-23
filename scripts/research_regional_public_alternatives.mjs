import { chromium } from "@playwright/test";

const targets = [
  {
    code: "STC",
    url: "https://stredoceskykraj.cz/web/dotace",
    allowed: new Set(["stredoceskykraj.cz", "www.stredoceskykraj.cz"]),
    detail: /\/web\/dotace\/[^?#/]+/i,
    document: /\/documents\/|\.(pdf|docx?|xlsx?)(?:$|\?)/i,
  },
  {
    code: "VYS",
    url:
      "https://www.kr-vysocina.cz/vismo/rejstrik.asp" +
      "?id_org=450008&p1=122604&p3=.&rh=397",
    allowed: new Set(["www.kr-vysocina.cz", "kr-vysocina.cz"]),
    detail: /\/[^?#]*\/d-\d+(?:\/|$|\?)/i,
    document: /\/assets\/File\.ashx|\.(pdf|docx?|xlsx?)(?:$|\?)/i,
  },
];

function clean(value) {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function safeLink(raw, base, config) {
  try {
    const u = new URL(raw, base);
    if (u.protocol !== "https:") return null;
    if (!config.allowed.has(u.hostname.toLowerCase())) return null;
    return {
      origin: u.origin,
      pathname: u.pathname,
      queryKeys: [...new Set([...u.searchParams.keys()])].sort(),
      href: u.href,
    };
  } catch {
    return null;
  }
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  locale: "cs-CZ",
  userAgent:
    "DotacniMajak-SourceResearch/0.4 (+https://github.com/Bbambaaamm/dotacni-majak)",
});

const results = [];

for (const target of targets) {
  const page = await context.newPage();
  let error = null;
  let status = null;
  let title = null;
  let preview = null;
  let links = [];

  try {
    const response = await page.goto(target.url, {
      waitUntil: "domcontentloaded",
      timeout: 45_000,
    });
    status = response?.status() ?? null;
    await page.waitForTimeout(4_000);
    title = await page.title();
    preview = clean(await page.locator("body").innerText()).slice(0, 5000);

    const rawLinks = await page.locator("a[href]").evaluateAll((nodes) =>
      nodes.slice(0, 4000).map((node) => ({
        text: (node.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 300),
        href: node.getAttribute("href") ?? "",
      })),
    );

    const seen = new Set();
    for (const item of rawLinks) {
      const safe = safeLink(item.href, page.url(), target);
      if (!safe || seen.has(safe.href)) continue;
      seen.add(safe.href);
      const kind = target.document.test(safe.pathname + new URL(safe.href).search)
        ? "document"
        : target.detail.test(safe.pathname + new URL(safe.href).search)
          ? "detail"
          : /dotac|fond|grant|program/i.test(item.text + " " + safe.href)
            ? "related"
            : null;
      if (!kind) continue;
      links.push({
        kind,
        text: item.text,
        ...safe,
      });
      if (links.length >= 160) break;
    }
  } catch (exc) {
    error = exc instanceof Error ? exc.message : String(exc);
  }

  results.push({
    code: target.code,
    requestedUrl: target.url,
    finalUrl: page.url(),
    status,
    title,
    bodyPreview: preview,
    links,
    counts: {
      detail: links.filter((x) => x.kind === "detail").length,
      document: links.filter((x) => x.kind === "document").length,
      related: links.filter((x) => x.kind === "related").length,
    },
    error,
  });
  await page.close();
}

console.log(
  JSON.stringify(
    {
      results,
      note:
        "Probe reads only public unauthenticated HTML and same-origin public links. " +
        "It does not log cookies, authorization headers, request/response bodies, " +
        "or bypass portal protections.",
    },
    null,
    2,
  ),
);

await context.close();
await browser.close();
