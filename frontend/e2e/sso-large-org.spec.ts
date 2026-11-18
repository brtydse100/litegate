import { expect, test, type Browser, type Page } from "@playwright/test";

// Real Keycloak, real LiteLLM and the real backend with enforced budgets:
// administrators set per-user limits on both pages, and many members replace
// their keys at the same time.
const origin = "http://127.0.0.1:4176";
const upstreamOrigin = process.env.LITELLM_URL ?? "http://127.0.0.1:4001";
const master = { Authorization: "Bearer sk-litegate-integration-master" };
const password = "litegate-sso-test-password";
const headers = { Origin: origin };

interface Group {
  id: string;
  name: string;
  per_user: number | null;
  per_user_override: number | null;
}

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

async function signedIn(browser: Browser, username: string) {
  const context = await browser.newContext({ baseURL: origin });
  const page = await context.newPage();
  await login(page, username);
  return { context, page };
}

async function groups(page: Page) {
  const response = await page.request.get("/api/v1/organization/budgets");
  expect(response.status()).toBe(200);
  return ((await response.json()) as { groups: Group[] }).groups;
}

async function freshKey(page: Page) {
  for (const old of (await (await page.request.get("/api/keys")).json()).keys) {
    await page.request.post(`${upstreamOrigin}/key/delete`, {
      headers: master,
      data: { keys: [old.token] },
    });
  }
  const created = await page.request.post("/api/keys", { headers });
  expect(created.status()).toBe(201);
  return (await created.json()).key as string;
}

async function keyInfo(page: Page, secret: string) {
  const response = await page.request.get(
    `${upstreamOrigin}/key/info?key=${encodeURIComponent(secret)}`,
    { headers: master },
  );
  return response.ok() ? (await response.json()).info : null;
}

