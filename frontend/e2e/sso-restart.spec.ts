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

    // The member's surviving session sees one calm info message, no warnings,
    // and no replacement action the backend would reject.
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
      user.getByRole("button", { name: /Regenerate key|Regeneration paused/ }),
    ).toHaveCount(0);
    await expect(user.getByText(/it can't be replaced here/)).toBeVisible();
    // The backend still refuses replacement; the page just no longer offers it.
    expect(
      (
        await user.request.post("/api/keys/regenerate", {
          headers: mutationHeaders,
        })
      ).status(),
    ).toBe(409);

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

    // The original credential kept working throughout.
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
