import { describe, expect, it } from "vitest";
import type { BudgetWindowSchedule } from "../types";
import { activeWindow, formatDays } from "./BudgetWindows";
import { resetLabel } from "../keyBudget";

const weekdays = ["mon", "tue", "wed", "thu", "fri"];
const schedule: BudgetWindowSchedule = {
  timezone: "Europe/Berlin",
  windows: [
    {
      name: "Morning",
      days: weekdays,
      start: "08:00",
      end: "13:00",
      label: "m",
    },
    {
      name: "Overnight",
      days: [...weekdays, "sat", "sun"],
      start: "18:00",
      end: "08:00",
      label: "o",
    },
  ],
};

describe("scheduled budget windows", () => {
  it("finds the open window in the schedule's timezone, including past midnight", () => {
    // Wednesday 2026-11-25 09:30 in Berlin (UTC+1).
    expect(activeWindow(schedule, new Date("2026-11-25T08:30:00Z"))?.name).toBe(
      "Morning",
    );
    // Monday 03:00 Berlin belongs to Sunday's overnight period.
    expect(activeWindow(schedule, new Date("2026-11-30T02:00:00Z"))?.name).toBe(
      "Overnight",
    );
    // Wednesday 15:00 Berlin is in no window.
    expect(activeWindow(schedule, new Date("2026-11-25T14:00:00Z"))).toBeNull();
  });

  it("summarizes days and reset periods in plain words", () => {
    expect(formatDays(weekdays)).toBe("Mon–Fri");
    expect(formatDays(["sat", "mon"])).toBe("Mon, Sat");
    expect(formatDays([...weekdays, "sat", "sun"])).toBe("Every day");
    expect(resetLabel("monthly")).toBe("resets monthly");
    expect(resetLabel("1mo")).toBe("resets monthly");
    expect(resetLabel("30d")).toBe("resets every 30 days");
  });
});
