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

test("administrator can create, edit, move a member, and delete a team", async ({ page }) => {
  const team = (team_id: string, team_alias: string, members_with_roles: Array<{ user_id: string; user_email: string; role: "user" | "admin" }> = []) => ({
    team_id,
    team_alias,
    spend: 0,
    max_budget: null,
    budget_duration: null,
    tpm_limit: null,
    rpm_limit: null,
    models: [],
    blocked: false,
    members_count: members_with_roles.length,
    keys_count: 0,
    members_with_roles,
    mapped_groups: [],
    default_key_team: false,
  });
  let teams = [
    team("team-source", "Source", [{ user_id: "alice", user_email: "alice@example.com", role: "user" }]),
    team("team-destination", "Destination"),
  ];
  let movePayload: unknown;

  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    let body: unknown = {};
    let status = 200;
    if (url.pathname === "/api/auth/me") body = { user_id: "admin", email: "admin@example.com", role: "admin", auth_source: "local", team_ids: [] };
    else if (url.pathname === "/api/portal-config") body = { support_ticket_url: "", logo_url: "", litellm_ui_url: "", api_docs_url: "/api/docs" };
    else if (url.pathname === "/api/keys/operation-limit") body = { limit: 5, remaining: 5, retry_after: 0 };
    else if (url.pathname === "/api/keys") body = { keys: [] };
    else if (url.pathname === "/api/v1/teams" && method === "GET") body = { teams, total: teams.length, page: 1, page_size: 25, total_pages: 1 };
    else if (url.pathname === "/api/v1/teams" && method === "POST") {
      const payload = route.request().postDataJSON();
      const created = { ...team(payload.team_id || "generated-team", payload.team_alias), ...payload };
      teams = [...teams, created];
      body = created;
      status = 201;
    } else if (url.pathname.startsWith("/api/v1/teams/") && method === "PATCH") {
      const id = decodeURIComponent(url.pathname.split("/").at(-1)!);
      const payload = route.request().postDataJSON();
      teams = teams.map(item => item.team_id === id ? { ...item, ...payload } : item);
      body = teams.find(item => item.team_id === id);
    } else if (url.pathname === "/api/v1/teams/team-source/members/move" && method === "POST") {
      movePayload = route.request().postDataJSON();
      teams = teams.map(item => item.team_id === "team-source" ? { ...item, members_count: 0, members_with_roles: [] } : item);
      body = { moved: true, user_id: "alice", source_team_id: "team-source", destination_team_id: "team-destination", keys_moved: 1, destination_membership_existed: false };
    } else if (url.pathname.startsWith("/api/v1/teams/") && method === "DELETE") {
      const id = decodeURIComponent(url.pathname.split("/").at(-1)!);
      teams = teams.filter(item => item.team_id !== id);
      body = { deleted: true, team_id: id };
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.goto("/teams");
  await expect(page.getByRole("heading", { name: "LiteLLM team policy" })).toBeVisible();

  await page.getByRole("button", { name: "Create team" }).click();
  const createDialog = page.getByRole("dialog", { name: "Create team" });
  await createDialog.getByLabel("Team name").fill("Research");
  await createDialog.getByLabel(/Team ID/).fill("team-research");
  await createDialog.getByRole("button", { name: "Create team" }).click();
  await expect(page.getByRole("heading", { name: "Research" })).toBeVisible();

  const research = page.locator("article").filter({ hasText: "Research" });
  await research.getByRole("button", { name: "Edit" }).click();
  const editDialog = page.getByRole("dialog", { name: "Edit team" });
  await editDialog.getByLabel("Maximum budget (USD)").fill("50");
  await editDialog.getByRole("button", { name: "Save changes" }).click();
  await expect(research.getByText("$50")).toBeVisible();

  await page.locator("article").filter({ hasText: "Source" }).getByRole("button", { name: "Members" }).click();
  const members = page.getByRole("dialog", { name: "Members of Source" });
  await members.getByRole("button", { name: "Move" }).click();
  await members.getByRole("combobox", { name: /Destination team/ }).selectOption("team-destination");
  await members.getByRole("checkbox").check();
  await members.getByRole("button", { name: "Move user and keys" }).click();
  await expect(members).toBeHidden();
  expect(movePayload).toEqual({ user_id: "alice", destination_team_id: "team-destination", confirm_policy_change: true });

  await research.getByRole("button", { name: "Delete" }).click();
  const deleteDialog = page.getByRole("dialog", { name: "Delete Research?" });
  await deleteDialog.getByLabel(/Type team-research/).fill("team-research");
  await deleteDialog.getByRole("button", { name: "Delete team and keys" }).click();
  await expect(page.getByRole("heading", { name: "Research" })).toHaveCount(0);
});

test("administrator can manage a local account without leaving the users page", async ({ page }) => {
  let users: Array<{ username: string; user_id: string; email: string; role: "user" | "admin"; active: boolean; created_at: string; updated_at: string }> = [];
  const updates: unknown[] = [];
  await page.route(/^https?:\/\/[^/]+\/api\//, async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    let body: unknown = {};
    let status = 200;
    if (url.pathname === "/api/auth/me") body = { user_id: "admin", email: "admin@example.com", role: "admin", auth_source: "local", team_ids: [] };
    else if (url.pathname === "/api/portal-config") body = { support_ticket_url: "", logo_url: "", litellm_ui_url: "", api_docs_url: "/api/docs" };
    else if (url.pathname === "/api/keys/operation-limit") body = { limit: 5, remaining: 5, retry_after: 0 };
    else if (url.pathname === "/api/keys") body = { keys: [] };
    else if (url.pathname === "/api/v1/users" && method === "GET") body = users;
    else if (url.pathname === "/api/v1/users" && method === "POST") {
      const payload = route.request().postDataJSON();
      const created = { ...payload, user_id: `local:${payload.username}`, active: true, created_at: "2026-08-22T00:00:00Z", updated_at: "2026-08-22T00:00:00Z" };
      users = [created];
      body = created;
      status = 201;
    } else if (url.pathname === "/api/v1/users/contractor" && method === "PATCH") {
      const payload = route.request().postDataJSON();
      updates.push(payload);
      users = users.map(user => ({ ...user, ...payload }));
      body = users[0];
    }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.goto("/users");
  await page.getByLabel("Username").fill("contractor");
  await page.getByLabel("Email").fill("contractor@example.com");
  await page.getByLabel("Temporary password").fill("temporary-password");
  await page.getByRole("button", { name: "Add user" }).click();
  await expect(page.getByText("contractor@example.com")).toBeVisible();

  await page.getByRole("button", { name: "Make admin" }).click();
  await expect(page.getByRole("button", { name: "Make user" })).toBeVisible();
  await page.getByRole("button", { name: "Disable" }).click();
  await expect(page.getByRole("button", { name: "Enable" })).toBeVisible();
  await page.getByRole("button", { name: "Reset password" }).click();
  const reset = page.getByRole("dialog", { name: "Reset contractor's password" });
  await reset.getByLabel("New password").fill("replacement-password");
  await reset.getByRole("button", { name: "Reset password" }).click();
  await expect(reset).toBeHidden();

  expect(updates).toEqual([
    { role: "admin" },
    { active: false },
    { password: "replacement-password" },
  ]);
});
