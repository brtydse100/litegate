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

/** The window covering `now` in the schedule's timezone, or null. */
export function activeWindow(
  schedule: BudgetWindowSchedule,
  now: Date,
): BudgetWindow | null {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: schedule.timezone,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const part = (type: string) =>
    parts.find((item) => item.type === type)?.value ?? "";
  const day = WEEKDAYS.indexOf(part("weekday").slice(0, 3).toLowerCase());
  const current =
    day * DAY_MINUTES + Number(part("hour")) * 60 + Number(part("minute"));
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

/** Teams page summary of the shared schedule and the window open right now. */
export function BudgetWindowsBanner({
  schedule,
}: {
  schedule: BudgetWindowSchedule;
}) {
  const current = activeWindow(schedule, useMinuteClock());
  return (
    <Callout tone="info" title={`Budget windows (${schedule.timezone})`}>
      <p>
        Every team shares these windows. Each team sets its own amount per
        window; a blank amount is unlimited. Spend starts at $0 when a window
        opens, and outside every window no window cap applies.
      </p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {schedule.windows.map((window) => {
          const open = window.name === current?.name;
          return (
            <li
              key={window.name}
              className={`rounded-md border px-2 py-1 text-xs ${open ? "border-blue bg-card font-semibold text-blue-ink" : "border-line bg-card text-ink-2"}`}
            >
              {window.name} · {windowSummary(window)}
              {open && " · open now"}
            </li>
          );
        })}
      </ul>
      {!current && (
        <p className="mt-2 text-xs">
          No window is open right now, so no window caps apply.
        </p>
      )}
    </Callout>
  );
}

/** One team row's spend and cap in each window, read from LiteLLM. */
export function TeamWindowUsage({ teamId }: { teamId: string }) {
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
  return (
    <ul className="space-y-0.5 text-xs text-ink-3">
      {usage.data.windows.map((window) => (
        <li key={window.name}>
          <span className={window.active ? "font-semibold text-ink" : ""}>
            {window.name}
          </span>{" "}
          {window.max_budget == null
            ? "· unlimited"
            : window.active
              ? `· ${metricValue(window.current_spend ?? 0, "spend")} of ${metricValue(window.max_budget, "spend")}`
              : `· ${metricValue(window.max_budget, "spend")} cap`}
          {window.active && <span className="text-blue-ink"> · open</span>}
        </li>
      ))}
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
  return (
    <fieldset className="space-y-2 rounded-lg border border-line p-3 sm:col-span-2">
      <legend className="px-1 text-xs font-semibold text-ink-2">
        Budget per window (USD, {schedule.timezone})
      </legend>
      <p className="text-xs text-ink-4">
        The windows are shared by every team. Leave an amount empty for
        unlimited in that window.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {schedule.windows.map((window) => (
          <NumericPolicyInput
            key={window.name}
            label={`${window.name} (${windowSummary(window)})`}
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
