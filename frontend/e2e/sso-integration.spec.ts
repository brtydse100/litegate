import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { access, writeFile } from "node:fs/promises";

const origin = "http://127.0.0.1:4176";
const upstreamOrigin = process.env.LITELLM_URL ?? "http://127.0.0.1:4001";
const password = "litegate-sso-test-password";
const personas = [
  ["system-admin", "admin", true],
  ["engineering-admin", "user", true],
  ["child-admin", "user", true],
  ["ordinary-user", "user", false],
  ["no-key-user", "user", false],
  ["outsider", "user", false],
  ["designated-nonadmin", "user", false],
  ["undesignated-admin", "user", false],
] as const;

async function login(page: Page, username: string) {
  let callbackStatus = 0;
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.origin === origin && url.pathname === "/api/auth/callback") {
      callbackStatus = response.status();
    }
  });
  await page.goto("/api/auth/login");
  await expect(page).toHaveURL(/127\.0\.0\.1:8082\/realms\/litegate-sso\//);
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.locator("#kc-login").click();
  await expect(page).toHaveURL(/127\.0\.0\.1:4176\/(?:my-key)?$/, {
    timeout: 30_000,
  });
  expect(callbackStatus).toBe(307);
  const response = await page.request.get("/api/auth/me");
  expect(response.status()).toBe(200);
  const user = await response.json();
  expect(user.auth_source).toBe("sso");
  expect(user.email).toBe(`${username}@litegate.example.invalid`);
  const session = (await page.context().cookies()).find(
    (cookie) => cookie.name === "litegate_session",
  );
  expect(session?.httpOnly).toBe(true);
  return user;
}

for (const [username, role, organization] of personas) {
  test(`real Keycloak login and authorization: ${username}`, async ({
    page,
  }) => {
    const user = await login(page, username);
    expect(user.role).toBe(role);
    const accessResponse = await page.request.get(
      "/api/v1/organization/access",
    );
    expect(accessResponse.status()).toBe(200);
    const access = await accessResponse.json();
    expect(access.organization).toBe(organization);
    expect(access.global_admin).toBe(role === "admin");
    expect((await page.request.get("/api/v1/organization")).status()).toBe(
      organization ? 200 : 403,
    );
    expect((await page.request.get("/api/v1/people")).status()).toBe(
      role === "admin" ? 200 : 403,
    );
    expect((await page.request.get("/api/analytics")).status()).toBe(200);
    if (username === "no-key-user") {
      const keys = await (await page.request.get("/api/keys")).json();
      expect(keys.keys).toEqual([]);
      await expect(
        page.getByRole("button", { name: "Create my API key" }),
      ).toBeVisible();
    }
  });
}

test("a callback without its browser state cookie fails closed", async ({
  page,
}) => {
  const response = await page.request.get(
    "/api/auth/callback?code=synthetic-invalid-code&state=synthetic-invalid-state",
  );
  expect(response.status()).toBe(400);
  expect((await response.json()).detail).toBe("Invalid state");
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);
});

test("registered SSO people include a person who has never created a key", async ({
  page,
}) => {
  await login(page, "system-admin");
  const response = await page.request.get("/api/v1/people?search=no-key-user");
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(JSON.stringify(body)).toContain(
    "no-key-user@litegate.example.invalid",
  );
  await page.goto("/users");
  await expect(
    page.getByRole("heading", { name: "People", exact: true }),
  ).toBeVisible();
  const directory = page.getByRole("region", { name: "People directory" });
  await directory.getByLabel("Search people by email").fill("no-key-user");
  await directory.getByRole("button", { name: "Search people" }).click();
  await expect(
    directory.getByText("no-key-user@litegate.example.invalid", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Add user", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Reset password", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText(/local account actions are below/i)).toHaveCount(
    0,
  );
});

test("the full account email is visible and copyable", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await login(page, "system-admin");
  const email = "system-admin@litegate.example.invalid";
  await expect(page.getByText(email, { exact: true }).first()).toBeVisible();
  await page
    .getByRole("button", { name: `Copy email ${email}` })
    .first()
    .click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(email);
});

