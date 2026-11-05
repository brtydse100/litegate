import { expect, test } from "@playwright/test";
import {
  organizationOverview,
  organizationUsers,
  organizationUsage,
} from "../src/demo/organization";

test("@smoke microspend axis labels fit inside the chart", async ({ page }) => {
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const url = new URL(route.request().url());
    let body: unknown = {};
    if (url.pathname === "/api/auth/me")
      body = {
        user_id: "admin",
        email: "admin@example.com",
        role: "admin",
        auth_source: "local",
        team_ids: [],
      };
    else if (url.pathname === "/api/v1/organization")
      body = organizationOverview();
    else if (url.pathname === "/api/v1/organization/users")
      body = organizationUsers(null, 1);
    else if (url.pathname === "/api/v1/organization/usage")
      body = {
        ...organizationUsage(null, "2026-01-01", "2026-01-01"),
        daily: [
          { date: "2026-01-01", spend: 0.000001, tokens: 0, requests: 0 },
        ],
      };
    await route.fulfill({ json: body });
  });
  await page.goto("/organization");
  const chart = page.getByRole("img", { name: "Spend (USD) over time" });
  await expect(chart).toBeVisible();
  const bounds = await chart.locator("g text").evaluateAll((labels) =>
    labels.map((label) => {
      const box = (label as SVGGraphicsElement).getBBox();
      return { text: label.textContent, left: box.x };
    }),
  );
  expect(bounds).toHaveLength(3);
  expect(bounds.map((label) => label.text)).toContain("$0.000001");
  for (const label of bounds) expect(label.left).toBeGreaterThanOrEqual(0);
});
