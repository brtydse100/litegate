import { useState } from "react";
import type { OrganizationUsage, UsageMetrics } from "../types/organization";
import EmailAddress from "./EmailAddress";
import { formatUsd } from "../formatUsd";

export type UsageMetric = keyof UsageMetrics;

export const metricLabels: Record<UsageMetric, string> = {
  spend: "Spend (USD)",
  tokens: "Tokens",
  requests: "Logged requests",
};

export function metricValue(value: number, metric: UsageMetric): string {
  if (metric !== "spend") return value.toLocaleString();
  return formatUsd(value);
}

const levels = ["bg-well", "bg-teal/25", "bg-teal/50", "bg-teal/75", "bg-teal"];
const weekdays = ["Mon", "", "Wed", "", "Fri", "", ""];
const tabLabels: Record<UsageMetric, string> = {
  spend: "Spend",
  requests: "Requests",
  tokens: "Tokens",
};
const units: Record<UsageMetric, string> = {
  spend: "spent",
  requests: "requests",
  tokens: "tokens",
};

type Day = OrganizationUsage["daily"][number];
const utc = (date: string) => new Date(`${date}T00:00:00Z`);
const monthName = (date: string) =>
  utc(date).toLocaleDateString(undefined, { month: "short", timeZone: "UTC" });

/** Days as weekly columns (Monday first), padded so each column is a week. */
function weeks(days: Day[]): Array<Array<Day | null>> {
  if (!days.length) return [];
  const lead = (utc(days[0].date).getUTCDay() + 6) % 7;
  const cells: Array<Day | null> = [...Array(lead).fill(null), ...days];
  const columns: Array<Array<Day | null>> = [];
  for (let index = 0; index < cells.length; index += 7)
    columns.push(cells.slice(index, index + 7));
  return columns;
}

/**
 * GitHub-style contribution history: one square per day, darker for more.
 * Metric tabs show each total; group chips rank groups by the chosen metric.
 */
