import { readFileSync } from "node:fs";

const path = new URL("../apps/api/wrangler.jsonc", import.meta.url);
const raw = readFileSync(path, "utf8");
const json = JSON.parse(raw.replace(/^\s*\/\/.*$/gm, ""));
const errors = [];

if (json.workers_dev !== false) errors.push("workers_dev must remain false by default");
if (json.send_metrics !== false) errors.push("send_metrics must remain false");
if (json.vars?.ENVIRONMENT !== "local") errors.push("committed config must target local environment");
if (!Array.isArray(json.d1_databases) || json.d1_databases[0]?.binding !== "DB") errors.push("D1 DB binding missing");
if (!Array.isArray(json.r2_buckets) || json.r2_buckets[0]?.binding !== "RAW") errors.push("R2 RAW binding missing");
if (!Array.isArray(json.vectorize) || json.vectorize[0]?.binding !== "SEARCH") errors.push("Vectorize SEARCH binding missing");

if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("Cloudflare config invariants OK");
