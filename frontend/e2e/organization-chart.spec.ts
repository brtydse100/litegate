import { expect, test } from "@playwright/test";
import {
  organizationChildren,
  organizationGroup,
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
    else if (url.pathname === "/api/v1/organization/children")
      body = organizationChildren();
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
  await page.getByRole("button", { name: "All groups, 4 users" }).click();
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

test("organization fetches direct children and selected data progressively", async ({
  page,
}) => {
  const requests: string[] = [];
  let releaseChildren!: () => void;
  const childrenGate = new Promise<void>((resolve) => {
    releaseChildren = resolve;
  });
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const url = new URL(route.request().url());
    requests.push(url.pathname + url.search);
    let body: unknown = {};
    if (url.pathname === "/api/auth/me")
      body = {
        user_id: "admin",
        email: "admin@example.com",
        role: "admin",
        auth_source: "local",
        team_ids: [],
      };
    if (url.pathname === "/api/v1/organization/children") {
      const parent = url.searchParams.get("parent");
      if (parent === "engineering") await childrenGate;
      body = organizationChildren(parent);
    }
    if (url.pathname.startsWith("/api/v1/organization/groups/"))
      body = organizationGroup(url.pathname.split("/").at(-1)!);
    if (url.pathname === "/api/v1/organization/users")
      body = organizationUsers(url.searchParams.get("node"), 1);
    if (url.pathname === "/api/v1/organization/usage")
      body = organizationUsage(
        url.searchParams.get("node"),
        url.searchParams.get("start_date")!,
        url.searchParams.get("end_date")!,
      );
    await route.fulfill({ json: body });
  });
  await page.goto("/organization");
  await expect(
    page.getByRole("button", { name: "Engineering, 3 users" }),
  ).toBeVisible();
  expect(requests.filter((path) => path.includes("organization"))).toEqual([
    "/api/v1/organization/children",
  ]);
  await page.getByRole("button", { name: "Engineering, 3 users" }).click();
  await expect(
    page.getByRole("button", { name: "Marketing, 1 user" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Infrastructure, 2 users" }),
  ).toHaveCount(0);
  releaseChildren();
  await expect(
    page.getByRole("button", { name: "Infrastructure, 2 users" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Platform, 1 user" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Collapse Engineering" }).click();
  await page.getByRole("button", { name: "Expand Engineering" }).click();
  await expect(
    page.getByRole("button", { name: "Infrastructure, 2 users" }),
  ).toBeVisible();
  expect(
    requests.filter(
      (path) => path === "/api/v1/organization/children?parent=engineering",
    ),
  ).toHaveLength(1);
  await page.getByRole("button", { name: "Infrastructure, 2 users" }).click();
  await expect(
    page.getByRole("button", { name: "Cloud, 1 user" }),
  ).toBeVisible();
  expect(
    requests.some(
      (path) => path === "/api/v1/organization/children?parent=infrastructure",
    ),
  ).toBe(true);
});