export function ContributionHistory({
  daily,
  totals,
  groups = [],
  groupLabel = "group",
}: {
  daily: Day[];
  totals: UsageMetrics;
  groups?: OrganizationUsage["by_group"];
  groupLabel?: string;
}) {
  const [metric, setMetric] = useState<UsageMetric>("tokens");
  const [team, setTeam] = useState<string | null>(null);
  const ranked = groups
    .filter((group) => group.daily?.length)
    .sort((left, right) => right[metric] - left[metric]);
  const chosen = ranked.find((group) => (group.id ?? "direct") === team);
  const series = chosen?.daily ?? daily;
  const total = chosen ? chosen[metric] : totals[metric];
  const max = Math.max(0, ...series.map((day) => day[metric]));
  const level = (value: number) =>
    value <= 0 || !max ? 0 : Math.max(1, Math.ceil((value / max) * 4));
  const peak = series.reduce<Day | undefined>(
    (best, day) => (!best || day[metric] > best[metric] ? day : best),
    undefined,
  );
  const columns = weeks(series);
  let lastMonth = "";
  const monthLabels = columns.map((column) => {
    const first = column.find((day): day is Day => !!day);
    const name = first ? monthName(first.date) : "";
    if (!name || name === lastMonth) return "";
    lastMonth = name;
    return name;
  });
  const scope = chosen ? ` for ${chosen.name}` : "";
  const summary =
    max === 0 || !peak
      ? `No recorded ${units[metric]}${scope} in this period`
      : `${metricValue(total, metric)} ${units[metric]}${scope}; busiest day ${peak.date} with ${metricValue(peak[metric], metric)}`;
  const chip = (active: boolean) =>
    `inline-flex min-h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] ${
      active
        ? "border-teal bg-teal-tint font-semibold text-teal-ink"
        : "border-line-input bg-card text-ink-3 hover:text-ink"
    }`;
  return (
    <section
      aria-label="Contribution history"
      className="flex flex-col gap-4 rounded-lg border border-line bg-card p-5"
    >
      <div
        role="group"
        aria-label="Metric"
        className="grid grid-cols-3 overflow-hidden rounded-lg border border-line"
      >
        {(["spend", "requests", "tokens"] as const).map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={metric === item}
            onClick={() => setMetric(item)}
            className={`flex flex-col items-start gap-0.5 border-r border-line px-4 py-3 text-left last:border-r-0 ${
              metric === item ? "bg-canvas" : "hover:bg-canvas/60"
            }`}
          >
            <span className="text-xs text-ink-4">{tabLabels[item]}</span>
            <span className="text-lg font-semibold text-ink">
              {metricValue(totals[item], item)}
            </span>
          </button>
        ))}
      </div>
      {ranked.length > 1 && (
        <div
          role="group"
          aria-label={`Rank by ${groupLabel}`}
          className="flex flex-wrap gap-1.5"
        >
          <button
            type="button"
            aria-pressed={!chosen}
            onClick={() => setTeam(null)}
            className={chip(!chosen)}
          >
            All
          </button>
          {ranked.map((group) => (
            <button
              key={group.id ?? "direct"}
              type="button"
              aria-pressed={chosen === group}
              onClick={() => setTeam(group.id ?? "direct")}
              className={chip(chosen === group)}
            >
              {group.name}
              <span className="text-ink-4">
                {metricValue(group[metric], metric)}
              </span>
            </button>
          ))}
        </div>
      )}
      <div>
        <p className="text-sm font-semibold text-ink">
          {metricValue(total, metric)} {units[metric]}
          {scope} in this period
        </p>
        <div className="relative mt-3 overflow-x-auto">
          <div role="img" aria-label={summary} className="inline-flex gap-2">
            <div
              aria-hidden="true"
              className="grid grid-rows-[16px_repeat(7,18px)] gap-1 text-[10px] text-ink-4"
            >
              <span />
              {weekdays.map((name, index) => (
                <span key={index} className="leading-[18px]">
                  {name}
                </span>
              ))}
            </div>
            {columns.map((column, index) => (
              <div
                key={index}
                className="grid grid-rows-[16px_repeat(7,18px)] gap-1"
              >
                <span
                  aria-hidden="true"
                  className="whitespace-nowrap text-[10px] leading-4 text-ink-4"
                >
                  {monthLabels[index]}
                </span>
                {Array.from({ length: 7 }, (_, row) => {
                  const day = column[row];
                  return day ? (
                    <span
                      key={day.date}
                      title={`${day.date}: ${metricValue(day[metric], metric)}`}
                      className={`h-[18px] w-[18px] rounded-[3px] ${levels[level(day[metric])]}`}
                    />
                  ) : (
                    <span key={row} />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        <p
          aria-hidden="true"
          className="mt-3 flex items-center justify-end gap-1 text-[11px] text-ink-4"
        >
          Less
          {levels.map((tone) => (
            <span key={tone} className={`h-3 w-3 rounded-[3px] ${tone}`} />
          ))}
          More
        </p>
      </div>
    </section>
  );
}

export function UsageBars({
  title,
  values,
  metric,
  onSelect,
  emailLabels = false,
}: {
  title: string;
  values: Array<UsageMetrics & { id?: string | null; name: string }>;
  metric: UsageMetric;
  onSelect?: (id: string) => void;
  emailLabels?: boolean;
}) {
  const sorted = [...values].sort((a, b) => b[metric] - a[metric]);
  const max = Math.max(...sorted.map((row) => row[metric]), 0) || 1;
  return (
    <section className="rounded-lg border border-line bg-card p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-ink">{title}</h2>
      <div className="mt-4 space-y-4">
        {sorted.map((row) => {
          const groupId = row.id;
          const key =
            groupId == null ? `label:${row.name}` : `group:${groupId}`;
          const content = (
            <>
              <span className="flex justify-between gap-3 text-xs">
                {emailLabels && row.name.includes("@") && !onSelect ? (
                  <EmailAddress
                    email={row.name}
                    className="font-medium text-ink-2"
                  />
                ) : (
                  <span className="truncate font-medium text-ink-2">
                    {row.name}
                  </span>
                )}
                <span className="shrink-0 text-ink-4">
                  {metricValue(row[metric], metric)}
                </span>
              </span>
              <span className="mt-2 block h-2 overflow-hidden rounded-full bg-well">
                <span
                  className="block h-full rounded-full bg-blue"
                  style={{ width: `${(row[metric] / max) * 100}%` }}
                />
              </span>
            </>
          );
          return onSelect && groupId != null ? (
            <button
              key={key}
              type="button"
              aria-label={`Select ${row.name}`}
              onClick={() => onSelect(groupId)}
              className="block w-full text-left hover:opacity-75"
            >
              {content}
            </button>
          ) : (
            <div key={key}>{content}</div>
          );
        })}
        {!sorted.length && (
          <p className="text-sm text-ink-4">No recorded usage.</p>
        )}
      </div>
    </section>
  );
}
