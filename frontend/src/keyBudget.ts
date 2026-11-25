import type { KeyInfo } from "./types";

const DAY_MS = 86_400_000;

/** Parse LiteLLM budget durations such as `30s`, `12h`, `30d`, `1w` or `1mo`. */
export function durationDays(value?: string | null): number | null {
  const match = value?.trim().match(/^(\d+(?:\.\d+)?)\s*(s|m|h|d|w|mo)$/i);
  if (!match) return null;
  const amount = Number(match[1]);
  const unit = match[2].toLowerCase();
  const days =
    unit === "s"
      ? amount / 86_400
      : unit === "m"
        ? amount / 1_440
        : unit === "h"
          ? amount / 24
          : unit === "d"
            ? amount
            : unit === "w"
              ? amount * 7
              : amount * 30;
  return days > 0 ? days : null;
}

/** Human-readable period, e.g. `30 days` or `1 month`. */
const RESET_WORDS: Record<string, string> = {
  daily: "daily",
  weekly: "weekly",
  monthly: "monthly",
  "1d": "daily",
  "24h": "daily",
  "1w": "weekly",
  "1mo": "monthly",
  "12mo": "yearly",
};

/** Team row reset text: "resets monthly", "resets every 30 days". */
export function resetLabel(duration: string): string {
  const word = RESET_WORDS[duration.trim().toLowerCase()];
  if (word) return `resets ${word}`;
  const label = durationLabel(duration);
  return label ? `resets every ${label}` : "resets on a schedule";
}

export function durationLabel(value?: string | null): string | null {
  const match = value?.trim().match(/^(\d+)\s*(s|m|h|d|w|mo)$/i);
  if (!match) return value?.trim() || null;
  const amount = Number(match[1]);
  const names: Record<string, string> = {
    s: "second",
    m: "minute",
    h: "hour",
    d: "day",
    w: "week",
    mo: "month",
  };
  const name = names[match[2].toLowerCase()];
  return `${amount} ${name}${amount === 1 ? "" : "s"}`;
}

/** LiteLLM may omit the timezone; the backend interprets those values as UTC. */
export function parseLiteLLMDate(value: string) {
  const timestamp = value.replace(" ", "T");
  return new Date(
    timestamp.includes("T") && !/(?:Z|[+-]\d{2}(?::?\d{2})?)$/i.test(timestamp)
      ? `${timestamp}Z`
      : timestamp,
  );
}

/** A key stops working at its expiry instant; invalid dates never expire it. */
export function isKeyExpired(
  expires?: string | null,
  now = Date.now(),
): boolean {
  return !!expires && parseLiteLLMDate(expires).getTime() <= now;
}

export interface BudgetSummary {
  managed: boolean;
  available: boolean;
  spent: number;
  budget: number | null;
  left: number | null;
  /** Fraction of the budget still available, 0–1. */
  remaining: number | null;
  periodLabel: string | null;
  resetAt: Date | null;
  daysUntilReset: number | null;
  perDay: number | null;
  onTrack: boolean | null;
}

export function budgetSummary(key: KeyInfo, now = Date.now()): BudgetSummary {
  const managed = !!key.organization_managed || !!key.organization_path;
  const available = !managed || key.user_budget_available !== false;
  const spent = key.user_spend ?? key.spend ?? 0;
  const budget = (managed ? key.user_budget : key.max_budget) ?? null;
  const left = budget == null ? null : Math.max(0, budget - spent);
  const remaining =
    budget == null || left == null
      ? null
      : budget <= 0
        ? 0
        : Math.min(1, left / budget);
  const periodDays = durationDays(key.budget_duration);
  const resetDate = key.budget_reset_at
    ? parseLiteLLMDate(key.budget_reset_at)
    : null;
  const resetAt =
    resetDate && !Number.isNaN(resetDate.getTime()) ? resetDate : null;
  const daysUntilReset =
    resetAt && resetAt.getTime() > now
      ? Math.ceil((resetAt.getTime() - now) / DAY_MS)
      : null;
  let perDay: number | null = null;
  let onTrack: boolean | null = null;
  // A daily pace is meaningless for periods shorter than a day.
  if (periodDays && periodDays >= 1 && resetAt) {
    const start = resetAt.getTime() - periodDays * DAY_MS;
    const elapsedDays = Math.max((now - start) / DAY_MS, 1);
    if (now >= start && elapsedDays <= periodDays + 1) {
      perDay = spent / elapsedDays;
      if (budget != null) onTrack = perDay * periodDays <= budget;
    }
  }
  return {
    managed,
    available,
    spent,
    budget,
    left,
    remaining,
    periodLabel: durationLabel(key.budget_duration),
    resetAt,
    daysUntilReset,
    perDay,
    onTrack,
  };
}

/** Allowed model names; `null` means every model on the gateway. */
export function allowedModels(models?: string[] | null): string[] | null {
  const named = (models ?? []).filter(Boolean);
  if (!named.length || named.includes("all-proxy-models")) return null;
  return [...new Set(named)].sort((left, right) => left.localeCompare(right));
}
