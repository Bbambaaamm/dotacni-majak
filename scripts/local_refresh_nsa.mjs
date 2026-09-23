import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { platform } from "node:process";

const root = resolve(import.meta.dirname, "..");
const venv = join(root, ".venv");
const venvPython =
  platform === "win32"
    ? join(venv, "Scripts", "python.exe")
    : join(venv, "bin", "python");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    shell: false,
    ...options,
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
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
    const result = spawnSync(command, [...prefix, "--version"], {
      cwd: root,
      stdio: "ignore",
      shell: false,
    });
    if (result.status === 0) return { command, prefix };
  }
  throw new Error(
    "Python 3.11+ nebyl nalezen. Je potřeba pro source connectory a ingestion.",
  );
}

await mkdir(join(root, ".local"), { recursive: true });

if (!existsSync(venvPython)) {
  const python = detectPython();
  console.log("Vytvářím lokální Python prostředí .venv…");
  run(python.command, [...python.prefix, "-m", "venv", ".venv"]);
}

console.log("Aktualizuji Python závislosti pro NSA ingestion…");
run(venvPython, [
  "-m",
  "pip",
  "install",
  "--disable-pip-version-check",
  "-q",
  "-e",
  "packages/source-sdk",
  "-e",
  "connectors/nsa",
]);

console.log("Stahuji aktuální veřejné výzvy NSA a připravuji canonical import…");
run(venvPython, ["scripts/local_ingest_nsa.py"]);

console.log("Aplikuji data do lokální D1…");
run(
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
    "../../.local/nsa-import.sql",
  ],
  { shell: platform === "win32" },
);

await writeFile(
  join(root, ".local", "nsa-refresh.json"),
  JSON.stringify(
    { source: "NSA", refreshedAt: new Date().toISOString() },
    null,
    2,
  ) + "\n",
  "utf8",
);

console.log("Lokální NSA data jsou připravená.");