test("a global administrator sets per-user limits on Budget planning and the Teams page", async ({
  browser,
}) => {
  test.setTimeout(240_000);
  const admin = await signedIn(browser, "system-admin");
  const teamAdmin = await signedIn(browser, "engineering-admin");
  const member = await signedIn(browser, "ordinary-user");
  let secret = "";
  let engineering = "";
  try {
    secret = await freshKey(member.page);
    engineering = (await groups(admin.page)).find(
      (g) => g.name === "Engineering",
    )!.id;

    // Budget planning: override the configured limit (none) with $25.
    await admin.page.goto("/organization");
    const input = admin.page.getByLabel("Engineering per-user limit");
    await input.fill("25");
    const saved = admin.page.waitForResponse(
      (r) => r.request().method() === "PATCH" && r.url().endsWith("/per-user"),
    );
    await admin.page
      .getByRole("button", { name: "Save Engineering per-user limit" })
      .click();
    expect((await saved).status()).toBe(200);
    const after = await groups(admin.page);
    expect(after.find((g) => g.name === "Engineering")?.per_user).toBe(25);
    // Platform has no limit of its own and inherits Engineering's.
    expect(after.find((g) => g.name === "Platform")?.per_user).toBe(25);

    // A team administrator sees the limit but cannot change it.
    await teamAdmin.page.goto("/organization");
    await expect(
      teamAdmin.page.getByText(/Per-user limit: \$25\.00 \(set here/).first(),
    ).toBeVisible();
    await expect(
      teamAdmin.page.getByLabel("Engineering per-user limit"),
    ).toHaveCount(0);
    const denied = await teamAdmin.page.request.patch(
      `/api/v1/organization/groups/${engineering}/per-user`,
      { headers, data: { amount: "999" } },
    );
    expect(denied.status()).toBe(403);

    // Teams page: the config-managed team edits the same limit.
    await admin.page.goto("/teams");
    await admin.page.getByLabel("Search teams").fill("sso-test-engineering");
    await admin.page
      .getByRole("button", { name: "Search", exact: true })
      .click();
    const row = admin.page.locator("article", {
      has: admin.page.getByText("sso-test-engineering", { exact: true }),
    });
    await row.getByRole("button", { name: "Edit" }).click();
    const dialog = admin.page.getByRole("dialog", { name: "Edit team" });
    const limit = dialog.getByRole("spinbutton", {
      name: "Per-user limit (USD)",
    });
    await expect(limit).toHaveValue("25");
    await limit.fill("30");
    const teamSaved = admin.page.waitForResponse(
      (r) => r.request().method() === "PATCH" && r.url().endsWith("/per-user"),
    );
    await dialog.getByRole("button", { name: "Save changes" }).click();
    expect((await teamSaved).status()).toBe(200);
    await expect(dialog).toHaveCount(0);
    expect(
      (await groups(admin.page)).find((g) => g.name === "Engineering")
        ?.per_user_override,
    ).toBe(30);

    // The next synchronization caps the member's key at their allowance:
    // their share of any group total, never above the per-user limit.
    const allowance = async () =>
      (
        (await (
          await admin.page.request.get("/api/v1/organization/budgets")
        ).json()) as {
          groups: {
            name: string;
            users: { email: string; allocation: number }[];
          }[];
        }
      ).groups
        .find((g) => g.name === "Engineering")
        ?.users.find((u) => u.email.startsWith("ordinary-user"))?.allocation;
    await expect.poll(allowance).toBeLessThanOrEqual(30);
    await expect
      .poll(
        async () =>
          (await keyInfo(member.page, secret))?.max_budget ===
          (await allowance()),
        { timeout: 150_000, intervals: [5_000] },
      )
      .toBe(true);
  } finally {
    if (engineering)
      await admin.page.request.patch(
        `/api/v1/organization/groups/${engineering}/per-user`,
        { headers, data: { amount: null } },
      );
    if (secret)
      await member.page.request.post(`${upstreamOrigin}/key/delete`, {
        headers: master,
        data: { keys: [secret] },
      });
    await Promise.all(
      [admin, teamAdmin, member].map(({ context }) => context.close()),
    );
  }
});

test("many members replacing their keys at once all succeed without queueing", async ({
  browser,
}) => {
  test.setTimeout(240_000);
  const names = [
    "ordinary-user",
    "designated-nonadmin",
    "undesignated-admin",
    "engineering-admin",
    "child-admin",
  ];
  const members = await Promise.all(
    names.map((name) => signedIn(browser, name)),
  );
  const created: string[] = [];
  try {
    const before = await Promise.all(members.map(({ page }) => freshKey(page)));
    created.push(...before);
    const started = Date.now();
    const responses = await Promise.all(
      members.map(async ({ page }) => {
        const begun = Date.now();
        const response = await page.request.post("/api/keys/regenerate", {
          headers,
          timeout: 120_000,
        });
        return { response, seconds: (Date.now() - begun) / 1000 };
      }),
    );
    const total = (Date.now() - started) / 1000;
    const after: string[] = [];
    for (const { response } of responses) {
      expect(response.status()).toBe(201);
      after.push((await response.json()).key);
    }
    created.push(...after);
    // Each replacement waits ~12 s for spend to settle, in parallel rather
    // than one after another (five in a row would take over a minute).
    expect(total).toBeLessThan(45);
    for (const [index, { page }] of members.entries()) {
      expect((await keyInfo(page, after[index]))?.blocked).toBeFalsy();
      // LiteLLM keeps deleted keys only as records marked deleted.
      expect((await keyInfo(page, before[index]))?.status ?? "deleted").toBe(
        "deleted",
      );
      expect(
        (await (await page.request.get("/api/keys")).json()).keys,
      ).toHaveLength(1);
    }
  } finally {
    await members[0].page.request.post(`${upstreamOrigin}/key/delete`, {
      headers: master,
      data: { keys: created },
    });
    await Promise.all(members.map(({ context }) => context.close()));
  }
});
