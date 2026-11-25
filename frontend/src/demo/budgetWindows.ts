import { activeWindow } from "../components/BudgetWindows";
import type {
  BudgetWindowSchedule,
  TeamBudgetWindowUsage,
  TeamInfo,
} from "../types";

// Synthetic scheduled budget windows for the demo; no LiteLLM is involved.

const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"];

// Weekdays only, so weekends (and weekday nights) have no window cap.
function window(days: string[], start: string, end: string) {
  return {
    name: `Mon-Fri ${start}-${end}`,
    days,
    start,
    end,
    label: `sched:Europe/Berlin:${days.join(",")}:${start}-${end}`,
  };
}

export const demoBudgetWindows: BudgetWindowSchedule = {
  timezone: "Europe/Berlin",
  windows: [
    window(WEEKDAYS, "08:00", "13:00"),
    window(WEEKDAYS, "13:00", "18:00"),
    window(WEEKDAYS, "18:00", "22:00"),
  ],
};

/** Seed caps in window order; null is unlimited. */
export function demoBudgetLimits(
  caps: (number | null)[],
): TeamInfo["budget_limits"] {
  return demoBudgetWindows.windows.flatMap((item, index) =>
    caps[index] != null
      ? [{ budget_duration: item.label, max_budget: caps[index] }]
      : [],
  );
}

/** Apply a create/update request's window_budgets to a team's budget_limits. */
export function applyWindowBudgets(
  team: TeamInfo,
  windowBudgets: unknown,
): TeamInfo["budget_limits"] {
  if (!windowBudgets || typeof windowBudgets !== "object")
    return team.budget_limits;
  const current = Object.fromEntries(
    (team.budget_limits ?? []).map((limit) => [
      limit.budget_duration,
      limit.max_budget,
    ]),
  );
  return demoBudgetLimits(
    demoBudgetWindows.windows.map((item) => {
      const requested = (windowBudgets as Record<string, unknown>)[item.name];
      const value = requested === undefined ? current[item.label] : requested;
      return typeof value === "number" ? value : null;
    }),
  );
}

export function demoWindowUsage(team: TeamInfo): TeamBudgetWindowUsage {
  const open = activeWindow(demoBudgetWindows, new Date());
  return {
    team_id: team.team_id,
    timezone: demoBudgetWindows.timezone,
    windows: demoBudgetWindows.windows.map((item) => {
      const cap =
        team.budget_limits?.find(
          (limit) => limit.budget_duration === item.label,
        )?.max_budget ?? null;
      const active = item.name === open?.name;
      return {
        ...item,
        max_budget: cap,
        current_spend: active && cap != null ? Math.round(cap * 37) / 100 : 0,
        active,
        next_start: null,
      };
    }),
  };
}
