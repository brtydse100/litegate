import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type {
  BudgetWindow,
  BudgetWindowSchedule,
  TeamInfo,
  WindowBudgets,
} from "../types";
import { resetLabel } from "../keyBudget";
import { Pill, UsageBar } from "./Page";
import { card, cardHeader, cardTitle, toneDot } from "./ui";
import { metricValue } from "./OrganizationCharts";
import { NumericPolicyInput } from "./PolicySettings";

// Scheduled budget windows (nightly; needs LiteLLM with BerriAI/litellm#54147).

const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const DAY_MINUTES = 24 * 60;
const WEEK_MINUTES = 7 * DAY_MINUTES;

function minutes(value: string): number {
  const [hours, mins] = value.split(":").map(Number);
  return hours * 60 + mins;
}

function dayName(day: string): string {
  return day.charAt(0).toUpperCase() + day.slice(1);
}

/** "Mon–Fri", "Every day" or "Mon, Wed, Sat". */
export function formatDays(days: string[]): string {
  const indexes = days.map((day) => WEEKDAYS.indexOf(day)).sort();
  if (indexes.length === 7) return "Every day";
  const contiguous = indexes.every(
    (value, position) => position === 0 || value === indexes[position - 1] + 1,
  );
  if (contiguous && indexes.length >= 3)
    return `${dayName(WEEKDAYS[indexes[0]])}–${dayName(WEEKDAYS[indexes[indexes.length - 1]])}`;
  return indexes.map((index) => dayName(WEEKDAYS[index])).join(", ");
}

export function windowSummary(window: BudgetWindow): string {
  return `${formatDays(window.days)} ${window.start}–${window.end}`;
}

/** Days every window shares ("Mon–Fri"), or null when they differ. */
export function sharedDays(windows: BudgetWindow[]): string | null {
  const days = new Set(windows.map((window) => formatDays(window.days)));
  return days.size === 1 ? [...days][0] : null;
}

/** "08:00–13:00" when the days are shown once elsewhere, else with days. */
function hoursLabel(window: BudgetWindow, shared: string | null): string {
  return shared ? `${window.start}–${window.end}` : windowSummary(window);
}

/** Minutes since Monday 00:00 in the schedule's timezone. */
function weekMinute(timezone: string, now: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const part = (type: string) =>
    parts.find((item) => item.type === type)?.value ?? "";
  const day = WEEKDAYS.indexOf(part("weekday").slice(0, 3).toLowerCase());
  return day * DAY_MINUTES + Number(part("hour")) * 60 + Number(part("minute"));
}

/** The next window to open after `now`, and the weekday it opens on. */
export function nextWindow(
  schedule: BudgetWindowSchedule,
  now: Date,
): { window: BudgetWindow; day: string } | null {
  const current = weekMinute(schedule.zone, now);
  let best: { window: BudgetWindow; day: string; wait: number } | null = null;
  for (const window of schedule.windows)
    for (const day of window.days) {
      const start = WEEKDAYS.indexOf(day) * DAY_MINUTES + minutes(window.start);
      const wait =
        (start - current + WEEK_MINUTES) % WEEK_MINUTES || WEEK_MINUTES;
      if (!best || wait < best.wait) best = { window, day, wait };
    }
  return best && { window: best.window, day: dayName(best.day) };
}

/** The window covering `now` in the schedule's timezone, or null. */
export function activeWindow(
  schedule: BudgetWindowSchedule,
  now: Date,
): BudgetWindow | null {
  const current = weekMinute(schedule.zone, now);
  return (
    schedule.windows.find((window) =>
      window.days.some((name) => {
        const start =
          WEEKDAYS.indexOf(name) * DAY_MINUTES + minutes(window.start);
        const length =
          (minutes(window.end) - minutes(window.start) + DAY_MINUTES) %
            DAY_MINUTES || DAY_MINUTES;
        const end = start + length;
        return (
          (start <= current && current < end) ||
          (end > WEEK_MINUTES && current < end - WEEK_MINUTES)
        );
      }),
    ) ?? null
  );
}

