import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { api } from "../api/client";
import type {
  BudgetWindow,
  BudgetWindowSchedule,
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

/** The window covering `now` and the minutes until it ends, or null. */
export function openWindow(
  schedule: BudgetWindowSchedule,
  now: Date,
): { window: BudgetWindow; minutesLeft: number } | null {
  const current = weekMinute(schedule.zone, now);
  for (const window of schedule.windows)
    for (const name of window.days) {
      const start =
        WEEKDAYS.indexOf(name) * DAY_MINUTES + minutes(window.start);
      const length =
        (minutes(window.end) - minutes(window.start) + DAY_MINUTES) %
          DAY_MINUTES || DAY_MINUTES;
      const end = start + length;
      if (start <= current && current < end)
        return { window, minutesLeft: end - current };
      // A period that runs past Sunday midnight continues at the week's start.
      if (end > WEEK_MINUTES && current < end - WEEK_MINUTES)
        return { window, minutesLeft: end - WEEK_MINUTES - current };
    }
  return null;
}

/** The window covering `now` in the schedule's timezone, or null. */
export function activeWindow(
  schedule: BudgetWindowSchedule,
  now: Date,
): BudgetWindow | null {
  return openWindow(schedule, now)?.window ?? null;
}

/** "2h 10m", "45m" or "1m": time until a window resets. */
export function formatLeft(minutesLeft: number): string {
  const hours = Math.floor(minutesLeft / 60);
  const rest = minutesLeft % 60;
  if (!hours) return `${Math.max(1, rest)}m`;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

function useMinuteClock(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

/** Teams page schedule: every shared window with its budget, the open one
 * raised with the time until it resets. */
export function BudgetWindowsBanner({
  schedule,
}: {
  schedule: BudgetWindowSchedule;
}) {
  const now = useMinuteClock();
  const open = openWindow(schedule, now);
  const next = open ? null : nextWindow(schedule, now);
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
        {open ? (
          <Pill tone="ok">
            Open now · resets in {formatLeft(open.minutesLeft)}
          </Pill>
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
            const isOpen = window.id === open?.window.id;
            return (
              <li
                key={window.id}
                title={window.id}
                aria-current={isOpen ? "time" : undefined}
                className={`flex min-h-11 flex-1 basis-36 flex-col items-center justify-center whitespace-nowrap rounded-[7px] px-3 py-1.5 text-center tabular-nums ${
                  isOpen
                    ? "bg-segment text-ink shadow-[0_1px_2px_rgb(0_0_0/0.12),0_0_0_0.5px_rgb(0_0_0/0.04)]"
                    : "text-ink-3"
                }`}
              >
                <span
                  className={`flex items-center gap-1.5 text-[13px] ${isOpen ? "font-semibold" : "font-medium"}`}
                >
                  {isOpen && (
                    <span
                      aria-hidden="true"
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${toneDot.ok}`}
                    />
                  )}
                  {hoursLabel(window, shared)}
                  {isOpen && <span className="sr-only"> (open now)</span>}
                </span>
                {(window.budget !== undefined || isOpen) && (
                  <span
                    className={`text-[11px] ${isOpen ? "text-ink-3" : "text-ink-4"}`}
                  >
                    {window.budget !== undefined &&
                      (window.budget == null
                        ? "Unlimited"
                        : metricValue(window.budget, "spend"))}
                    {window.budget !== undefined && isOpen && " · "}
                    {isOpen && open && `${formatLeft(open.minutesLeft)} left`}
                  </span>
                )}
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

/** "config" in grey or "custom" in blue: where a team's window cap comes from. */
function SourceTag({ source }: { source: "config" | "custom" }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-1.5 py-px text-[11px] font-medium ${
        source === "custom"
          ? "bg-blue-tint text-blue-ink"
          : "bg-well text-ink-3"
      }`}
    >
      {source}
    </span>
  );
}

/** One team row: only the window open now, with spend against its cap and the
 * time until it resets; otherwise when the next window opens and its cap. */
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
  const clock = openWindow(usage.data, now);
  // LiteLLM marks a capped open window; the clock finds an uncapped one.
  const openId =
    windows.find((window) => window.active)?.id ?? clock?.window.id;
  const open = windows.find((window) => window.id === openId);
  const shared = sharedDays(windows);
  if (!open) {
    const next = nextWindow(usage.data, now);
    const upcoming = windows.find((window) => window.id === next?.window.id);
    return (
      <div
        className="space-y-0.5 text-xs tabular-nums text-ink-4"
        title={upcoming?.id}
      >
        <p>No window open</p>
        {next && upcoming && (
          <p className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
            <span className="whitespace-nowrap">
              Next {next.day} {upcoming.start} ·{" "}
              {upcoming.max_budget != null
                ? metricValue(upcoming.max_budget, "spend")
                : "Unlimited"}
            </span>
            <SourceTag source={upcoming.source} />
          </p>
        )}
      </div>
    );
  }
  const spent = open.active ? (open.current_spend ?? 0) : 0;
  const cap = open.max_budget;
  const left =
    clock?.window.id === open.id ? formatLeft(clock.minutesLeft) : null;
  const reached = cap != null && spent >= cap;
  return (
    <div className="space-y-1 text-xs tabular-nums" title={open.id}>
      <p className="flex items-center gap-1.5 whitespace-nowrap font-semibold text-ink">
        <span
          aria-hidden="true"
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${toneDot.ok}`}
        />
        <span>
          <span className="sr-only">Open window </span>
          {hoursLabel(open, shared)}
        </span>
      </p>
      {cap != null ? (
        <>
          <p className="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5">
            <span className="whitespace-nowrap text-[13px]">
              <span className="font-semibold text-ink">
                {metricValue(spent, "spend")}
              </span>{" "}
              <span className="text-ink-4">of {metricValue(cap, "spend")}</span>
            </span>
            <SourceTag source={open.source} />
          </p>
          <UsageBar percent={cap ? (spent / cap) * 100 : 100} />
          <p className={reached ? "text-danger" : "text-ink-3"}>
            {reached
              ? "Cap reached"
              : `${metricValue(cap - spent, "spend")} left`}
            {left && ` · resets in ${left}`}
          </p>
        </>
      ) : (
        <p className="flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 text-ink-3">
          <span>
            No cap
            {left && ` · window ends in ${left}`}
          </span>
          <SourceTag source={open.source} />
        </p>
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

/** The cap a team gets in a window for a dialog choice, before saving. */
function teamCap(window: BudgetWindow, choice: WindowChoice): string {
  if (choice.mode === "unlimited") return "Team cap unlimited";
  if (choice.mode === "custom")
    return choice.amount.trim() === ""
      ? "Enter a custom cap"
      : `Team cap ${metricValue(Number(choice.amount), "spend")} · config ${capText(window.budget)}`;
  return `Team cap ${capText(window.budget)} · from config`;
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
                  </span>
                  <span className="block text-xs text-ink-4">
                    Team cap {capText(locked[window.id])}
                  </span>
                </p>
                <span className="inline-flex items-center gap-1 text-xs text-ink-3">
                  <Lock aria-hidden="true" size={12} strokeWidth={2} />
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
                  </span>
                  <span className="block text-xs text-ink-4" aria-live="polite">
                    {teamCap(window, choice)}
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
