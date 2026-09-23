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
let grantCollectionRequest = null;
let grantCollectionSample = null;
const selectedPublicBodies = {};
let selectedDetailSample = null;
let selectedDocumentSample = null;
let detailDownloadLinks = [];

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

    if (
      item.origin === "https://dotisreactfunctions.azurewebsites.net" &&
      [
        "/api/Data/GetProjectSubprojectCollection",
        "/api/Data/GetSubproject",
        "/api/Data/GetSubprojectDocumentCollection",
      ].includes(item.pathname)
    ) {
      try {
        const rawBody = request.postData();
        selectedPublicBodies[item.pathname] = rawBody ? JSON.parse(rawBody) : null;
      } catch {
        selectedPublicBodies[item.pathname] = "<unparseable-json>";
      }
    }

    if (
      item.origin === "https://dotisreactfunctions.azurewebsites.net" &&
      item.pathname === "/api/Data/GetProjectSubprojectCollection"
    ) {
      try {
        const rawBody = request.postData();
        grantCollectionRequest = rawBody ? JSON.parse(rawBody) : null;
      } catch {
        grantCollectionRequest = "<unparseable-json>";
      }

      try {
        const payload = await response.json();
        const rows = Array.isArray(payload?.data) ? payload.data : [];
        grantCollectionSample = rows.slice(0, 3).map((row) => ({
          id_Def_Project: row?.id_Def_Project ?? null,
          memo: row?.memo ?? null,
          name: row?.name ?? null,
          subprojects: Array.isArray(row?.subprojects)
            ? row.subprojects.slice(0, 5).map((sub) => ({
                id_Def_Subproject: sub?.id_Def_Subproject ?? null,
                memo: sub?.memo ?? null,
                name: sub?.name ?? null,
                dateBeg: sub?.dateBeg ?? null,
                dateEnd: sub?.dateEnd ?? null,
                state: sub?.state ?? null,
              }))
            : [],
        }));
      } catch {
        grantCollectionSample = "<json-unreadable>";
      }
    }

    if (
      item.origin === "https://dotisreactfunctions.azurewebsites.net" &&
      item.pathname === "/api/Data/GetSubproject"
    ) {
      try {
        const payload = await response.json();
        const row = payload?.data ?? null;
        selectedDetailSample = row
          ? {
              id_Def_Subproject: row.id_Def_Subproject ?? null,
              memo: row.memo ?? null,
              name: row.name ?? null,
              dateBeg: row.dateBeg ?? null,
              dateEnd: row.dateEnd ?? null,
              desc: row.desc ?? null,
              purposeList: row.purposeList ?? null,
              applicantsRange: row.applicantsRange ?? null,
              percentMaximum: row.percentMaximum ?? null,
              percentMaximumWeb: row.percentMaximumWeb ?? null,
              priceMinimum: row.priceMinimum ?? null,
              priceMinimumWeb: row.priceMinimumWeb ?? null,
              priceMaximum: row.priceMaximum ?? null,
              priceMaximumWeb: row.priceMaximumWeb ?? null,
              totalPrice: row.totalPrice ?? null,
              totalPriceWeb: row.totalPriceWeb ?? null,
              programLinks: row.programLinks ?? null,
            }
          : null;
      } catch {
        selectedDetailSample = "<json-unreadable>";
      }
    }

    if (
      item.origin === "https://dotisreactfunctions.azurewebsites.net" &&
      item.pathname === "/api/Data/GetSubprojectDocumentCollection"
    ) {
      try {
        const payload = await response.json();
        const rows = Array.isArray(payload?.data) ? payload.data : [];
        selectedDocumentSample = rows.slice(0, 8).map((row) => ({
          id_Document: row?.id_Document ?? null,
          title: row?.title ?? null,
          note: row?.note ?? null,
          ext: row?.ext ?? null,
          size: row?.size ?? null,
        }));
      } catch {
        selectedDocumentSample = "<json-unreadable>";
      }
    }
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

  // The React listing does not expose program cards as <a>; their public
  // codes are delivered by GetProjectSubprojectCollection. Use the first
  // captured public code, falling back to a known search-indexed public
  // program only when the async capture finishes after the DOM inspection.
  const capturedCode =
    Array.isArray(grantCollectionSample) &&
    grantCollectionSample[0]?.subprojects?.[0]?.memo
      ? grantCollectionSample[0].subprojects[0].memo
      : "26SPT10";
  detailUrl = links[0]?.href ?? `https://dotace.khk.cz/grantProgram/${capturedCode}`;

  if (detailUrl) {
    await page.goto(detailUrl, {
      waitUntil: "domcontentloaded",
      timeout: 45_000,
    });
    await page.waitForTimeout(8_000);
    detailBodyPreview = (await page.locator("body").innerText())
      .replace(/\s+/g, " ")
      .slice(0, 6500);
    detailDownloadLinks = await page.locator("a[href]").evaluateAll((nodes) =>
      nodes
        .map((node) => ({
          text: (node.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 250),
          href: node.href,
        }))
        .filter((item) =>
          /document|download|\.pdf($|\?)|\.docx?($|\?)|\.xlsx?($|\?)/i.test(item.href)
        )
        .filter(
          (item, index, all) =>
            all.findIndex((other) => other.href === item.href) === index,
        )
        .slice(0, 40),
    );
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
      grantCollectionRequest,
      grantCollectionSample,
      selectedPublicBodies,
      selectedDetailSample,
      selectedDocumentSample,
      detailDownloadLinks,
      xhrContracts: [...contracts.values()].sort((a, b) =>
        `${a.method} ${a.origin}${a.pathname}`.localeCompare(
          `${b.method} ${b.origin}${b.pathname}`,
        ),
      ),
      note:
        "No cookies/auth headers are logged. Bodies are captured only for three observed unauthenticated read-only public endpoints needed to establish the connector contract; responses are reduced to selected public grant/document metadata.",
      error,
    },
    null,
    2,
  ),
);

await context.close();
await browser.close();
