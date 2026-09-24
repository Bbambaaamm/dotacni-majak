import { existsSync, readFileSync, statSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

function run(command, args, { required = true } = {}) {
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    shell: true,
  });
  if (required && result.status !== 0) {
    process.exit(result.status ?? 1);
  }
  return result.status === 0;
}

run("npm", ["run", "dev:db:migrate"]);

const refreshMarker = join(root, ".local", "data-refresh.json");
const sixHoursMs = 6 * 60 * 60 * 1000;

function hasRecentSuccessfulRefresh() {
  if (!existsSync(refreshMarker)) return false;
  if (Date.now() - statSync(refreshMarker).mtimeMs > sixHoursMs) return false;

  try {
    const marker = JSON.parse(readFileSync(refreshMarker, "utf8"));
    return Array.isArray(marker.succeeded) && marker.succeeded.length > 0;
  } catch {
    return false;
  }
}

const needsRefresh = !hasRecentSuccessfulRefresh();

if (needsRefresh && process.env.DEV_SKIP_AUTO_REFRESH !== "1") {
  console.log(
    "Lokální dotační data nejsou čerstvá. Spouštím bezpečný multi-source refresh…",
  );
  const refreshed = run("npm", ["run", "dev:data:refresh"], { required: false });
  if (!refreshed) {
    console.warn(
      "Žádný zdroj se teď nepodařilo bezpečně obnovit. Vývojové servery se " +
        "přesto spustí; web transparentně ukáže poslední dostupná nebo prázdná data.",
    );
  }
}

const children = [
  spawn("npm", ["run", "dev:api"], {
    cwd: root,
    stdio: "inherit",
    shell: true,
  }),
  spawn("npm", ["run", "dev:web"], {
    cwd: root,
    stdio: "inherit",
    shell: true,
  }),
];

let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (!child.killed) child.kill();
  }
  process.exitCode = code;
}

for (const child of children) {
  child.on("exit", (code) => {
    if (!stopping && code && code !== 0) stop(code);
  });
}

process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
