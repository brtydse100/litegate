import { expect, test, type Page } from "@playwright/test";

const keyPage = {
  keys: [
    { token: "key-1", key_alias: "Alice", spend: 1, models: [], user_id: "alice" },
    { token: "key-2", key_alias: "Bob", spend: 2, models: [], user_id: "bob" },
  ],
  page: 1,
  size: 25,
  total: 2,
  total_pages: 1,
};

async function mockApi(page: Page, role: "admin" | "user") {
  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const url = new URL(route.request().url());
    let body: unknown = {};
    if (url.pathname === "/api/auth/me") body = { user_id: role, email: `${role}@example.com`, role, auth_source: "local", team_ids: [] };
    else if (url.pathname === "/api/portal-config") body = { support_ticket_url: "", logo_url: "", litellm_ui_url: "", api_docs_url: "/api/docs" };
    else if (url.pathname === "/api/keys/operation-limit") body = { limit: 5, remaining: 5, retry_after: 0 };
    else if (url.pathname === "/api/keys") body = { keys: [] };
    else if (url.pathname === "/api/v1/users") body = [];
    else if (url.pathname === "/api/v1/keys/identifiers") body = { keys: ["key-1", "key-2"], total: 2 };
    else if (url.pathname === "/api/v1/keys") body = keyPage;
    // Keep the older response shape: optional fields added by a newer backend
    // must not crash the frontend during a rolling upgrade.
    else if (url.pathname === "/api/v1/status") body = { ready: true, dependencies: { litellm: { ok: true, detail: "Connected" }, database: { ok: true, detail: "Writable" } }, storage_mode: "sqlite-single-replica" };
    else if (url.pathname === "/api/v1/audit-events") body = { events: [] };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

test("administrator navigation has stable routes and global selection", async ({ page }) => {
  await mockApi(page, "admin");
  await page.goto("/keys");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("token"))).toBeNull();
  await expect(page).toHaveURL(/\/keys$/);
  await expect(page.getByRole("heading", { name: "Key policies" })).toBeVisible();
  await page.getByRole("button", { name: "Select all keys (2)" }).click();
  await expect(page.getByText("2 selected").first()).toBeVisible();
  await page.getByRole("link", { name: "Status" }).click();
  await expect(page).toHaveURL(/\/status$/);
  await expect(page.getByText("LiteGate is ready to serve requests.")).toBeVisible();

  const usersRequest = page.waitForRequest(request => new URL(request.url()).pathname === "/api/v1/users");
  await page.getByRole("link", { name: "Local users" }).click();
  await usersRequest;
  await expect(page.getByRole("heading", { name: "Local user access" })).toBeVisible();
});

test("normal users cannot open administrator routes", async ({ page }) => {
  await mockApi(page, "user");
  await page.goto("/keys");
  await expect(page).toHaveURL(/\/my-key$/);
  await expect(page.getByRole("heading", { name: "Your API access" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Local users" })).toHaveCount(0);
});
