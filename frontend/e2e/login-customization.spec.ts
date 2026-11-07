import { expect, test, type Page } from "@playwright/test";

async function mockLoginConfig(page: Page, loginText: string, logoUrl: string) {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ status: 401, json: { detail: "Not signed in" } }),
  );
  await page.route("**/api/auth/config", (route) =>
    route.fulfill({
      json: {
        sso_enabled: true,
        local_enabled: true,
        login_text: loginText,
        logo_url: logoUrl,
      },
    }),
  );
}

test("@smoke login shows the shared logo and escapes custom text on mobile", async ({
  page,
}) => {
  const loginText = 'Welcome to Example\n<img src=x onerror="alert(1)">';
  await page.setViewportSize({ width: 375, height: 812 });
  await mockLoginConfig(page, loginText, "/example-logo.svg");
  await page.route("**/example-logo.svg", (route) =>
    route.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="44"><rect width="320" height="44" fill="indigo"/></svg>',
    }),
  );

  await page.goto("/login");

  const logo = page.getByRole("img", { name: "Organization logo" });
  await expect(logo).toBeVisible();
  await expect(logo).toHaveAttribute("src", "/example-logo.svg");
  await expect(logo).toHaveJSProperty("naturalWidth", 320);
  await expect(page.getByText("Welcome to Example")).toHaveText(loginText);
  await expect(page.locator("img")).toHaveCount(1);
  await expect(
    page.getByRole("link", { name: "Sign in with SSO" }),
  ).toHaveAttribute("href", "/api/auth/login");
  await expect(page.getByRole("textbox", { name: "Username" })).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
  const logoBounds = await logo.boundingBox();
  expect(logoBounds!.x + logoBounds!.width).toBeLessThanOrEqual(375);
});

test("@smoke blank login customization preserves the default page", async ({
  page,
}) => {
  await mockLoginConfig(page, "", "");

  await page.goto("/login");

  await expect(page.getByRole("textbox", { name: "Username" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "LiteGate" })).toBeVisible();
  await expect(
    page.getByText("Sign in to your LiteLLM access portal"),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "Organization logo" }),
  ).toHaveCount(0);
  await expect(page.locator("polygon")).toBeVisible();
});
