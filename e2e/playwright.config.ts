import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: "http://localhost:5199",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "cd app && pnpm dev",
    port: 5199,
    reuseExistingServer: true,
    timeout: 30000,
  },
});
