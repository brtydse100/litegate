import { expect, test } from "@playwright/test";

test("key policies use one scrollbar and edit budgets with 5000 selected keys @smoke", async ({
  page,
}) => {
  const identifiers = Array.from(
    { length: 5000 },
    (_, index) => `key-${index}`,
  );
  const models = Array.from({ length: 80 }, (_, index) => `model-${index}`);
  let update: unknown;
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};
    if (path === "/api/auth/me")
      data = {
        user_id: "admin",
        email: "admin@example.com",
        role: "admin",
        auth_source: "local",
        team_ids: [],
      };
    if (path === "/api/portal-config")
      data = { litellm_enterprise_enabled: true, local_users_enabled: true };
    if (path === "/api/keys") data = { keys: [] };
    if (path === "/api/keys/operation-limit")
      data = { limit: 5, remaining: 5, retry_after: 0 };
    if (path === "/api/v1/models") data = { models };
    if (path === "/api/v1/keys/identifiers")
      data = { keys: identifiers, total: identifiers.length };
    if (path === "/api/v1/keys")
      data = {
        keys: identifiers
          .slice(0, 25)
          .map((token) => ({ token, key_alias: token, spend: 0, models })),
        page: 1,
        size: 25,
        total: 5000,
        total_pages: 200,
      };
    if (path === "/api/v1/keys/bulk") {
      update = route.request().postDataJSON();
      data = { updated: 5000, failed: 0, results: [] };
    }
    await route.fulfill({ json: data });
  });
  await page.goto("/keys");
  await page.getByRole("button", { name: "Select all keys (5000)" }).click();
  await expect(
    page.getByRole("button", { name: "Deselect all (5000)" }),
  ).toBeVisible();
  await page.getByLabel("Alias", { exact: true }).fill("Updated policy");
  await page
    .getByRole("checkbox", { name: "Replace per-model budgets" })
    .check();
  await page.getByRole("button", { name: "Add model budget" }).click();
  await page.getByLabel("Budget model 1", { exact: true }).fill("model-0");
  await page.getByLabel("Model budget 1 (USD)").fill("25");
  await page.getByLabel("Model reset period 1").fill("2h");

  const scrollAreas = await page.locator("main").evaluate((main) =>
    [main, ...main.querySelectorAll("*")]
      .filter((element) => {
        const style = getComputedStyle(element);
        return (
          ["auto", "scroll"].includes(style.overflowY) &&
          element.scrollHeight > element.clientHeight
        );
      })
      .map((element) => element.tagName),
  );
  expect(scrollAreas).toEqual(["MAIN"]);
  await page
    .getByRole("button", { name: "Apply settings to 5000 keys" })
    .click();
  await expect
    .poll(() => update)
    .toEqual({
      keys: identifiers,
      settings: {
        key_alias: "Updated policy",
        model_max_budget: {
          "model-0": { budget_limit: 25, time_period: "2h" },
        },
      },
    });
});
