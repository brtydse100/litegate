import { expect, test } from "@playwright/test";

// Playwright hides scrollbars by default; real Windows browsers do not, and
// their scrollbars take width from the layout. This must be file-level.
test.use({ launchOptions: { ignoreDefaultArgs: ["--hide-scrollbars"] } });

for (const width of [1136, 1139, 1140, 1150, 1157]) {
  test(`the group panel stays visible at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("./organization");
    await page.addStyleTag({
      content: "::-webkit-scrollbar { width: 17px; height: 17px; }",
    });
    const groups = page.getByRole("list", { name: "Organization groups" });
    await groups.getByRole("button", { name: /^Infrastructure,/ }).click();
    const panel = page.getByRole("complementary", {
      name: "Edit Infrastructure",
    });
    await expect(
      page.getByText(/Usage in Infrastructure/).first(),
    ).toBeVisible();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    // The scrollbar must really take space, or this test proves nothing.
    expect(
      await page
        .locator("main")
        .evaluate((main) => main.offsetWidth - main.clientWidth),
    ).toBe(17);
    await expect(
      panel.getByRole("heading", { name: "Infrastructure" }),
    ).toBeInViewport();
    // Either a full row above the report, or a 340px column beside it.
    const box = (await panel.boundingBox())!;
    expect(width >= 1140 ? box.width : width - box.width).toBeLessThanOrEqual(
      340,
    );
  });
}
