import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "demo-mode.spec.ts",
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:4174/litegate/",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command:
      "npx vite build --base=/litegate/ && npx vite preview --host 127.0.0.1 --port 4174 --base=/litegate/",
    url: "http://127.0.0.1:4174/litegate/",
    reuseExistingServer: !process.env.CI,
    env: { ...process.env, VITE_DEMO_MODE: "true" },
  },
});
