import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { BudgetWindow, BudgetWindowSchedule } from "../types";
import { Callout } from "./Page";
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

/** Teams page summary: only the window open now, or when the next opens. */
export function BudgetWindowsBanner({
  schedule,
}: {
  schedule: BudgetWindowSchedule;
}) {
  const now = useMinuteClock();
  const current = activeWindow(schedule, now);
  const next = current ? null : nextWindow(schedule, now);
  return (
    <Callout tone="info" title={`Budget windows (${schedule.timezone})`}>
      {current ? (
        <p>
          <span className="font-semibold">
            Open now: {windowSummary(current)}.
          </span>{" "}
          Each team&apos;s cap for this window applies until {current.end}; a
          blank cap is unlimited.
        </p>
      ) : (
        <p>
          <span className="font-semibold">No window open · no cap.</span>
          {next &&
            ` Next: ${next.day} ${next.window.start}–${next.window.end}.`}
        </p>
      )}
      <p className="mt-1 text-xs">
        Every team shares the same windows and sets its own cap per window in
        the team dialog. Spend starts at $0 when a window opens.
      </p>
    </Callout>
  );
}

/** One team row: only the open window's spend and cap, read from LiteLLM. */
export function TeamWindowUsage({ teamId }: { teamId: string }) {
  const now = useMinuteClock();
  const usage = useQuery({
    // Under "teams" so every team save also refreshes the window caps.
    queryKey: ["teams", "budget-windows", teamId],
    queryFn: () => api.teamBudgetWindows(teamId),
    staleTime: 30_000,
  });
  if (usage.isPending)
    return <p className="text-xs text-ink-4">Loading window…</p>;
  if (usage.isError)
    return <p className="text-xs text-danger">Window unavailable</p>;
  // LiteLLM marks a capped open window; an uncapped one is found by the clock.
  const openName =
    usage.data.windows.find((window) => window.active)?.name ??
    activeWindow(usage.data, now)?.name;
  const open = usage.data.windows.find((window) => window.name === openName);
  if (!open)
    return <p className="text-xs text-ink-4">No window open · no cap</p>;
  return (
    <p className="text-xs text-ink-3">
      <span className="font-semibold text-ink">
        {open.start}–{open.end}
      </span>{" "}
      {open.max_budget == null
        ? "· no cap"
        : `· ${metricValue(open.active ? (open.current_spend ?? 0) : 0, "spend")} of ${metricValue(open.max_budget, "spend")}`}
    </p>
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
