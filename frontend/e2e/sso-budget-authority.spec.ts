import { expect, test, type Page } from "@playwright/test";
import { openGroup } from "./organizationPanel";

// Real Keycloak, real LiteLLM and the real backend with enforced budgets:
// a team administrator redistributes their team's budget but can never change
// the team's own total, in the UI or through the API.
const origin = "http://127.0.0.1:4176";
const password = "litegate-sso-test-password";
const headers = { Origin: origin };
const ordinaryUser = "10000000-0000-4000-8000-000000000004";

interface Group {
  id: string;
  name: string;
  assigned: number;
  can_edit_envelope: boolean;
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

async function view(page: Page) {
  const response = await page.request.get("/api/v1/organization/budgets");
  expect(response.status()).toBe(200);
  return (await response.json()) as { revision: number; groups: Group[] };
}

async function patch(page: Page, path: string, amount: string | null) {
  const { revision } = await view(page);
  return page.request.patch(`/api/v1/organization/budgets${path}`, {
    headers,
    data: { revision, amount },
  });
}

test("a team admin redistributes within the team total but cannot change it", async ({
  browser,
}) => {
  const contexts = await Promise.all(
    [0, 1, 2, 3].map(() => browser.newContext({ baseURL: origin })),
  );
  const [system, member, teamAdmin, childAdmin] = await Promise.all(
    contexts.map((context) => context.newPage()),
  );
  try {
    await login(system, "system-admin");
    await login(member, "ordinary-user");
    await login(teamAdmin, "engineering-admin");
    await login(childAdmin, "child-admin");

    // Start from a clean allocation: only the system admin sets the total.
    const all = await view(system);
    const engineering = all.groups.find((g) => g.name === "Engineering")!;
    const platform = all.groups.find((g) => g.name === "Platform")!;
    expect((await patch(system, `/groups/${platform.id}`, "0")).status()).toBe(
      200,
    );
    expect(
      (
        await patch(
          system,
          `/groups/${engineering.id}/users/${ordinaryUser}`,
          null,
        )
      ).status(),
    ).toBe(200);
    expect(
      (await patch(system, `/groups/${engineering.id}`, "100")).status(),
    ).toBe(200);

    // UI: the team total is read-only; child allocations are editable.
    await teamAdmin.goto("/organization");
    const engineeringPanel = await openGroup(teamAdmin, "Engineering");
    await expect(
      engineeringPanel.getByText(/Set by a parent team/),
    ).toBeVisible();
    await expect(teamAdmin.getByLabel("Engineering group budget")).toHaveCount(
      0,
    );
    const platformPanel = await openGroup(teamAdmin, "Platform");
    const childInput = platformPanel.getByLabel("Platform group budget");
    await childInput.fill("40");
    const saved = teamAdmin.waitForResponse(
      (r) => r.request().method() === "PATCH" && r.url().includes("/budgets/"),
    );
    await platformPanel.getByRole("button", { name: "Save changes" }).click();
    expect((await saved).status()).toBe(200);
    await expect(childInput).toHaveValue("40");
    await expect
      .poll(
        async () =>
          (await view(teamAdmin)).groups.find((g) => g.name === "Platform")
            ?.assigned,
      )
      .toBe(40);

    // Redistributing more than the total is rejected and shown.
    await childInput.fill("150");
    const rejected = teamAdmin.waitForResponse(
      (r) => r.request().method() === "PATCH" && r.url().includes("/budgets/"),
    );
    await platformPanel.getByRole("button", { name: "Save changes" }).click();
    expect((await rejected).status()).toBe(409);
    await expect(
      platformPanel
        .getByRole("alert")
        .filter({ hasText: /cannot cover|exceed/i }),
    ).toBeVisible();
    // The rejected draft stays for correction; the saved amount is unchanged.
    await expect(childInput).toHaveValue("150");

    // API: the total cannot be changed, raised or lowered, by the team admin.
    for (const amount of ["500", "50"]) {
      const response = await patch(
        teamAdmin,
        `/groups/${engineering.id}`,
        amount,
      );
      expect(response.status()).toBe(403);
      expect((await response.json()).detail).toMatch(
        /parent or system administrator/,
      );
    }
    // Lowering a member to $10 would raise the admin's own automatic share
    // ($60 left over 3 members = $20 each, then $25): rejected.
    const selfRaise = await patch(
      teamAdmin,
      `/groups/${engineering.id}/users/${ordinaryUser}`,
      "10",
    );
    expect(selfRaise.status()).toBe(403);
    expect((await selfRaise.json()).detail).toMatch(/personal allowance/);
    // Redistributing within the total without raising their own share works;
    // more than the total is rejected.
    expect(
      (
        await patch(
          teamAdmin,
          `/groups/${engineering.id}/users/${ordinaryUser}`,
          "30",
        )
      ).status(),
    ).toBe(200);
    expect(
      (
        await patch(
          teamAdmin,
          `/groups/${engineering.id}/users/${ordinaryUser}`,
          "1000",
        )
      ).status(),
    ).toBe(409);

    // A child-team admin cannot change their own team's total either, and
    // cannot reach the parent team at all.
    await childAdmin.goto("/organization");
    const ownPanel = await openGroup(childAdmin, "Platform");
    await expect(ownPanel.getByText(/Set by a parent team/)).toBeVisible();
    await expect(childAdmin.getByLabel("Platform group budget")).toHaveCount(0);
    expect(
      (await patch(childAdmin, `/groups/${platform.id}`, "999")).status(),
    ).toBe(403);
    expect(
      (await patch(childAdmin, `/groups/${engineering.id}`, "999")).status(),
    ).toBe(404);

    // An ordinary member cannot use the budget API at all.
    expect(
      (await member.request.get("/api/v1/organization/budgets")).status(),
    ).toBe(403);

    // Nothing above changed the totals that only the system admin controls.
    const after = await view(system);
    expect(after.groups.find((g) => g.name === "Engineering")?.assigned).toBe(
      100,
    );
    expect(after.groups.find((g) => g.name === "Platform")?.assigned).toBe(40);
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});
