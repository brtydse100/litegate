import { activeWindow } from "../components/BudgetWindows";
import type {
  BudgetWindowSchedule,
  TeamBudgetWindowUsage,
  TeamInfo,
} from "../types";

// Synthetic scheduled budget windows for the demo; no LiteLLM is involved.

const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"];
const EVERY_DAY = [...WEEKDAYS, "sat", "sun"];

function window(name: string, days: string[], start: string, end: string) {
  return {
    name,
    days,
    start,
    end,
    label: `sched:Europe/Berlin:${days.join(",")}:${start}-${end}`,
  };
}

export const demoBudgetWindows: BudgetWindowSchedule = {
  timezone: "Europe/Berlin",
  windows: [
    window("Morning", WEEKDAYS, "08:00", "13:00"),
    window("Afternoon", WEEKDAYS, "13:00", "18:00"),
    window("Overnight", EVERY_DAY, "18:00", "08:00"),
  ],
};

/** Seed caps by window name; a missing name is unlimited. */
export function demoBudgetLimits(
  caps: Record<string, number>,
): TeamInfo["budget_limits"] {
  return demoBudgetWindows.windows
    .filter((item) => caps[item.name] != null)
    .map((item) => ({
      budget_duration: item.label,
      max_budget: caps[item.name],
    }));
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
  const caps: Record<string, number> = {};
  for (const item of demoBudgetWindows.windows) {
    const requested = (windowBudgets as Record<string, unknown>)[item.name];
    const value = requested === undefined ? current[item.label] : requested;
    if (typeof value === "number") caps[item.name] = value;
  }
  return demoBudgetLimits(caps);
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