test("a real owned key retains its identifier and stored secret across login and backend restart", async ({
  page,
  browser,
}) => {
  await login(page, "ordinary-user");
  const mutationHeaders = { Origin: origin };
  const created = await page.request.post("/api/keys", {
    headers: mutationHeaders,
  });
  expect(created.status()).toBe(201);
  const secret: string = (await created.json()).key;
  try {
    const metadata = await (await page.request.get("/api/keys")).json();
    expect(metadata.keys).toHaveLength(1);
    const identifier = metadata.keys[0].token;
    expect(typeof identifier).toBe("string");
    expect(identifier === secret).toBe(false);
    expect(metadata.keys[0].secret_available).toBe(true);
    const reveal = await page.request.post("/api/keys/reveal", {
      headers: mutationHeaders,
      data: { key: identifier },
    });
    expect(reveal.status()).toBe(200);
    expect((await reveal.json()).key === secret).toBe(true);

    const other = await browser.newContext({ baseURL: origin });
    try {
      const otherPage = await other.newPage();
      await login(otherPage, "outsider");
      expect(
        (
          await otherPage.request.post("/api/keys/reveal", {
            headers: mutationHeaders,
            data: { key: identifier },
          })
        ).status(),
      ).toBe(403);
    } finally {
      await other.close();
    }

    await page.context().clearCookies();
    await login(page, "ordinary-user");
    const refreshed = await (await page.request.get("/api/keys")).json();
    expect(refreshed.keys[0].token === identifier).toBe(true);
    const again = await page.request.post("/api/keys/reveal", {
      headers: mutationHeaders,
      data: { key: identifier },
    });
    expect(again.status()).toBe(200);
    expect((await again.json()).key === secret).toBe(true);
    const marker = "../backend/data/litegate-sso-test.restart";
    await writeFile(marker, "restart");
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
        { timeout: 30_000 },
      )
      .toBe(true);
    const restarted = await (await page.request.get("/api/keys")).json();
    expect(restarted.keys[0].token === identifier).toBe(true);
    const afterRestart = await page.request.post("/api/keys/reveal", {
      headers: mutationHeaders,
      data: { key: identifier },
    });
    expect(afterRestart.status()).toBe(200);
    expect((await afterRestart.json()).key === secret).toBe(true);
    const inference = await page.request.post(
      `${upstreamOrigin}/v1/chat/completions`,
      {
        headers: { Authorization: `Bearer ${secret}` },
        data: {
          model: "litegate-integration-mock",
          messages: [{ role: "user", content: "Synthetic SSO restart check" }],
        },
      },
    );
    expect(inference.status()).toBe(200);
  } finally {
    // Remove only this test's created upstream credential, even after an assertion failure.
    const deleted = await page.request.post(`${upstreamOrigin}/key/delete`, {
      headers: { Authorization: "Bearer sk-litegate-integration-master" },
      data: { keys: [secret] },
    });
    expect(deleted.status()).toBe(200);
  }
});

test("personal analytics read only the authenticated owner even with an owner query", async ({
  page,
  browser,
}) => {
  await login(page, "ordinary-user");
  const other = await browser.newContext({ baseURL: origin });
  try {
    const otherPage = await other.newPage();
    await login(otherPage, "outsider");
    execFileSync("python", [
      "../scripts/run_sso_backend.py",
      "--seed-analytics",
    ]);
    const ordinary = await (
      await page.request.get(
        "/api/analytics?user_id=10000000-0000-4000-8000-000000000006",
      )
    ).json();
    const outsider = await (
      await otherPage.request.get("/api/analytics")
    ).json();
    expect(ordinary.totals.requests).toBe(11);
    expect(outsider.totals.requests).toBe(97);
  } finally {
    await other.close();
  }
});

