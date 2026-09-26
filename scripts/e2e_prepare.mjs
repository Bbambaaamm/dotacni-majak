import { rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join, resolve } from "node:path";
import { platform } from "node:process";

const root = resolve(import.meta.dirname, "..");
const persist = join(root, ".wrangler", "e2e");
rmSync(persist, { recursive: true, force: true });

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    shell: platform === "win32",
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const base = [
  "--workspace", "@dotacni-majak/api", "exec", "--",
  "wrangler", "d1",
];

run("npm", [
  ...base,
  "migrations", "apply", "dotacni-majak-local",
  "--local", "--persist-to", "../../.wrangler/e2e",
]);

run("npm", [
  ...base,
  "execute", "dotacni-majak-local",
  "--local", "--persist-to", "../../.wrangler/e2e",
  "--file", "../../tests/e2e/seed.sql",
]);

console.log("E2E_D1_READY");
