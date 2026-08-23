import { defineConfig, devices } from "@playwright/test";

const integrationEnvironment = {
  ...process.env,
  LITELLM_URL: process.env.LITELLM_URL ?? "http://127.0.0.1:4000",
  LITELLM_MASTER_KEY: "sk-litegate-integration-master",
  JWT_SECRET: "litegate-integration-jwt-secret-at-least-32-characters",
  MANAGEMENT_API_KEY: "litegate-integration-management-key",
  LOCAL_AUTH_USERNAME: "integration-admin",
  LOCAL_AUTH_PASSWORD: "litegate-integration-password",
  LOCAL_USERS_DB_PATH: "../backend/data/litegate-integration.db",
  ROOT_URL: "http://127.0.0.1:4175",
  CORS_ORIGINS: "http://127.0.0.1:4175",
};

export default defineConfig({
  testDir: "./e2e",
  testMatch: "litellm-integration.spec.ts",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:4175",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        "python -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/api/health/ready",
      reuseExistingServer: false,
      timeout: 120_000,
      env: integrationEnvironment,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4175",
      url: "http://127.0.0.1:4175",
      reuseExistingServer: false,
      timeout: 30_000,
      env: integrationEnvironment,
    },
  ],
});
