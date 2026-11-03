import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { organizationUsage, organizationUsers } from "./organization";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-15T12:00:00Z"));
});
afterEach(() => vi.useRealTimers());

it("reconciles Cloud's reporting period and Priya's demo budget-period spend", () => {
  const report = organizationUsage("cloud", "2026-09-16", "2026-10-15");
  const priya = organizationUsers("cloud", 1).users[0];
  expect(report.by_user).toHaveLength(1);
  expect(report.by_user[0]).toMatchObject({ id: "priya", name: priya.email });
  expect(report.by_user[0].spend).toBeCloseTo(priya.budget_spend!);
  expect(report.totals.spend).toBeCloseTo(priya.budget_spend!);
});

it("uses the same dated data for members, groups, models and daily totals", () => {
  const report = organizationUsage("engineering", "2026-10-06", "2026-10-15");
  for (const rows of [
    report.by_user,
    report.by_group,
    report.by_model,
    report.daily,
  ]) {
    for (const metric of ["spend", "tokens", "requests"] as const) {
      expect(rows.reduce((total, row) => total + row[metric], 0)).toBeCloseTo(
        report.totals[metric],
      );
    }
  }
  const first = organizationUsage("cloud", "2026-09-16", "2026-09-30");
  const second = organizationUsage("cloud", "2026-10-01", "2026-10-15");
  const whole = organizationUsage("cloud", "2026-09-16", "2026-10-15");
  expect(first.totals.spend + second.totals.spend).toBeCloseTo(
    whole.totals.spend,
  );
  for (const model of whole.by_model) {
    for (const metric of ["spend", "tokens", "requests"] as const) {
      const left = first.by_model.find((value) => value.name === model.name)!;
      const right = second.by_model.find((value) => value.name === model.name)!;
      expect(left[metric] + right[metric]).toBeCloseTo(model[metric]);
    }
  }
});

it("has no demo usage before the displayed budget period", () => {
  const report = organizationUsage("cloud", "2026-09-01", "2026-09-15");
  expect(report.totals).toEqual({ spend: 0, tokens: 0, requests: 0 });
});
