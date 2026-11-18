import { defineConfig } from "@playwright/test";
import base from "./playwright.sso.config";

// The real-SSO harness with enforced organization budgets, for restarts that
// lose the database (a deployment without persistent storage).
const extra = {
  HIERARCHICAL_BUDGETS_ENABLED: "true",
  HIERARCHICAL_BUDGETS_ENFORCED: "true",
};

export default defineConfig({
  ...base,
  testMatch: [
    "sso-restart.spec.ts",
    "sso-budget-authority.spec.ts",
    "sso-large-org.spec.ts",
  ],
  webServer: (Array.isArray(base.webServer) ? base.webServer : []).map(
    (server) => ({ ...server, env: { ...server.env, ...extra } }),
  ),
});
