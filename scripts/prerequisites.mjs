#!/usr/bin/env node
/**
 * Prerequisites check for Dotační maják local development.
 *
 * Validates that all *runtime* prerequisites (Node.js, npm, Python 3)
 * are available before running `npm install` / `npm run dev`.
 *
 * Exit code: 0 = all checks passed, 1 = one or more checks failed.
 * Usage:    node scripts/prerequisites.mjs
 */

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = join(import.meta.dirname, "..");

const results = [];

function check(name, run) {
  let detail = null;
  try {
    detail = run();
  } catch (e) {
    detail = e.message || String(e);
  }
  const passed = detail === null;
  results.push({ name, passed, detail: passed ? "OK" : detail });
}

// --- 1. Node.js ---
check("Node.js", () => {
  const nvmrc = (() => {
    try {
      return readFileSync(join(ROOT, ".nvmrc"), "utf-8").trim();
    } catch {
      return "20";
    }
  })();
  const required = parseInt(nvmrc, 10) || 20;
  const major = parseInt(process.versions.node.split(".")[0], 10);
  if (major < required) {
    return `Node.js >= ${required} required (per .nvmrc=${nvmrc}), found v${process.versions.node}`;
  }
  return null;
});

// --- 2. npm ---
check("npm", () => {
  try {
    execFileSync("npm", ["--version"], { stdio: "pipe" });
    return null;
  } catch {
    return "npm not found — install Node.js (npm ships with it)";
  }
});

// --- 3. Python 3 (required by data-pipeline refresh scripts) ---
check("Python 3", () => {
  try {
    const out = execFileSync("python3", ["--version"], { stdio: "pipe" })
      .toString()
      .trim();
    if (out.startsWith("Python 3.")) {
      return null;
    }
    return `Unexpected python3 version: ${out}`;
  } catch {
    return "python3 not found — required for `npm run dev:data:refresh`";
  }
});

// --- Report ---
let allPassed = true;
console.log("=== Dotační maják — předpoklady ===");
for (const r of results) {
  const icon = r.passed ? "OK" : "CHYBA";
  console.log(`[${icon}] ${r.name}: ${r.detail}`);
  if (!r.passed) allPassed = false;
}

if (allPassed) {
  console.log(
    "\nOK — všechny předpoklady splněny. Spusť `npm run dev` pro lokální vývoj."
  );
  process.exit(0);
}

console.error(
  "\nCHYBA — některé předpoklady chybí. Viz docs/LOCAL_DEVELOPMENT.md → Troubleshooting."
);
process.exit(1);
