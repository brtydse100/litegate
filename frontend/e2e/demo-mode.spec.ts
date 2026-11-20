import { expect, test } from "@playwright/test";

test("organization demo filters usage and protects the admin view", async ({
  page,
}) => {
  await page.goto("./");
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await expect(page).toHaveURL(/\/organization$/);
  const groups = page.getByRole("list", { name: "Organization groups" });
  await expect(groups.getByRole("button", { name: /^Platform,/ })).toHaveCount(
    0,
  );
  await groups
    .getByRole("button", {
      name: "Expand Engineering → Infrastructure",
      exact: true,
    })
    .click();
  await groups.getByRole("button", { name: /^Platform,/ }).click();
  const platform = page.getByRole("complementary", { name: "Edit Platform" });
  await expect(platform.getByText("$100", { exact: true })).toBeVisible();
  await expect(platform.getByText(/Overrides Infrastructure/)).toBeVisible();
  await expect(page.getByText("sam@example.com", { exact: true })).toHaveCount(
    0,
  );
  // Spend, requests and tokens each have their own small trend.
  await expect(
    page.getByRole("img", { name: "Tokens over time" }),
  ).toBeVisible();
  await groups
    .getByRole("button", {
      name: "Collapse Engineering → Infrastructure",
      exact: true,
    })
    .click();
  await expect(groups.getByRole("button", { name: /^Platform,/ })).toHaveCount(
    0,
  );
  await expect(platform.getByText("$100", { exact: true })).toBeVisible();
  await groups
    .getByRole("button", {
      name: "Expand Engineering → Infrastructure",
      exact: true,
    })
    .click();
  await groups.getByRole("button", { name: /^Cloud,/ }).click();
  const cloud = page.getByRole("complementary", { name: "Edit Cloud" });
  await expect(cloud.getByText(/Inherited from Engineering/)).toBeVisible();
  await expect(cloud.getByText("$50", { exact: true })).toBeVisible();
  const memberChart = page
    .getByRole("heading", { name: "Usage by member" })
    .locator("..");
  await expect(memberChart.getByText("priya@example.com")).toBeVisible();
  await expect(memberChart.getByText("$29.93", { exact: true })).toBeVisible();
  await expect(memberChart.getByText("Direct members")).toHaveCount(0);
  await page.getByRole("button", { name: "View demo as user" }).click();
  await expect(page).toHaveURL(/\/my-key$/);
  await expect(
    page.getByRole("navigation", { name: "Admin navigation" }),
  ).toHaveCount(0);
  const status = await page.evaluate(
    async () => (await fetch("/api/v1/organization")).status,
  );
  expect(status).toBe(403);
});