function useMinuteClock(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

/** Teams page schedule: every shared window, with the open one raised. */
export function BudgetWindowsBanner({
  schedule,
  keyResetPeriod,
}: {
  schedule: BudgetWindowSchedule;
  /** KEY_BUDGET_DURATION, which still zeroes key totals. */
  keyResetPeriod?: string | null;
}) {
  const now = useMinuteClock();
  const current = activeWindow(schedule, now);
  const next = current ? null : nextWindow(schedule, now);
  const shared = sharedDays(schedule.windows);
  return (
    <section aria-labelledby="budget-windows-title" className={card}>
      <header className={cardHeader}>
        <div className="min-w-0">
          <h2 id="budget-windows-title" className={cardTitle}>
            Budget windows
          </h2>
          <p className="text-xs text-ink-4">
            {shared ? `${shared} · ` : ""}
            {schedule.timezone}
          </p>
        </div>
        {current ? (
          <Pill tone="ok">Open now · until {current.end}</Pill>
        ) : (
          <Pill>
            No window open
            {next && ` · next ${next.day} ${next.window.start}`}
          </Pill>
        )}
      </header>
      <div className="px-5 py-4">
        <ol className="flex flex-wrap gap-1 rounded-[10px] bg-well p-1">
          {schedule.windows.map((window) => {
            const open = window.name === current?.name;
            return (
              <li
                key={window.name}
                aria-current={open ? "time" : undefined}
                className={`flex min-h-9 flex-1 basis-32 items-center justify-center gap-2 rounded-[7px] px-3 text-[13px] tabular-nums ${
                  open
                    ? "bg-segment font-semibold text-ink shadow-[0_1px_2px_rgb(0_0_0/0.12),0_0_0_0.5px_rgb(0_0_0/0.04)]"
                    : "font-medium text-ink-3"
                }`}
              >
                {open && (
                  <span
                    aria-hidden="true"
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${toneDot.ok}`}
                  />
                )}
                {hoursLabel(window, shared)}
                {open && <span className="sr-only"> (open now)</span>}
              </li>
            );
          })}
        </ol>
        <p className="mt-3 text-xs text-ink-4">
          Every team follows these windows. Each window has a default cap that a
          team can override in the team dialog. Spend starts at $0 when a window
          opens, and outside these hours there is no cap.
        </p>
        {keyResetPeriod && (
          <p className="mt-2 flex items-start gap-1.5 text-xs text-orange-ink">
            <span
              aria-hidden="true"
              className={`mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full ${toneDot.warn}`}
            />
            <span>
              Each key&apos;s total still {resetLabel(keyResetPeriod)}{" "}
              (KEY_BUDGET_DURATION). Windows never reset totals.
            </span>
          </p>
        )}
      </div>
    </section>
  );
}

/** One team row: every window's cap and whether it is the default, the open
 * one marked with its spend. */
export function TeamWindowUsage({ teamId }: { teamId: string }) {
  const now = useMinuteClock();
  const usage = useQuery({
    // Under "teams" so every team save also refreshes the window caps.
    queryKey: ["teams", "budget-windows", teamId],
    queryFn: () => api.teamBudgetWindows(teamId),
    staleTime: 30_000,
  });
  if (usage.isPending)
    return <p className="text-xs text-ink-4">Loading windows…</p>;
  if (usage.isError)
    return <p className="text-xs text-danger">Windows unavailable</p>;
  // LiteLLM marks a capped open window; an uncapped one is found by the clock.
  const openName =
    usage.data.windows.find((window) => window.active)?.name ??
    activeWindow(usage.data, now)?.name;
  const shared = sharedDays(usage.data.windows);
  return (
    <ul
      className="mt-0.5 space-y-0.5 text-xs tabular-nums"
      aria-label="Budget windows"
    >
      {usage.data.windows.map((window) => {
        const open = window.name === openName;
        const spent = open && window.active ? (window.current_spend ?? 0) : 0;
        const capped = window.max_budget != null;
        return (
          <li key={window.name}>
            <span className="flex items-center justify-between gap-2 whitespace-nowrap">
              <span
                className={`flex items-center gap-1.5 ${open ? "font-semibold text-ink" : "text-ink-4"}`}
              >
                <span
                  aria-hidden="true"
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${open ? toneDot.ok : "bg-transparent"}`}
                />
                {hoursLabel(window, shared)}
                {open && <span className="sr-only"> (open now)</span>}
              </span>
              <span className={open ? "font-semibold text-ink" : "text-ink-4"}>
                {capped
                  ? metricValue(window.max_budget ?? 0, "spend")
                  : "Unlimited"}
                {window.source === "default" && (
                  <span className="font-normal text-ink-4"> · default</span>
                )}
              </span>
            </span>
            {open && capped && (
              <span className="mb-1 ml-3 mt-1 block">
                <UsageBar
                  percent={
                    window.max_budget ? (spent / window.max_budget) * 100 : 100
                  }
                />
                <span className="mt-0.5 block text-ink-3">
                  {metricValue(spent, "spend")} spent
                </span>
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export type WindowChoice =
  | { mode: "default" }
  | { mode: "unlimited" }
  | { mode: "custom"; amount: string };

/** The dialog's starting choice per window, from the team's overrides. */
export function initialChoices(
  schedule: BudgetWindowSchedule,
  team: TeamInfo | null,
): Record<string, WindowChoice> {
  const own = team?.window_budgets ?? {};
  return Object.fromEntries(
    schedule.windows.map((window): [string, WindowChoice] => {
      if (!(window.name in own)) return [window.name, { mode: "default" }];
      const amount = own[window.name];
      return [
        window.name,
        amount == null
          ? { mode: "unlimited" }
          : { mode: "custom", amount: String(amount) },
      ];
    }),
  );
}

/** The request's window_budgets. */
export function choicePayload(
  choices: Record<string, WindowChoice>,
): WindowBudgets {
  return Object.fromEntries(
    Object.entries(choices).map(([name, choice]) => [
      name,
      choice.mode === "default"
        ? "default"
        : choice.mode === "unlimited"
          ? null
          : Number(choice.amount),
    ]),
  );
}

const CHOICES: { mode: WindowChoice["mode"]; label: string }[] = [
  { mode: "default", label: "Default" },
  { mode: "custom", label: "Custom" },
  { mode: "unlimited", label: "Unlimited" },
];

function segment(active: boolean): string {
  return `min-h-7 flex-1 whitespace-nowrap rounded-md px-2.5 text-xs font-medium transition-colors duration-150 ${
    active
      ? "bg-segment text-ink shadow-[0_1px_2px_rgb(0_0_0/0.12),0_0_0_0.5px_rgb(0_0_0/0.04)]"
      : "text-ink-3 hover:text-ink"
  }`;
}

/** Team editor: per shared window, follow the default, a custom cap or unlimited. */
export function WindowBudgetFields({
  schedule,
  values,
  onChange,
}: {
  schedule: BudgetWindowSchedule;
  values: Record<string, WindowChoice>;
  onChange: (name: string, value: WindowChoice) => void;
}) {
  const shared = sharedDays(schedule.windows);
  return (
    <fieldset className="space-y-2 rounded-lg border border-line p-3 sm:col-span-2">
      <legend className="px-1 text-xs font-semibold text-ink-2">
        Budget per window (USD{shared ? `, ${shared}` : ""}, {schedule.timezone}
        )
      </legend>
      <p className="text-xs text-ink-4">
        Every team shares these windows. A team follows each window&apos;s
        default cap unless you choose a custom cap or unlimited here.
      </p>
      <ul className="divide-y divide-line-soft">
        {schedule.windows.map((window) => {
          const choice = values[window.name] ?? { mode: "default" };
          const hours = hoursLabel(window, shared);
          const fallback =
            window.default_budget === undefined
              ? "…"
              : window.default_budget == null
                ? "unlimited"
                : metricValue(window.default_budget, "spend");
          return (
            <li key={window.name} className="space-y-2 py-2.5 last:pb-0">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[13px] tabular-nums text-ink">
                  <span className="font-medium">{hours}</span>{" "}
                  <span className="text-xs text-ink-4">default {fallback}</span>
                </p>
                <div
                  role="group"
                  aria-label={`Cap for ${hours}`}
                  className="flex w-full items-center rounded-lg bg-ink/[0.06] p-0.5 sm:w-auto"
                >
                  {CHOICES.map((item) => (
                    <button
                      key={item.mode}
                      type="button"
                      aria-pressed={choice.mode === item.mode}
                      className={segment(choice.mode === item.mode)}
                      onClick={() =>
                        choice.mode !== item.mode &&
                        onChange(
                          window.name,
                          item.mode === "custom"
                            ? { mode: "custom", amount: "" }
                            : { mode: item.mode },
                        )
                      }
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
              {choice.mode === "custom" && (
                <NumericPolicyInput
                  label={`Custom cap for ${hours} (USD)`}
                  value={choice.amount}
                  onValueChange={(amount) =>
                    onChange(window.name, { mode: "custom", amount })
                  }
                  step="any"
                  required
                />
              )}
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}