test("delegated pages and APIs expose only the authorized subtree without an Enterprise license", async ({
  page,
  browser,
}) => {
  await login(page, "engineering-admin");
  await page.goto("/organization");
  await expect(
    page.getByRole("heading", { name: /organization/i }).first(),
  ).toBeVisible();
  const scoped = await (await page.request.get("/api/v1/organization")).json();
  expect(
    scoped.groups.every(
      (group: { path: string[] }) => group.path[0] === "Engineering",
    ),
  ).toBe(true);
  expect(JSON.stringify(scoped)).not.toContain("Marketing");
  const adminContext = await browser.newContext({ baseURL: origin });
  try {
    const adminPage = await adminContext.newPage();
    await login(adminPage, "system-admin");
    const all = await (
      await adminPage.request.get("/api/v1/organization")
    ).json();
    const marketing = all.groups.find(
      (group: { name: string }) => group.name === "Marketing",
    );
    expect(
      (
        await page.request.get(`/api/v1/organization/groups/${marketing.id}`)
      ).status(),
    ).toBe(404);
    expect(
      (
        await page.request.get(
          `/api/v1/organization/usage?node=${marketing.id}`,
        )
      ).status(),
    ).toBe(404);
    expect((await page.request.get("/api/v1/teams")).status()).toBe(403);
  } finally {
    await adminContext.close();
  }
});

test("group changes retain the same canonical owner and original key secret", async ({
  page,
  browser,
}) => {
  const keycloak = await page.request.post(
    "http://127.0.0.1:8082/realms/master/protocol/openid-connect/token",
    {
      form: {
        client_id: "admin-cli",
        grant_type: "password",
        username: "litegate-test-admin",
        password: "litegate-test-admin-password",
      },
    },
  );
  expect(keycloak.status()).toBe(200);
  const token = (await keycloak.json()).access_token;
  const headers = { Authorization: `Bearer ${token}` };
  const groups = await (
    await page.request.get(
      "http://127.0.0.1:8082/admin/realms/litegate-sso/groups",
      { headers },
    )
  ).json();
  const engineering = groups.find(
    (group: { name: string }) => group.name === "engineering",
  ).id;
  const marketing = groups.find(
    (group: { name: string }) => group.name === "marketing",
  ).id;
  const membership =
    "http://127.0.0.1:8082/admin/realms/litegate-sso/users/10000000-0000-4000-8000-000000000004/groups/";
  await login(page, "ordinary-user");
  const created = await page.request.post("/api/keys", {
    headers: { Origin: origin },
  });
  expect(created.status()).toBe(201);
  const secret = (await created.json()).key;
  const before = (await (await page.request.get("/api/keys")).json()).keys[0];
  const fresh = await browser.newContext({ baseURL: origin });
  try {
    expect(
      (
        await page.request.delete(membership + engineering, { headers })
      ).status(),
    ).toBe(204);
    expect(
      (await page.request.put(membership + marketing, { headers })).status(),
    ).toBe(204);
    const newPage = await fresh.newPage();
    const user = await login(newPage, "ordinary-user");
    expect(user.user_id).toBe("10000000-0000-4000-8000-000000000004");
    const after = (await (await newPage.request.get("/api/keys")).json())
      .keys[0];
    expect(after.token).toBe(before.token);
    expect(after.team_id).toBe("sso-test-marketing");
    const revealed = await newPage.request.post("/api/keys/reveal", {
      headers: { Origin: origin },
      data: { key: after.token },
    });
    expect((await revealed.json()).key === secret).toBe(true);
    const inference = await newPage.request.post(
      `${upstreamOrigin}/v1/chat/completions`,
      {
        headers: { Authorization: `Bearer ${secret}` },
        data: {
          model: "litegate-integration-mock",
          messages: [{ role: "user", content: "Synthetic group transfer" }],
        },
      },
    );
    expect(inference.status()).toBe(200);
  } finally {
    await page.request.delete(membership + marketing, { headers });
    await page.request.put(membership + engineering, { headers });
    await page.request.post(`${upstreamOrigin}/key/delete`, {
      headers: { Authorization: "Bearer sk-litegate-integration-master" },
      data: { keys: [secret] },
    });
    await fresh.close();
  }
});
