import { expect, test, type Page } from "@playwright/test";
import { access, writeFile } from "node:fs/promises";

// Real Keycloak, real LiteLLM 1.109.1 and the real backend with enforced
// organization budgets. Restarts here delete the database, like a deployment
// without persistent storage.
const origin = "http://127.0.0.1:4176";
const upstreamOrigin = process.env.LITELLM_URL ?? "http://127.0.0.1:4001";
const master = "sk-litegate-integration-master";
const password = "litegate-sso-test-password";
const marker = "../backend/data/litegate-sso-test.restart";
const mutationHeaders = { Origin: origin };

async function login(page: Page, username: string) {
  await page.goto("/api/auth/login");
  await expect(page).toHaveURL(/127\.0\.0\.1:8082\/realms\/litegate-sso\//);
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.locator("#kc-login").click();
  await expect(page).toHaveURL(/127\.0\.0\.1:4176\/(?:my-key)?$/, {
    timeout: 30_000,
  });
}

async function restartBackend(mode: "wipe" | "restart") {
  await writeFile(marker, mode);
  await expect
    .poll(
      async () => {
        try {
          await access(marker);
          return false;
        } catch {
          return true;
        }
      },
      { timeout: 60_000 },
    )
    .toBe(true);
}

async function saveRootBudget(page: Page, team: string, amount: string) {
  await page.goto("/organization");
  const input = page.getByLabel(`${team} assigned budget`);
  await input.fill(amount);
  await page.getByRole("button", { name: `Save ${team} budget` }).click();
  await expect(input).toHaveValue(amount);
  const editor = page.locator("article", { has: input });
  await expect(editor.getByRole("alert")).toHaveCount(0);
}

test("two team budgets saved across restarts without persistence never break the key page", async ({
  browser,
}) => {
  // Two restarts plus one 60-second reconciliation pass.
  test.setTimeout(300_000);
  const adminContext = await browser.newContext({ baseURL: origin });
  const userContext = await browser.newContext({ baseURL: origin });
  const admin = await adminContext.newPage();
  const user = await userContext.newPage();
  let secret = "";
  try {
    await login(admin, "system-admin");
    await login(user, "ordinary-user");
    // A fresh signed-in member with one key in Engineering.
    for (const old of (await (await user.request.get("/api/keys")).json())
      .keys) {
      await user.request.post(`${upstreamOrigin}/key/delete`, {
        headers: { Authorization: `Bearer ${master}` },
        data: { keys: [old.token] },
      });
    }
    const created = await user.request.post("/api/keys", {
      headers: mutationHeaders,
    });
    expect(created.status()).toBe(201);
    secret = (await created.json()).key;

    // Team 1 budget, then a restart that loses the database.
    await saveRootBudget(admin, "Engineering", "80");
    await restartBackend("wipe");

    // Team 2 budget after the restart: the save succeeds.
    await saveRootBudget(admin, "Marketing", "60");
    await restartBackend("wipe");
    await saveRootBudget(admin, "Engineering", "90");

    // The member's surviving session sees one calm info message and no warnings.
    await user.goto("/my-key");
    const notice = user.getByText(
      "Sign out and sign in again to restore your organization details.",
      { exact: false },
    );
    await expect(notice).toBeVisible();
    await expect(user.getByRole("alert")).toHaveCount(0);
    await expect(user.getByText(/Policy unavailable/)).toHaveCount(0);
    await expect(user.getByText(/mapping was removed/)).toHaveCount(0);
    await expect(user.getByText(/Key status:/)).toHaveCount(0);
    await expect(
      user.getByRole("button", { name: "Regenerate key" }),
    ).toBeVisible();
    // Until they sign in again LiteGate cannot tell which team the new key
    // belongs to, so replacement asks for that and changes nothing.
    const early = await user.request.post("/api/keys/regenerate", {
      headers: mutationHeaders,
    });
    expect(early.status()).toBe(409);
    expect((await early.json()).detail).toMatch(/sign in again/i);

    // The message closes with its ×.
    await user
      .getByRole("status")
      .filter({ has: notice })
      .getByRole("button", { name: "Dismiss message" })
      .click();
    await expect(notice).toHaveCount(0);

    // Signing in again restores the organization details: no notice remains,
    // and the enforced Engineering budget is applied to the key.
    await userContext.clearCookies();
    await login(user, "ordinary-user");
    await user.goto("/my-key");
    await expect(user.getByText(/Assigned through/)).toBeVisible();
    await expect(
      user.getByText(/Sign out and sign in again/, { exact: false }),
    ).toHaveCount(0);
    await expect(user.getByRole("alert")).toHaveCount(0);
    await expect
      .poll(
        async () =>
          (await (await user.request.get("/api/keys")).json()).keys[0]
            .user_budget,
        { timeout: 150_000, intervals: [5_000] },
      )
      .toBeGreaterThan(0);

    // The original credential kept working throughout (the refused
    // replacement above did not pause it).
    const inference = await user.request.post(
      `${upstreamOrigin}/v1/chat/completions`,
      {
        headers: { Authorization: `Bearer ${secret}` },
        data: {
          model: "litegate-integration-mock",
          messages: [{ role: "user", content: "Synthetic restart check" }],
        },
      },
    );
    expect(inference.status()).toBe(200);
  } finally {
    if (secret) {
      await user.request.post(`${upstreamOrigin}/key/delete`, {
        headers: { Authorization: `Bearer ${master}` },
        data: { keys: [secret] },
      });
    }
    await adminContext.close();
    await userContext.close();
  }
});

test("with persistent storage a restart keeps team budgets and shows no messages", async ({
  browser,
}) => {
  test.setTimeout(180_000);
  const adminContext = await browser.newContext({ baseURL: origin });
  const userContext = await browser.newContext({ baseURL: origin });
  const admin = await adminContext.newPage();
  const user = await userContext.newPage();
  let secret = "";
  try {
    await login(admin, "system-admin");
    await login(user, "ordinary-user");
    for (const old of (await (await user.request.get("/api/keys")).json())
      .keys) {
      await user.request.post(`${upstreamOrigin}/key/delete`, {
        headers: { Authorization: `Bearer ${master}` },
        data: { keys: [old.token] },
      });
    }
    const created = await user.request.post("/api/keys", {
      headers: mutationHeaders,
    });
    expect(created.status()).toBe(201);
    secret = (await created.json()).key;
    await saveRootBudget(admin, "Engineering", "70");
    await saveRootBudget(admin, "Marketing", "50");
    await restartBackend("restart");

    await admin.goto("/organization");
    await expect(admin.getByLabel("Engineering assigned budget")).toHaveValue(
      "70",
    );
    await expect(admin.getByLabel("Marketing assigned budget")).toHaveValue(
      "50",
    );
    await user.goto("/my-key");
    await expect(user.getByText(/Assigned through/)).toBeVisible();
    await expect(user.getByRole("alert")).toHaveCount(0);
    await expect(
      user.getByText(/Sign out and sign in again/, { exact: false }),
    ).toHaveCount(0);
    await expect(user.getByText(/Key status:/)).toHaveCount(0);
    // The saved copy survived: the page shows it again (it reveals saved keys
    // on load) and offers no replacement.
    await expect(
      user.getByRole("button", { name: /Show API key|Hide API key/ }),
    ).toBeVisible();
    await expect(
      user.getByRole("button", { name: /Regenerate key/ }),
    ).toHaveCount(0);
  } finally {
    if (secret) {
      await user.request.post(`${upstreamOrigin}/key/delete`, {
        headers: { Authorization: `Bearer ${master}` },
        data: { keys: [secret] },
      });
    }
    await adminContext.close();
    await userContext.close();
  }
});

// Keycloak's administration API moves a synthetic user between SSO groups.
const keycloak = "http://127.0.0.1:8082";
async function setGroups(page: Page, userId: string, groups: string[]) {
  const login = await page.request.post(
    `${keycloak}/realms/master/protocol/openid-connect/token`,
    {
      form: {
        grant_type: "password",
        client_id: "admin-cli",
        username: "litegate-test-admin",
        password: "litegate-test-admin-password",
      },
    },
  );
  expect(login.status()).toBe(200);
  const headers = {
    Authorization: `Bearer ${(await login.json()).access_token}`,
  };
  const admin = `${keycloak}/admin/realms/litegate-sso`;
  const all: { id: string; name: string }[] = await (
    await page.request.get(`${admin}/groups`, { headers })
  ).json();
  const current: { id: string; name: string }[] = await (
    await page.request.get(`${admin}/users/${userId}/groups`, { headers })
  ).json();
  for (const group of current.filter((g) => !groups.includes(g.name)))
    await page.request.delete(`${admin}/users/${userId}/groups/${group.id}`, {
      headers,
    });
  for (const group of all.filter((g) => groups.includes(g.name)))
    await page.request.put(`${admin}/users/${userId}/groups/${group.id}`, {
      headers,
    });
}

test("a member moved to another team regenerates their key after a restart without persistence", async ({
  browser,
}) => {
  test.setTimeout(240_000);
  const userId = "10000000-0000-4000-8000-000000000004";
  const context = await browser.newContext({ baseURL: origin });
  const user = await context.newPage();
  const created: string[] = [];
  try {
    await login(user, "ordinary-user");
    for (const old of (await (await user.request.get("/api/keys")).json())
      .keys) {
      await user.request.post(`${upstreamOrigin}/key/delete`, {
        headers: { Authorization: `Bearer ${master}` },
        data: { keys: [old.token] },
      });
    }
    const first = await user.request.post("/api/keys", {
      headers: mutationHeaders,
    });
    expect(first.status()).toBe(201);
    const oldSecret: string = (await first.json()).key;
    created.push(oldSecret);
    // Usage already consumed on the old key must follow the member.
    await user.request.post(`${upstreamOrigin}/key/update`, {
      headers: { Authorization: `Bearer ${master}` },
      data: { key: oldSecret, spend: 0.25 },
    });

    // The member moves to Marketing; the backend restarts and loses its
    // database together with the saved copy of the key.
    await setGroups(user, userId, ["marketing"]);
    await restartBackend("wipe");
    await context.clearCookies();
    await login(user, "ordinary-user");
    await user.goto("/my-key");
    await expect(user.getByText(/Marketing/).first()).toBeVisible();

    // Self-service replacement, no administrator involved.
    await user.getByRole("button", { name: "Regenerate key" }).click();
    const replaced = user.waitForResponse(
      (r) => r.url().endsWith("/api/keys/regenerate"),
      { timeout: 60_000 },
    );
    await user.getByRole("button", { name: "Replace key" }).click();
    const response = await replaced;
    expect(response.status()).toBe(201);
    const newSecret: string = (await response.json()).key;
    created.push(newSecret);
    await expect(user.getByText(newSecret)).toBeVisible();

    // The new key lives in the new team and carries the consumed spend; the
    // old key is gone.
    const info = await (
      await user.request.get(
        `${upstreamOrigin}/key/info?key=${encodeURIComponent(newSecret)}`,
        { headers: { Authorization: `Bearer ${master}` } },
      )
    ).json();
    expect(info.info.team_id).toBe("sso-test-marketing");
    expect(info.info.spend).toBeGreaterThanOrEqual(0.25);
    expect(info.info.blocked).toBeFalsy();
    const chat = (secret: string) =>
      user.request.post(`${upstreamOrigin}/v1/chat/completions`, {
        headers: { Authorization: `Bearer ${secret}` },
        data: {
          model: "litegate-integration-mock",
          messages: [{ role: "user", content: "Synthetic rotation check" }],
        },
      });
    expect((await chat(newSecret)).status()).toBe(200);
    expect((await chat(oldSecret)).status()).toBe(401);
    expect(
      (await (await user.request.get("/api/keys")).json()).keys,
    ).toHaveLength(1);
  } finally {
    await setGroups(user, userId, ["engineering"]);
    await user.request.post(`${upstreamOrigin}/key/delete`, {
      headers: { Authorization: `Bearer ${master}` },
      data: { keys: created },
    });
    await context.close();
  }
});
