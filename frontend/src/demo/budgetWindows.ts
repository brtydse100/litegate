import { activeWindow } from "../components/BudgetWindows";
import type {
  BudgetWindowSchedule,
  TeamBudgetWindowUsage,
  TeamInfo,
} from "../types";

// Synthetic scheduled budget windows for the demo; no LiteLLM is involved.

const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"];

function window(
  id: string,
  days: string[],
  start: string,
  end: string,
  budget: number | null,
) {
  return {
    id,
    days,
    start,
    end,
    label: `sched:Etc/GMT-2:${days.join(",")}:${start}-${end}`,
    budget,
  };
}

/** Administrator view, with each window's budget. Weekday nights have no window. */
export const demoAdminBudgetWindows: BudgetWindowSchedule = {
  timezone: "UTC+2",
  zone: "Etc/GMT-2",
  windows: [
    window("weekday-morning", WEEKDAYS, "08:00", "13:00", 40),
    window("weekday-afternoon", WEEKDAYS, "13:00", "18:00", 40),
    window("weekday-evening", WEEKDAYS, "18:00", "22:00", null),
    window("weekend", ["sat", "sun"], "00:00", "00:00", 10),
  ],
};

/** The public portal-config copy leaves the budgets out. */
export const demoBudgetWindows: BudgetWindowSchedule = {
  timezone: demoAdminBudgetWindows.timezone,
  zone: demoAdminBudgetWindows.zone,
  windows: demoAdminBudgetWindows.windows.map((item) => ({
    id: item.id,
    days: item.days,
    start: item.start,
    end: item.end,
    label: item.label,
  })),
};

/** Seed caps in window order; undefined follows the config, null is unlimited. */
export function demoOverrides(
  caps: (number | null | undefined)[],
): Record<string, number | null> {
  return Object.fromEntries(
    demoAdminBudgetWindows.windows.flatMap((item, index) =>
      caps[index] !== undefined ? [[item.id, caps[index]]] : [],
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
    if (name in (team.window_config ?? {})) continue;
    if (value === "config") delete current[name];
    else if (value === null || typeof value === "number") current[name] = value;
  }
  return current;
}

export function demoWindowUsage(team: TeamInfo): TeamBudgetWindowUsage {
  const open = activeWindow(demoBudgetWindows, new Date());
  const own = team.window_budgets ?? {};
  const fixed = team.window_config ?? {};
  return {
    team_id: team.team_id,
    timezone: demoAdminBudgetWindows.timezone,
    zone: demoAdminBudgetWindows.zone,
    windows: demoAdminBudgetWindows.windows.map((item) => {
      const locked = item.id in fixed;
      const custom = !locked && item.id in own;
      const cap =
        (locked ? fixed[item.id] : custom ? own[item.id] : item.budget) ?? null;
      const active = item.id === open?.id;
      return {
        ...item,
        max_budget: cap,
        source: custom ? "custom" : "config",
        locked,
        current_spend: active && cap != null ? Math.round(cap * 37) / 100 : 0,
        active,
        next_start: null,
      };
    }),
  };
}
