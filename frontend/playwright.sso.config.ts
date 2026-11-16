import { defineConfig, devices } from "@playwright/test";

const environment = {
  ...process.env,
  LITELLM_URL: process.env.LITELLM_URL ?? "http://127.0.0.1:4001",
  LITELLM_MASTER_KEY: "sk-litegate-integration-master",
  JWT_SECRET: "litegate-sso-test-jwt-secret-at-least-32-characters",
  MANAGEMENT_API_KEY: "litegate-sso-test-management-key-at-least-32-characters",
  LOCAL_USERS_ENABLED: "false",
  LOCAL_AUTH_USERNAME: "",
  LOCAL_AUTH_PASSWORD: "",
  LOCAL_USERS_DB_PATH: "../backend/data/litegate-sso-test.db",
  ROOT_URL: "http://127.0.0.1:4176",
  CORS_ORIGINS: "http://127.0.0.1:4176",
  OIDC_ISSUER_URL: "http://127.0.0.1:8082/realms/litegate-sso",
  OIDC_CLIENT_ID: "litegate-sso-test",
  OIDC_CLIENT_SECRET: "litegate-sso-test-client-secret",
  OIDC_REDIRECT_URI: "http://127.0.0.1:4176/api/auth/callback",
  ADMIN_GROUPS: "system-admins",
  ADMIN_EMAILS: "",
  SAVE_API_KEYS_IN_DB: "true",
  ANALYTICS_ENABLED: "true",
  ORGANIZATION_HIERARCHY_FILE: "../deploy/docker-compose/sso/organization.json",
  ORGANIZATION_ACCESS_DESIGNATIONS: JSON.stringify({
    "10000000-0000-4000-8000-000000000002": ["sso-test-engineering"],
    "10000000-0000-4000-8000-000000000003": ["sso-test-platform"],
    "10000000-0000-4000-8000-000000000007": ["sso-test-engineering"],
  }),
  ORGANIZATION_GROUP_ADMINS: JSON.stringify({
    "sso-test-engineering": [
      "10000000-0000-4000-8000-000000000002",
      "10000000-0000-4000-8000-000000000008",
    ],
    "sso-test-platform": ["10000000-0000-4000-8000-000000000003"],
  }),
};

export default defineConfig({
  testDir: "./e2e",
  testMatch: "sso-integration.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4176",
    // Traces can contain authorization codes and newly created test keys.
    trace: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "python ../scripts/run_sso_backend.py",
      url: "http://127.0.0.1:8000/api/health/ready",
      reuseExistingServer: false,
      timeout: 120_000,
      env: environment,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4176",
      url: "http://127.0.0.1:4176",
      reuseExistingServer: false,
      env: environment,
    },
  ],
});
