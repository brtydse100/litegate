import { expect, type Page } from "@playwright/test";

/**
 * Opens a group's edit panel on the Organization page: from its table row or
 * the table's own "Open" button, by adding its department, or from a single
 * team's People section.
 */
export async function openGroup(page: Page, name: string) {
  const panel = page.getByRole("complementary", { name: `Edit ${name}` });
  const row = page.getByRole("button", {
    name: new RegExp(`^${name}, \\d+ users?$`),
  });
  const department = page.getByRole("button", {
    name,
    exact: true,
    pressed: false,
  });
  const details = page.getByRole("button", { name: "Team details" });
  await expect(row.or(department).or(details).first()).toBeVisible();
  if (await row.count()) await row.first().click();
  else if (await department.count()) {
    await department.click();
    await row.first().click();
  } else await details.click();
  await expect(panel).toBeVisible();
  return panel;
}
