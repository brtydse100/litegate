import { render, cleanup, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import {
  BarCard,
  DonutCard,
  UsageBars,
  metricValue,
  weekly,
} from "./OrganizationCharts";
afterEach(cleanup);
it.each([0.000001, 0.02, 1, 1234, 123456789])(
  "draws spend of %s as finite bars, the largest solid",
  (spend) => {
    const { container } = render(
      <BarCard
        title="Spend history"
        subtitle="By week"
        metric="spend"
        bars={[
          { label: "Week 1", value: spend / 2 },
          { label: "Week 2", value: spend },
        ]}
      />,
    );
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
    const bars = [...container.querySelectorAll("[title]")];
    expect(bars.map((bar) => bar.getAttribute("style"))).toEqual([
      "height: 50%;",
      "height: 100%;",
    ]);
    expect(bars[0].className).toContain("opacity-50");
    expect(bars[1].className).not.toContain("opacity-50");
    expect(
      screen.getByRole("img", { name: /^Spend history: Week 1 / }),
    ).toBeVisible();
  },
);

it("sums days into labelled weeks", () => {
  const daily = Array.from({ length: 9 }, (_, index) => ({
    date: `2026-01-${String(index + 1).padStart(2, "0")}`,
    spend: 0,
    tokens: 10,
    requests: 1,
  }));
  expect(weekly(daily, "tokens").map((week) => week.value)).toEqual([70, 20]);
});

it("shows each model's share of spend in a donut", () => {
  render(
    <DonutCard
      title="Spend by model"
      subtitle="Share"
      metric="spend"
      slices={[
        { label: "small", value: 25 },
        { label: "large", value: 75 },
        { label: "unused", value: 0 },
      ]}
    />,
  );
  expect(
    screen.getByRole("img", { name: "Spend by model: large 75%, small 25%" }),
  ).toBeVisible();
  expect(screen.queryByText("unused")).not.toBeInTheDocument();
});
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
      <BarCard
        title="Spend history"
        subtitle="By week"
        metric="spend"
        bars={weekly(daily, "spend")}
      />
      <DonutCard
        title="Spend by model"
        subtitle="Share"
        metric="spend"
        slices={[]}
      />
      <UsageBars
        title="Usage"
        metric="spend"
        values={daily.map((d) => ({ ...d, name: d.date }))}
      />
    </>,
  );
  expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
  expect(container.textContent).toContain("No recorded usage in this period.");
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
