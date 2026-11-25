import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type {
  BudgetWindow,
  BudgetWindowSchedule,
  TeamBudgetWindowUsage,
  TeamInfo,
  WindowBudgets,
} from "../types";
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

/** "08:00–13:00", or "all day" for a window that runs a full 24 hours. */
function hourRange(window: BudgetWindow): string {
  return window.start === window.end
    ? "all day"
    : `${window.start}–${window.end}`;
}

export function windowSummary(window: BudgetWindow): string {
  return `${formatDays(window.days)} ${hourRange(window)}`;
}

/** Days every window shares ("Mon–Fri"), or null when they differ. */
export function sharedDays(windows: BudgetWindow[]): string | null {
  const days = new Set(windows.map((window) => formatDays(window.days)));
  return days.size === 1 ? [...days][0] : null;
}

/** "08:00–13:00" when the days are shown once elsewhere, else with days. */
function hoursLabel(window: BudgetWindow, shared: string | null): string {
  return shared ? hourRange(window) : windowSummary(window);
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
            const open = window.id === current?.id;
            return (
              <li
                key={window.id}
                title={window.id}
                aria-current={open ? "time" : undefined}
                className={`flex min-h-9 flex-1 basis-32 items-center justify-center gap-2 whitespace-nowrap rounded-[7px] px-3 text-[13px] tabular-nums ${
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
          Every team follows these windows. Caps come from the configuration
          unless a team has a custom cap from the team dialog. Spend starts at
          $0 when a window opens, and outside these hours there is no cap.
        </p>
      </div>
    </section>
  );
}

function capLabel(window: TeamBudgetWindowUsage["windows"][number]): string {
  const cap =
    window.max_budget != null
      ? metricValue(window.max_budget, "spend")
      : "Unlimited";
  return `${cap} · ${window.source}`;
}

/** One team row: only the window open now, with its cap, where the cap comes
 * from and the spend so far; otherwise when the next window opens. */
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
  const windows = usage.data.windows;
  // LiteLLM marks a capped open window; an uncapped one is found by the clock.
  const openId =
    windows.find((window) => window.active)?.id ??
    activeWindow(usage.data, now)?.id;
  const open = windows.find((window) => window.id === openId);
  const shared = sharedDays(windows);
  if (!open) {
    const next = nextWindow(usage.data, now);
    const upcoming = windows.find((window) => window.id === next?.window.id);
    return (
      <p className="text-xs tabular-nums text-ink-4" title={upcoming?.id}>
        No window open
        {next && upcoming && (
          <>
            {" "}
            · next {next.day} {upcoming.start}{" "}
            <span className="whitespace-nowrap">({capLabel(upcoming)})</span>
          </>
        )}
      </p>
    );
  }
  const spent = open.active ? (open.current_spend ?? 0) : 0;
  return (
    <div className="text-xs tabular-nums" title={open.id}>
      <p className="flex flex-wrap items-center gap-x-1.5 font-semibold text-ink">
        <span
          aria-hidden="true"
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${toneDot.ok}`}
        />
        <span>
          <span className="sr-only">Open window </span>
          {hoursLabel(open, shared)}
        </span>
        <span className="whitespace-nowrap font-normal text-ink-3">
          · {capLabel(open)}
        </span>
      </p>
      {open.max_budget != null && (
        <div className="mb-1 ml-3 mt-1">
          <UsageBar
            percent={open.max_budget ? (spent / open.max_budget) * 100 : 100}
          />
          <p className="mt-0.5 text-ink-3">
            {metricValue(spent, "spend")} spent
          </p>
        </div>
      )}
    </div>
  );
}

export type WindowChoice =
  | { mode: "config" }
  | { mode: "unlimited" }
  | { mode: "custom"; amount: string };

/** The dialog's starting choice per window, from the team's custom caps. */
export function initialChoices(
  schedule: BudgetWindowSchedule,
  team: TeamInfo | null,
): Record<string, WindowChoice> {
  const own = team?.window_budgets ?? {};
  return Object.fromEntries(
    schedule.windows.map((window): [string, WindowChoice] => {
      if (!(window.id in own)) return [window.id, { mode: "config" }];
      const amount = own[window.id];
      return [
        window.id,
        amount == null
          ? { mode: "unlimited" }
          : { mode: "custom", amount: String(amount) },
      ];
    }),
  );
}

/** The request's window_budgets; windows set in configuration are not sent. */
export function choicePayload(
  choices: Record<string, WindowChoice>,
  locked: Record<string, number | null> = {},
): WindowBudgets {
  return Object.fromEntries(
    Object.entries(choices)
      .filter(([name]) => !(name in locked))
      .map(([name, choice]) => [
        name,
        choice.mode === "config"
          ? "config"
          : choice.mode === "unlimited"
            ? null
            : Number(choice.amount),
      ]),
  );
}

const CHOICES: { mode: WindowChoice["mode"]; label: string }[] = [
  { mode: "config", label: "Config" },
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

function capText(cap: number | null | undefined): string {
  return cap === undefined
    ? "…"
    : cap == null
      ? "unlimited"
      : metricValue(cap, "spend");
}

/** Team editor: per shared window, the configured cap, a custom cap or
 * unlimited. Windows the configuration sets for this team are read-only. */
export function WindowBudgetFields({
  schedule,
  values,
  locked = {},
  onChange,
}: {
  schedule: BudgetWindowSchedule;
  values: Record<string, WindowChoice>;
  /** Caps the configuration sets for this team (team_budgets). */
  locked?: Record<string, number | null>;
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
        configured cap unless you choose a custom cap or unlimited here.
      </p>
      <ul className="divide-y divide-line-soft">
        {schedule.windows.map((window) => {
          const hours = hoursLabel(window, shared);
          if (window.id in locked)
            return (
              <li
                key={window.id}
                className="flex flex-wrap items-center justify-between gap-2 py-2.5 last:pb-0"
              >
                <p className="text-[13px] tabular-nums text-ink">
                  <span className="font-medium" title={window.id}>
                    {hours}
                  </span>{" "}
                  <span className="text-xs text-ink-4">
                    {capText(locked[window.id])}
                  </span>
                </p>
                <span className="text-xs text-ink-3">
                  Set in config for this team
                </span>
              </li>
            );
          const choice = values[window.id] ?? { mode: "config" };
          return (
            <li key={window.id} className="space-y-2 py-2.5 last:pb-0">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[13px] tabular-nums text-ink">
                  <span className="font-medium" title={window.id}>
                    {hours}
                  </span>{" "}
                  <span className="text-xs text-ink-4">
                    config {capText(window.budget)}
                  </span>
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
                          window.id,
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
                    onChange(window.id, { mode: "custom", amount })
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
