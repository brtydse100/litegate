import { expect, test } from "@playwright/test";

test("@smoke My key guidance remains below actions after creation", async ({
  page,
}) => {
  const message = 'Keep your key private.\n<img src=x onerror="alert(1)">';
  let created = false;
  let regenerated = false;
  await page.setViewportSize({ width: 375, height: 812 });
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path === "/api/auth/me") {
      body = {
        user_id: "owner",
        role: "user",
        email: "owner@example.com",
        team_ids: [],
      };
    } else if (path === "/api/portal-config") {
      body = { my_key_text: message, save_api_keys_in_db: false };
    } else if (path === "/api/keys/operation-limit") {
      body = { limit: 5, remaining: 5, retry_after: 0 };
    } else if (path === "/api/keys/regenerate") {
      regenerated = true;
      body = { key: "sk-synthetic-regenerated", user_id: "owner" };
    } else if (path === "/api/keys") {
      if (route.request().method() === "POST") {
        created = true;
        body = { key: "sk-synthetic-guidance", user_id: "owner" };
      } else {
        body = {
          keys: created
            ? [
                {
                  token: regenerated ? "hashed-regenerated" : "hashed-guidance",
                  spend: 0,
                  models: [],
                },
              ]
            : [],
        };
      }
    }
    await route.fulfill({ json: body });
  });
  await page.goto("/my-key");
  const guidance = page.getByLabel("My key guidance");
  const create = page.getByRole("button", { name: "Create API key" });
  await expect(guidance).toHaveText(message);
  await expect(guidance.locator("img")).toHaveCount(0);
  expect((await guidance.boundingBox())!.y).toBeGreaterThan(
    (await create.boundingBox())!.y,
  );
  await create.click();
  await expect(
    page.getByText("sk-synthetic-guidance", { exact: true }),
  ).toBeVisible();
  const regenerate = page.getByRole("button", { name: "Regenerate key" });
  const hide = page.getByRole("button", { name: "Hide API key" });
  await expect(hide).toHaveCount(1);
  await expect(regenerate).toHaveCount(0);
  await expect(guidance).toHaveText(message);
  expect((await guidance.boundingBox())!.y).toBeGreaterThan(
    (await hide.boundingBox())!.y,
  );
  await hide.click();
  await expect(
    page.getByText("sk-synthetic-guidance", { exact: true }),
  ).toHaveCount(0);
  await expect(regenerate).toBeVisible();
  await regenerate.click();
  await page.getByRole("button", { name: "Replace key", exact: true }).click();
  await expect(
    page.getByText("sk-synthetic-regenerated", { exact: true }),
  ).toBeVisible();
  await expect(hide).toHaveCount(1);
  await expect(regenerate).toHaveCount(0);
  await expect(guidance).toHaveText(message);
  await hide.click();
  await expect(
    page.getByText("sk-synthetic-regenerated", { exact: true }),
  ).toHaveCount(0);
  await expect(regenerate).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
