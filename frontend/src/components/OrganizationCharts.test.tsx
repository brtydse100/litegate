import { render, cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import {
  ContributionHistory,
  UsageBars,
  metricValue,
} from "./OrganizationCharts";
afterEach(cleanup);
const day = (date: string, values: Partial<Record<string, number>> = {}) => ({
  date,
  spend: 0,
  tokens: 0,
  requests: 0,
  ...values,
});

it.each([0.000001, 0.02, 1, 1234, 123456789])(
  "shows spend of %s as a finite contribution history",
  (spend) => {
    const daily = [
      day("2026-01-01", { spend: spend / 2 }),
      day("2026-01-02", { spend }),
    ];
    const { container } = render(
      <ContributionHistory
        daily={daily}
        totals={{ spend: spend * 1.5, tokens: 0, requests: 0 }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Spend/ }));
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
    expect(
      screen.getByRole("img", { name: /busiest day 2026-01-02/ }),
    ).toBeVisible();
    // The busiest day takes the darkest shade, whatever the scale.
    const busiest = container.querySelector('[title^="2026-01-02"]')!;
    expect(busiest.className.split(" ")).toContain("bg-teal");
  },
);
it("rounds sub-cent spend to two decimals for display", () => {
  expect(metricValue(0.000001, "spend")).toBe("$0.00");
  expect(metricValue(0.0000000123, "spend")).toBe("$0.00");
  expect(metricValue(0, "spend")).toBe("$0.00");
  expect(metricValue(1e-12, "spend")).toBe("$0.00");
});
it("keeps sub-cent chart proportions while rounding only their labels", () => {
  const { container } = render(
    <UsageBars
      title="Small charges"
      metric="spend"
      values={[
        { name: "A", spend: 0.00000002, tokens: 2, requests: 2 },
        { name: "B", spend: 0.00000001, tokens: 1, requests: 1 },
      ]}
    />,
  );
  expect(screen.getAllByText("$0.00")).toHaveLength(2);
  expect(
    [...container.querySelectorAll("[style]")].map((el) =>
      el.getAttribute("style"),
    ),
  ).toEqual(["width: 100%;", "width: 50%;"]);
});
it.each(["spend", "tokens", "requests"] as const)(
  "scales %s bars to actual maximum",
  (metric) => {
    const { container } = render(
      <UsageBars
        title="Usage"
        metric={metric}
        values={[
          { name: "A", spend: 0.04, tokens: 4, requests: 2 },
          { name: "B", spend: 0.02, tokens: 2, requests: 1 },
        ]}
      />,
    );
    expect(
      [...container.querySelectorAll("[style]")].map((el) =>
        el.getAttribute("style"),
      ),
    ).toEqual(["width: 100%;", "width: 50%;"]);
  },
);
it.each([
  { daily: [] },
  { daily: [{ date: "2026-01-01", spend: 0, tokens: 0, requests: 0 }] },
])("renders zero and empty usage finitely", ({ daily }) => {
  const { container } = render(
    <>
      <ContributionHistory
        daily={daily}
        totals={{ spend: 0, tokens: 0, requests: 0 }}
      />
      <UsageBars
        title="Usage"
        metric="spend"
        values={daily.map((d) => ({ ...d, name: d.date }))}
      />
    </>,
  );
  expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
  expect(container.textContent).toContain("$0.00");
});

it("offers full email copy access in per-user usage labels", () => {
  render(
    <UsageBars
      title="People"
      metric="spend"
      emailLabels
      values={[
        { name: "long.person@example.com", spend: 2, requests: 1, tokens: 1 },
      ]}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Copy email long.person@example.com" }),
  ).toBeVisible();
});

it("ranks groups by tokens and shows a chosen group's own history", () => {
  const { container } = render(
    <ContributionHistory
      daily={[
        day("2026-01-01", { tokens: 110 }),
        day("2026-01-02", { tokens: 400 }),
      ]}
      totals={{ spend: 0, tokens: 510, requests: 0 }}
      groupLabel="team"
      groups={[
        {
          id: "small",
          name: "Small",
          tokens: 10,
          spend: 0,
          requests: 0,
          daily: [day("2026-01-01", { tokens: 10 }), day("2026-01-02")],
        },
        {
          id: "big",
          name: "Big",
          tokens: 500,
          spend: 0,
          requests: 0,
          daily: [
            day("2026-01-01", { tokens: 100 }),
            day("2026-01-02", { tokens: 400 }),
          ],
        },
      ]}
    />,
  );
  const chips = screen
    .getByRole("group", { name: "Rank by team" })
    .querySelectorAll("button");
  // Tokens are shown first; the biggest token user comes right after All.
  expect([...chips].map((chip) => chip.textContent)).toEqual([
    "All",
    "Big500",
    "Small10",
  ]);
  fireEvent.click(screen.getByRole("button", { name: /^Small/ }));
  expect(
    screen.getByRole("img", { name: /10 tokens for Small/ }),
  ).toBeVisible();
  expect(
    container.querySelector('[title="2026-01-02: 0"]')!.className,
  ).toContain("bg-well");
});
