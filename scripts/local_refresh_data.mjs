import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { join, resolve } from "node:path";
import { platform } from "node:process";

const root = resolve(import.meta.dirname, "..");
const venv = join(root, ".venv");
const venvPython =
  platform === "win32"
    ? join(venv, "Scripts", "python.exe")
    : join(venv, "bin", "python");

function spawn(command, args, { quiet = false, shell = false } = {}) {
  return spawnSync(command, args, {
    cwd: root,
    stdio: quiet ? "ignore" : "inherit",
    shell,
  });
}

function requireSuccess(command, args, options = {}) {
  const result = spawn(command, args, options);
  if (result.status !== 0) process.exit(result.status ?? 1);
}

function detectPython() {
  const candidates =
    platform === "win32"
      ? [
          ["python", []],
          ["py", ["-3"]],
        ]
      : [
          ["python3", []],
          ["python", []],
        ];

  for (const [command, prefix] of candidates) {
    const result = spawn(command, [...prefix, "--version"], { quiet: true });
    if (result.status === 0) return { command, prefix };
  }
  throw new Error(
    "Python 3.11+ nebyl nalezen. Je potřeba pro source connectory a ingestion.",
  );
}

function applySql(file) {
  return (
    spawn(
      "npm",
      [
        "--workspace",
        "@dotacni-majak/api",
        "exec",
        "--",
        "wrangler",
        "d1",
        "execute",
        "dotacni-majak-local",
        "--local",
        "--persist-to",
        "../../.wrangler/local",
        "--file",
        `../../.local/${file}`,
      ],
      { shell: platform === "win32" },
    ).status === 0
  );
}

await mkdir(join(root, ".local"), { recursive: true });

if (!existsSync(venvPython)) {
  const python = detectPython();
  console.log("Vytvářím lokální Python prostředí .venv…");
  requireSuccess(python.command, [...python.prefix, "-m", "venv", ".venv"]);
}

console.log("Aktualizuji Python závislosti pro lokální source ingestion…");
requireSuccess(venvPython, [
  "-m",
  "pip",
  "install",
  "--disable-pip-version-check",
  "-q",
  "-e",
  "packages/source-sdk",
  "-e",
  "connectors/nsa",
  "-e",
  "connectors/dotaceeu",
]);

const sources = [
  {
    code: "NSA",
    command: ["scripts/local_ingest_nsa.py"],
    sql: "nsa-import.sql",
  },
  {
    code: "DOTACEEU",
    command: ["scripts/local_ingest_dotaceeu.py"],
    sql: "dotaceeu-import.sql",
  },
];

const succeeded = [];
const failed = [];

for (const source of sources) {
  console.log(`\n=== ${source.code}: live refresh ===`);
  const generated = spawn(venvPython, source.command).status === 0;
  if (!generated) {
    failed.push({ source: source.code, stage: "fetch" });
    console.warn(`${source.code}: fetch/normalize selhal, zachovávám last-known-good data.`);
    continue;
  }

  const applied = applySql(source.sql);
  if (!applied) {
    failed.push({ source: source.code, stage: "publish" });
    console.warn(`${source.code}: publish selhal, ostatní zdroje zůstávají nedotčené.`);
    continue;
  }

  succeeded.push(source.code);
}

const marker = {
  refreshedAt: new Date().toISOString(),
  succeeded,
  failed,
};
await writeFile(
  join(root, ".local", "data-refresh.json"),
  JSON.stringify(marker, null, 2) + "\n",
  "utf8",
);

console.log(`\nÚspěšné zdroje: ${succeeded.join(", ") || "žádné"}`);
if (failed.length) {
  console.warn("Selhané zdroje:", failed);
}

if (succeeded.length === 0) {
  process.exit(1);
}
// A partial source outage must not make a successful last-known-good refresh
// look like a total failure. Details remain in data-refresh.json and stdout.
