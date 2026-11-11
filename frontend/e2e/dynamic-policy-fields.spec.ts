import { expect, test, type Page } from "@playwright/test";

async function setup(page: Page) {
  let discoveries = 0;
  let submitted: unknown;
  const mcp = {
    anyOf: [
      { type: "object", additionalProperties: { type: "integer", minimum: 0 } },
      { type: "null" },
    ],
  };
  const schemas = {
    key_update: {
      properties: {
        max_parallel_requests: { type: "integer", minimum: 1 },
        mcp_rpm_limit: mcp,
      },
    },
    team_create: {
      properties: {
        team_member_budget: { type: "number", minimum: 0 },
        mcp_rpm_limit: mcp,
      },
    },
    team_update: { properties: {} },
  };
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};
    if (path === "/api/auth/me")
      data = {
        user_id: "admin",
        email: "admin@example.invalid",
        role: "admin",
        auth_source: "local",
        team_ids: [],
      };
    if (path === "/api/portal-config")
      data = { litellm_enterprise_enabled: true, local_users_enabled: true };
    if (path === "/api/keys/operation-limit")
      data = { limit: 5, remaining: 5, retry_after: 0 };
    if (path === "/api/keys") data = { keys: [] };
    if (path === "/api/v1/keys")
      data = {
        keys: [
          {
            token: "key-1",
            key_alias: "Synthetic",
            spend: 0,
            max_budget: 100,
            models: [],
          },
        ],
        page: 1,
        total: 1,
        size: 25,
        total_pages: 1,
      };
    if (path === "/api/v1/models") data = { models: ["test-opus"] };
    if (path === "/api/v1/policy-schemas") {
      discoveries += 1;
      data = { available: true, schemas };
    }
    if (path === "/api/v1/teams") {
      data = { teams: [], total: 0, page: 1, page_size: 25, total_pages: 1 };
      if (route.request().method() === "POST") {
        submitted = route.request().postDataJSON();
        data = {
          team_id: "new-team",
          team_alias: "Synthetic",
          models: [],
          members_with_roles: [],
          mapped_groups: [],
          default_key_team: false,
          members_count: 0,
          keys_count: 0,
          blocked: false,
        };
      }
    }
    if (path === "/api/v1/keys/bulk") {
      submitted = route.request().postDataJSON();
      data = {
        updated: 1,
        failed: 0,
        results: [{ key: "key-1", updated: true }],
      };
    }
    await route.fulfill({ json: data });
  });
  return { discoveries: () => discoveries, submitted: () => submitted };
}

test("key editor discovers Advanced MCP fields only when opened @smoke", async ({
  page,
}) => {
  const state = await setup(page);
  await page.goto("/keys");
  await page
    .getByRole("checkbox", { name: "Select Synthetic" })
    .locator("..")
    .click();
  expect(state.discoveries()).toBe(0);
  await page.getByText("Advanced settings", { exact: true }).click();
  await page.getByLabel("Edit max_parallel_requests", { exact: true }).check();
  await page.getByLabel("max_parallel_requests", { exact: true }).fill("3");
  await page.getByLabel("Edit mcp_rpm_limit", { exact: true }).check();
  await page
    .getByLabel("mcp_rpm_limit", { exact: true })
    .fill('{"synthetic-mcp":9}');
  await page
    .getByRole("checkbox", { name: "Replace per-model budgets" })
    .check();
  await page.getByRole("button", { name: "Add model budget" }).click();
  await page.getByLabel("Budget model 1", { exact: true }).fill("test-opus");
  await page.getByLabel("Model budget 1 (USD)").fill("25");
  await page.getByLabel("Model reset period 1").fill("2h");
  await page
    .getByRole("button", { name: "Apply settings to 1 key", exact: true })
    .click();
  await expect.poll(state.submitted).toEqual({
    keys: ["key-1"],
    settings: {
      advanced_settings: {
        max_parallel_requests: 3,
        mcp_rpm_limit: { "synthetic-mcp": 9 },
      },
      model_max_budget: {
        "test-opus": { budget_limit: 25, time_period: "2h" },
      },
    },
  });
  expect(state.discoveries()).toBe(1);
});

test("team creation submits discovered member budgets and MCP settings @smoke", async ({
  page,
}) => {
  const state = await setup(page);
  await page.goto("/teams");
  await page.getByRole("button", { name: "Create team", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Create team" });
  await dialog.getByLabel("Team name", { exact: true }).fill("Synthetic");
  expect(state.discoveries()).toBe(0);
  await dialog.getByText("Advanced settings", { exact: true }).click();
  await dialog.getByLabel("Edit team_member_budget", { exact: true }).check();
  await dialog.getByLabel("team_member_budget", { exact: true }).fill("20");
  await dialog.getByLabel("Edit mcp_rpm_limit", { exact: true }).check();
  await dialog
    .getByLabel("mcp_rpm_limit", { exact: true })
    .fill('{"synthetic-mcp":5}');
  await dialog
    .getByRole("button", { name: "Create team", exact: true })
    .click();
  await expect.poll(state.submitted).toMatchObject({
    team_alias: "Synthetic",
    advanced_settings: {
      team_member_budget: 20,
      mcp_rpm_limit: { "synthetic-mcp": 5 },
    },
  });
});
