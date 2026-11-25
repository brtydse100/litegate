import { activeWindow } from "../components/BudgetWindows";
import type {
  AdminBudgetWindows,
  BudgetWindowSchedule,
  TeamBudgetWindowUsage,
  TeamInfo,
} from "../types";

// Synthetic scheduled budget windows for the demo; no LiteLLM is involved.

const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"];

// Weekdays only, so weekends (and weekday nights) have no window cap.
function window(start: string, end: string, defaultBudget: number | null) {
  return {
    name: `Mon-Fri ${start}-${end}`,
    days: WEEKDAYS,
    start,
    end,
    label: `sched:Etc/GMT-2:${WEEKDAYS.join(",")}:${start}-${end}`,
    default_budget: defaultBudget,
  };
}

/** Administrator view, with default caps and a key reset period to warn about. */
export const demoAdminBudgetWindows: AdminBudgetWindows = {
  timezone: "UTC+2",
  zone: "Etc/GMT-2",
  windows: [
    window("08:00", "13:00", 40),
    window("13:00", "18:00", 40),
    window("18:00", "22:00", null),
  ],
  key_budget_duration: "30d",
};

/** The public portal-config copy leaves the default caps out. */
export const demoBudgetWindows: BudgetWindowSchedule = {
  timezone: demoAdminBudgetWindows.timezone,
  zone: demoAdminBudgetWindows.zone,
  windows: demoAdminBudgetWindows.windows.map((item) => ({
    name: item.name,
    days: item.days,
    start: item.start,
    end: item.end,
    label: item.label,
  })),
};

/** Seed overrides in window order; undefined follows the default, null is unlimited. */
export function demoOverrides(
  caps: (number | null | undefined)[],
): Record<string, number | null> {
  return Object.fromEntries(
    demoAdminBudgetWindows.windows.flatMap((item, index) =>
      caps[index] !== undefined ? [[item.name, caps[index]]] : [],
    ),
  );
}

/** Apply a create/update request's window_budgets to a team's overrides. */
export function applyWindowBudgets(
  team: TeamInfo,
  windowBudgets: unknown,
): TeamInfo["window_budgets"] {
  const current = { ...(team.window_budgets ?? {}) };
  if (!windowBudgets || typeof windowBudgets !== "object") return current;
  for (const [name, value] of Object.entries(windowBudgets)) {
    if (value === "default") delete current[name];
    else if (value === null || typeof value === "number") current[name] = value;
  }
  return current;
}

export function demoWindowUsage(team: TeamInfo): TeamBudgetWindowUsage {
  const open = activeWindow(demoBudgetWindows, new Date());
  const own = team.window_budgets ?? {};
  return {
    team_id: team.team_id,
    timezone: demoAdminBudgetWindows.timezone,
    zone: demoAdminBudgetWindows.zone,
    windows: demoAdminBudgetWindows.windows.map((item) => {
      const overridden = item.name in own;
      const cap = (overridden ? own[item.name] : item.default_budget) ?? null;
      const active = item.name === open?.name;
      return {
        ...item,
        max_budget: cap,
        source: overridden ? "team" : "default",
        current_spend: active && cap != null ? Math.round(cap * 37) / 100 : 0,
        active,
        next_start: null,
      };
    }),
  };
}