test("interactive demo keeps its key views consistent and supports local sign-in", async ({
  page,
}) => {
  await page.goto("./");
  await expect(page.getByRole("heading", { name: "My key" })).toBeAttached();
  await expect(page.getByRole("region", { name: "Budget" })).toBeVisible();

  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Use dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.reload();
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Use light theme" }).click();

  await page.getByRole("button", { name: "Regenerate key" }).click();
  await page.getByRole("button", { name: "Replace key" }).click();
  await expect(page.getByText("sk-litegate-demo-rotated-4d8e")).toBeVisible();
  await page.getByRole("button", { name: "Hide API key" }).click();

  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await page.getByRole("link", { name: "Keys", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Key policies" }),
  ).toBeVisible();
  await expect(page.getByText("sk-litega....4d8e")).toBeVisible();
  await expect(page.getByText("sk-litega....7f3a")).toHaveCount(0);
  await expect(page.getByText("$18.42 spent")).toBeVisible();
  await page.getByLabel("Select alex-primary").check({ force: true });
  await page.getByLabel("Select product-research").check({ force: true });
  await page.getByRole("button", { name: "Reset spend for 2 keys" }).click();
  await expect(
    page.getByRole("dialog", { name: "Reset spend for 2 keys?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reset spend to zero" }).click();
  await expect(page.getByText("2 reset, 0 failed.")).toBeVisible();
  await expect(page.getByText("$0.00 spent")).toHaveCount(2);

  await page.getByRole("button", { name: "View demo as user" }).click();
  await expect(page).toHaveURL(/\/litegate\/my-key$/);
  await expect(
    page.getByRole("navigation", { name: "Admin navigation" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "View demo as admin" }).click();
  // The admin sidebar appears at once, without leaving My key.
  await expect(page).toHaveURL(/\/litegate\/my-key$/);
  await expect(
    page.getByRole("link", { name: "Keys", exact: true }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Teams" }).click();
  await expect(
    page.getByRole("heading", { name: "LiteLLM team policy" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/litegate\/login$/);
  await expect(
    page.getByRole("link", { name: "Sign in with SSO" }),
  ).toHaveCount(0);

  await page.getByLabel("Username").fill("demo");
  await page.getByLabel("Password").fill("demo-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/litegate\/my-key$/);
  await expect(page.getByRole("region", { name: "Budget" })).toBeVisible();
});

for (const width of [390, 1280]) {
  test(`people directory and long email copy work at ${width}px`, async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("./");
    await page.getByRole("link", { name: "Organization", exact: true }).click();
    await page.getByRole("link", { name: "People", exact: true }).click();
    const directory = page.getByRole("region", { name: "People directory" });
    await directory.getByLabel("Search people by email").fill("no-key");
    await directory
      .getByRole("button", { name: "Search people", exact: true })
      .click();
    await expect(
      directory.getByText("no-key@example.com", { exact: true }),
    ).toBeVisible();
    const email =
      "long.address.with.several.selectable.parts@a-long-organization-domain.example.com";
    await page
      .getByLabel("Username", { exact: true })
      .fill(`synthetic-${width}`);
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page
      .getByLabel("Temporary password", { exact: true })
      .fill("synthetic-only-password");
    await page.getByRole("button", { name: "Add user", exact: true }).click();
    const address = page.getByText(email, { exact: true });
    await expect(address).toBeVisible();
    await expect(address).toHaveCSS("white-space", "normal");
    const bounds = await address.boundingBox();
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    await page
      .getByRole("button", { name: `Copy email ${email}`, exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("Email copied");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
      email,
    );
  });
}

test("the signed-in email is visible and copyable on My key", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("./my-key");
  await page.getByRole("button", { name: "View demo as user" }).click();
  const copy = page.getByRole("button", { name: /^Copy email / }).first();
  await expect(copy).toBeVisible();
  const email = (await copy.getAttribute("aria-label"))!.replace(
    "Copy email ",
    "",
  );
  await expect(page.getByText(email, { exact: true }).first()).toBeVisible();
  await copy.click();
  // Copying is asynchronous; wait for the clipboard instead of racing it.
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe(email);
});

test("My key says which team the key is assigned through", async ({ page }) => {
  await page.goto("./my-key");
  await page.getByRole("button", { name: "View demo as user" }).click();
  await expect(page.getByText(/^Assigned through /)).toBeVisible();
  await expect(page.getByText(/Key status:/)).toHaveCount(0);
});

test("the top-bar account menu stays on a phone screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("./my-key");
  // The top bar belongs to the user layout; admins get the sidebar.
  await page.getByRole("button", { name: "View demo as user" }).click();
  await expect(
    page.getByRole("navigation", { name: "Primary navigation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Account menu" }).click();
  const box = await page.getByRole("menu").boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
});

for (const width of [390, 768, 1024, 1100, 1280]) {
  test(`an opened group's panel is on screen at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("./organization");
    const groups = page.getByRole("list", { name: "Organization groups" });
    await groups.getByRole("button", { name: /^Infrastructure,/ }).click();
    const panel = page.getByRole("complementary", {
      name: "Edit Infrastructure",
    });
    await expect(panel).toBeVisible();
    // Let the group's report finish rendering, then check the panel stayed put.
    await expect(
      page.getByText(/Usage in Infrastructure/).first(),
    ).toBeVisible();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);
    await expect(
      panel.getByRole("heading", { name: "Infrastructure" }),
    ).toBeInViewport();
  });
}

test("the sidebar account menu fits inside the sidebar", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("./");
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  const nav = page.getByRole("navigation", { name: "Admin navigation" });
  await nav.getByRole("button", { name: "Account menu" }).last().click();
  await expect(nav.getByRole("menu")).toBeVisible();
  const overflow = await nav.evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("the current sidebar link is visible on phones", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("./");
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  for (const [route, label] of [
    ["teams", "Teams"],
    ["keys", "Keys"],
    ["users", "People"],
    ["status", "Status"],
  ]) {
    await page.goto(`./${route}`);
    const nav = page.getByRole("navigation", { name: "Admin navigation" });
    await expect(nav.getByText(/^(Ready|Not ready)$/).first()).toBeAttached();
    await page.waitForLoadState("networkidle");
    await expect(
      // The Status link's name also carries its hidden Ready text.
      nav.getByRole("link", { name: new RegExp(`^${label}`) }),
    ).toBeInViewport({ ratio: 0.95 });
  }
});

test("pages fit a phone screen without sideways scrolling", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("./");
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  const admin = ["organization", "teams", "keys", "users", "status"];
  for (const route of [...admin, "analytics", "my-key"]) {
    await page.goto(`./${route}`);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    // Admin pages show a status dot once system status loads; wait for it,
    // and for page data, so late content is measured too.
    if (admin.includes(route))
      await expect(
        page.getByText(/^(Ready|Not ready)$/).first(),
      ).toBeAttached();
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, `${route} scrolls sideways`).toBeLessThanOrEqual(0);
  }
});

test("team owners see only their own team", async ({ page }) => {
  await page.goto("./my-key");
  await page.getByRole("button", { name: "View demo as team owner" }).click();

  // An owner of a team of teams works inside that team.
  await page
    .getByRole("button", { name: "Own Infrastructure, a team of teams" })
    .click();
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Groups in Infrastructure" }),
  ).toBeVisible();
  const groups = page.getByRole("list", { name: "Organization groups" });
  await expect(
    groups.getByRole("button", { name: /^Platform,/ }),
  ).toBeVisible();
  await expect(groups.getByRole("button", { name: /^Cloud,/ })).toBeVisible();
  await expect(page.getByText("Marketing")).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Keys", exact: true }),
  ).toHaveCount(0);

  // An owner of a team of people sees its report and members at once.
  await page
    .getByRole("button", { name: "Own Platform, a team of people" })
    .click();
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Usage in Platform" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Usage by member" }),
  ).toBeVisible();
  await expect(page.getByText("Cloud")).toHaveCount(0);
});

test("the usage report ranks groups by tokens", async ({ page }) => {
  await page.goto("./organization");
  await page.getByRole("button", { name: "All", exact: true }).click();
  await page
    .getByRole("button", { name: "Usage report, all groups, 4 users" })
    .click();
  const grid = page.getByRole("region", { name: "Tokens by department" });
  await expect(grid).toBeVisible();
  const rows = grid.getByRole("img");
  await expect(rows.first()).toHaveAccessibleName(/^Engineering: /);
  await expect(rows.nth(1)).toHaveAccessibleName(/^Marketing: /);
});
