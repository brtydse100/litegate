import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { BudgetWindow, BudgetWindowSchedule } from "../types";
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
  const current = weekMinute(schedule.timezone, now);
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
  const current = weekMinute(schedule.timezone, now);
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
}: {
  schedule: BudgetWindowSchedule;
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
          Each team sets its own cap per window in the team dialog; a blank cap
          is unlimited. Spend starts at $0 when a window opens, and outside
          these hours there is no cap.
        </p>
      </div>
    </section>
  );
}

/** One team row: every window's cap, the open one marked with its spend. */
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
  if (usage.data.windows.every((window) => window.max_budget == null))
    return <p className="text-xs text-ink-4">No window caps</p>;
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
                  : "No cap"}
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

/** Team editor: one amount per shared window; blank is unlimited. */
export function WindowBudgetFields({
  schedule,
  values,
  onChange,
}: {
  schedule: BudgetWindowSchedule;
  values: Record<string, string>;
  onChange: (name: string, value: string) => void;
}) {
  const shared = sharedDays(schedule.windows);
  return (
    <fieldset className="space-y-2 rounded-lg border border-line p-3 sm:col-span-2">
      <legend className="px-1 text-xs font-semibold text-ink-2">
        Budget per window (USD{shared ? `, ${shared}` : ""}, {schedule.timezone}
        )
      </legend>
      <p className="text-xs text-ink-4">
        The windows are shared by every team. Leave an amount empty for
        unlimited in that window.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {schedule.windows.map((window) => (
          <NumericPolicyInput
            key={window.name}
            label={hoursLabel(window, shared)}
            value={values[window.name] ?? ""}
            onValueChange={(value) => onChange(window.name, value)}
            step="any"
            placeholder="Unlimited"
          />
        ))}
      </div>
    </fieldset>
  );
}
