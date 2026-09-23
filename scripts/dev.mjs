import { spawn } from "node:child_process";

const children = [
  spawn("npm", ["run", "dev:api"], {
    stdio: "inherit",
    shell: true,
  }),
  spawn("npm", ["run", "dev:web"], {
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
