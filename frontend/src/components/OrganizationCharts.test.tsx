import { render, cleanup, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { TrendCard, UsageBars, metricValue } from "./OrganizationCharts";
afterEach(cleanup);
it.each([0.000001, 0.02, 1, 1234, 123456789])(
  "summarises spend of %s with a finite trend and its peak day",
  (spend) => {
    const daily = [
      { date: "2026-01-01", spend: spend / 2, tokens: 0, requests: 0 },
      { date: "2026-01-02", spend, tokens: 0, requests: 0 },
    ];
    const { container } = render(
      <TrendCard metric="spend" daily={daily} total={spend * 1.5} />,
    );
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
    expect(
      screen.getByRole("img", { name: "Spend (USD) over time" }),
    ).toBeVisible();
    expect(container.textContent).toContain(metricValue(spend * 1.5, "spend"));
    // One bar per day; the peak day is full height, whatever the scale.
    const bars = [...container.querySelectorAll("rect")];
    expect(bars.map((bar) => bar.getAttribute("height"))).toEqual(["23", "46"]);
    expect(bars[1].textContent).toContain("2026-01-02");
    expect(container.textContent).toMatch(/peak .+ on /);
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
      <TrendCard metric="spend" daily={daily} total={0} />
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
