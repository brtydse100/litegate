import type React from "react";
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

type Day = OrganizationUsage["daily"][number];

const shortDate = (date: string) =>
  new Date(`${date}T00:00:00Z`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });

/** Daily usage summed into weeks, labelled by each week's first day. */
export function weekly(daily: Day[], metric: UsageMetric) {
  const weeks: Array<{ label: string; value: number; title: string }> = [];
  for (let index = 0; index < daily.length; index += 7) {
    const days = daily.slice(index, index + 7);
    const value = days.reduce((sum, day) => sum + day[metric], 0);
    const first = days[0].date;
    const last = days[days.length - 1].date;
    weeks.push({
      label: shortDate(first),
      value,
      title: `${shortDate(first)} – ${shortDate(last)}: ${metricValue(value, metric)}`,
    });
  }
  return weeks;
}

export interface StatTile {
  caption: string;
  value: string;
  sub: string;
}

function Card({
  title,
  subtitle,
  tiles,
  children,
}: {
  title: string;
  subtitle: string;
  tiles?: StatTile[];
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className="flex min-w-0 flex-col gap-4 rounded-2xl border border-line bg-card p-5"
    >
      <div>
        <h3 className="text-base font-semibold text-ink">{title}</h3>
        <p className="mt-0.5 text-[13px] text-ink-4">{subtitle}</p>
      </div>
      {children}
      {tiles && tiles.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          {tiles.map((tile) => (
            <div key={tile.caption} className="rounded-xl bg-canvas px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-4">
                {tile.caption}
              </p>
              <p className="mt-1 truncate text-[15px] font-bold text-ink">
                {tile.value}
              </p>
              <p className="truncate text-xs text-ink-4">{tile.sub}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

const barTone: Record<UsageMetric, string> = {
  spend: "bg-teal",
  requests: "bg-blue",
  tokens: "bg-periwinkle",
};

/** A few thick rounded bars with a label under each; the largest is solid. */
export function BarCard({
  title,
  subtitle,
  bars,
  metric,
  tiles,
}: {
  title: string;
  subtitle: string;
  bars: Array<{ label: string; value: number; title?: string }>;
  metric: UsageMetric;
  tiles?: StatTile[];
}) {
  const max = Math.max(0, ...bars.map((bar) => bar.value));
  const summary = bars
    .map((bar) => `${bar.label} ${metricValue(bar.value, metric)}`)
    .join(", ");
  return (
    <Card title={title} subtitle={subtitle} tiles={tiles}>
      {max === 0 ? (
        <p className="flex h-40 items-center justify-center text-sm text-ink-4">
          No recorded usage in this period.
        </p>
      ) : (
        <div role="img" aria-label={`${title}: ${summary}`}>
          <div aria-hidden="true" className="flex h-40 items-end gap-2.5">
            {bars.map((bar, index) => (
              <span
                key={`${bar.label}-${index}`}
                title={
                  bar.title ?? `${bar.label}: ${metricValue(bar.value, metric)}`
                }
                className={`min-w-0 flex-1 rounded-xl ${barTone[metric]} ${
                  bar.value === max ? "" : "opacity-50"
                }`}
                style={{ height: `${Math.max(4, (bar.value / max) * 100)}%` }}
              />
            ))}
          </div>
          <div aria-hidden="true" className="mt-2 flex gap-2.5">
            {bars.map((bar, index) => (
              <span
                key={`${bar.label}-${index}`}
                className="min-w-0 flex-1 truncate text-center text-[11px] text-ink-4"
              >
                {bar.label}
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

const sliceColors = [
  "rgb(var(--teal))",
  "rgb(var(--blue))",
  "rgb(var(--periwinkle))",
  "rgb(var(--cyan))",
  "rgb(var(--mint))",
  "rgb(var(--sand))",
];

/** A donut of shares, largest first, with a legend of percentages. */
export function DonutCard({
  title,
  subtitle,
  slices,
  metric,
  tiles,
}: {
  title: string;
  subtitle: string;
  slices: Array<{ label: string; value: number }>;
  metric: UsageMetric;
  tiles?: StatTile[];
}) {
  const sorted = [...slices]
    .filter((slice) => slice.value > 0)
    .sort((left, right) => right.value - left.value);
  // More than six shares fold into "Other" so colours stay distinct.
  const shown = sorted.length > 6 ? sorted.slice(0, 5) : sorted;
  if (sorted.length > 6)
    shown.push({
      label: "Other",
      value: sorted.slice(5).reduce((sum, slice) => sum + slice.value, 0),
    });
  const total = shown.reduce((sum, slice) => sum + slice.value, 0);
  const circumference = 2 * Math.PI * 40;
  let offset = 0;
  return (
    <Card title={title} subtitle={subtitle} tiles={tiles}>
      {total === 0 ? (
        <p className="flex h-40 items-center justify-center text-sm text-ink-4">
          No recorded usage in this period.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-5">
          <svg
            role="img"
            aria-label={`${title}: ${shown
              .map(
                (slice) =>
                  `${slice.label} ${Math.round((slice.value / total) * 100)}%`,
              )
              .join(", ")}`}
            viewBox="0 0 100 100"
            className="h-36 w-36 shrink-0 -rotate-90"
          >
            <circle
              cx="50"
              cy="50"
              r="40"
              fill="none"
              stroke="rgb(var(--well))"
              strokeWidth="14"
            />
            {shown.map((slice, index) => {
              const length = (slice.value / total) * circumference;
              const dash = (
                <circle
                  key={slice.label}
                  cx="50"
                  cy="50"
                  r="40"
                  fill="none"
                  stroke={sliceColors[index % sliceColors.length]}
                  strokeWidth="14"
                  strokeDasharray={`${length} ${circumference - length}`}
                  strokeDashoffset={-offset}
                >
                  <title>
                    {slice.label}: {metricValue(slice.value, metric)}
                  </title>
                </circle>
              );
              offset += length;
              return dash;
            })}
          </svg>
          <ul className="flex min-w-0 flex-1 flex-col gap-2 text-[13px]">
            {shown.map((slice, index) => (
              <li key={slice.label} className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{
                    background: sliceColors[index % sliceColors.length],
                  }}
                />
                <span className="min-w-0 flex-1 truncate text-ink-2">
                  {slice.label}
                </span>
                <span className="text-ink-4">
                  {Math.round((slice.value / total) * 100)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
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
