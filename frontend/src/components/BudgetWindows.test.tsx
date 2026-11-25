import { describe, expect, it } from "vitest";
import type { BudgetWindowSchedule } from "../types";
import {
  activeWindow,
  choicePayload,
  formatDays,
  initialChoices,
  nextWindow,
} from "./BudgetWindows";
import { resetLabel } from "../keyBudget";

const weekdays = ["mon", "tue", "wed", "thu", "fri"];
const schedule: BudgetWindowSchedule = {
  timezone: "Europe/Berlin",
  zone: "Europe/Berlin",
  windows: [
    {
      id: "Morning",
      days: weekdays,
      start: "08:00",
      end: "13:00",
      label: "m",
    },
    {
      id: "Overnight",
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
    expect(activeWindow(schedule, new Date("2026-11-25T08:30:00Z"))?.id).toBe(
      "Morning",
    );
    // Monday 03:00 Berlin belongs to Sunday's overnight period.
    expect(activeWindow(schedule, new Date("2026-11-30T02:00:00Z"))?.id).toBe(
      "Overnight",
    );
    // Wednesday 15:00 Berlin is in no window.
    expect(activeWindow(schedule, new Date("2026-11-25T14:00:00Z"))).toBeNull();
  });

  it("names the next window to open", () => {
    // Wednesday 15:00 Berlin: the overnight window opens at 18:00 the same day.
    const next = nextWindow(schedule, new Date("2026-11-25T14:00:00Z"));
    expect(next?.window.id).toBe("Overnight");
    expect(next?.day).toBe("Wed");
    // Saturday 10:00 Berlin with weekday mornings only: next is Monday.
    const weekdays = { ...schedule, windows: [schedule.windows[0]] };
    expect(nextWindow(weekdays, new Date("2026-11-28T09:00:00Z"))?.day).toBe(
      "Mon",
    );
  });

  it("runs a UTC+2 schedule on the fixed Etc/GMT-2 clock", () => {
    const fixed = { ...schedule, timezone: "UTC+2", zone: "Etc/GMT-2" };
    // Wednesday 06:30 UTC is 08:30 at UTC+2, in the morning window.
    expect(activeWindow(fixed, new Date("2026-11-25T06:30:00Z"))?.id).toBe(
      "Morning",
    );
    expect(activeWindow(fixed, new Date("2026-11-25T11:30:00Z"))).toBeNull();
  });

  it("turns dialog choices into window_budgets and back", () => {
    const team = {
      team_id: "t",
      models: [],
      blocked: false,
      members_with_roles: [],
      mapped_groups: [],
      default_key_team: false,
      window_budgets: { Morning: 7, Overnight: null },
    };
    const choices = initialChoices(schedule, team);
    expect(choices).toEqual({
      Morning: { mode: "custom", amount: "7" },
      Overnight: { mode: "unlimited" },
    });
    expect(choicePayload(choices)).toEqual({ Morning: 7, Overnight: null });
    expect(choicePayload(initialChoices(schedule, null))).toEqual({
      Morning: "config",
      Overnight: "config",
    });
    // Windows set in configuration for the team are never sent.
    expect(choicePayload(choices, { Overnight: 4 })).toEqual({ Morning: 7 });
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
