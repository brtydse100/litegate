import { expect, test } from "@playwright/test";

test("interactive demo keeps its key views consistent and supports local sign-in", async ({
  page,
}) => {
  await page.goto("./");
  await expect(
    page.getByRole("heading", { name: "Your API access" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Regenerate key" }).click();
  await page.getByRole("button", { name: "Replace key" }).click();
  await expect(page.getByText("sk-litegate-demo-rotated-4d8e")).toBeVisible();
  await page.getByRole("button", { name: "Dismiss" }).click();

  await page.getByRole("link", { name: "Key policies" }).click();
  await expect(
    page.getByRole("heading", { name: "Key policies" }),
  ).toBeVisible();
  await expect(page.getByText("sk-litega....4d8e")).toBeVisible();
  await expect(page.getByText("sk-litega....7f3a")).toHaveCount(0);

  await page.getByRole("link", { name: "Teams" }).click();
  await expect(
    page.getByRole("heading", { name: "LiteLLM team policy" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/litegate\/login$/);
  await expect(
    page.getByRole("link", { name: "Sign in with SSO" }),
  ).toHaveCount(0);

  await page.getByLabel("Username").fill("demo");
  await page.getByLabel("Password").fill("demo-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/litegate\/my-key$/);
  await expect(
    page.getByRole("heading", { name: "Your API access" }),
  ).toBeVisible();
});
