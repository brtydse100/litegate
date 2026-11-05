import { render, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { SpendTrend, UsageBars, metricValue } from "./OrganizationCharts";
afterEach(cleanup);
it.each([0.000001, 0.000002, 0.0024, 0.02, 0.04, 0.99, 1, 1234, 123456789])(
  "distinguishes ticks at scale %s",
  (spend) => {
    const { container } = render(
      <SpendTrend
        metric="spend"
        daily={[{ date: "2026-01-01", spend, tokens: 0, requests: 0 }]}
      />,
    );
    const labels = [...container.querySelectorAll("g text")].map(
      (el) => el.textContent,
    );
    expect(new Set(labels).size).toBe(3);
    expect(labels[1]).not.toMatch(/^\$0(?:\.0+)?$/);
    expect(labels[2]).not.toMatch(/^\$0(?:\.0+)?$/);
  },
);
it("shows microspend precisely in accessible values", () => {
  expect(metricValue(0.000001, "spend")).toBe("$0.000001");
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
      <SpendTrend metric="spend" daily={daily} />
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
