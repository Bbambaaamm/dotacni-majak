import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "core-flow.spec.ts",
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command:
        "node scripts/e2e_prepare.mjs && npm --workspace @dotacni-majak/api run dev:e2e",
      url: "http://127.0.0.1:8787/ready",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npm --workspace @dotacni-majak/web run dev:e2e",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
