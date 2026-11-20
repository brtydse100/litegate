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

const trendColor: Record<UsageMetric, string> = {
  spend: "text-teal",
  requests: "text-blue",
  tokens: "text-periwinkle",
};

const shortDay = (date: string) =>
  new Date(`${date}T00:00:00Z`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });

/** A compact card: the period total, a small daily trend and its peak day. */
export function TrendCard({
  daily,
  metric,
  total,
}: {
  daily: OrganizationUsage["daily"];
  metric: UsageMetric;
  total: number;
}) {
  const label = metricLabels[metric];
  const values = daily.map((day) => day[metric]);
  const max = Math.max(0, ...values);
  const scale = max || 1;
  // One bar per day: equal slots across the chart, bars 70% of a slot wide.
  const slot = 240 / Math.max(1, daily.length);
  const barWidth = Math.max(1, slot * 0.7);
  const height = (value: number) => (value / scale) * 46;
  const peak = daily.reduce<(typeof daily)[number] | undefined>(
    (best, day) => (!best || day[metric] > best[metric] ? day : best),
    undefined,
  );
  const average = daily.length ? total / daily.length : 0;
  return (
    <section
      aria-label={`${label} summary`}
      className="flex min-w-0 flex-col rounded-[10px] border border-line bg-card p-4"
    >
      <p className="text-xs text-ink-4">{label}</p>
      <p className="mt-1 text-xl font-semibold text-ink">
        {metricValue(total, metric)}
      </p>
      <svg
        role="img"
        aria-label={`${label} over time`}
        viewBox="0 0 240 56"
        preserveAspectRatio="none"
        className={`mt-3 h-14 w-full ${trendColor[metric]}`}
      >
        <title>{label} by day</title>
        <line
          x1="0"
          x2="240"
          y1="52"
          y2="52"
          stroke="currentColor"
          className="text-line"
        />
        {daily.map((day, index) => (
          <rect
            key={day.date}
            x={index * slot + (slot - barWidth) / 2}
            y={52 - height(day[metric])}
            width={barWidth}
            height={height(day[metric])}
            fill="currentColor"
          >
            <title>
              {day.date}: {metricValue(day[metric], metric)}
            </title>
          </rect>
        ))}
      </svg>
      {daily.length > 0 && (
        <p className="mt-1 flex justify-between text-[11px] text-ink-4">
          <span>{shortDay(daily[0].date)}</span>
          <span>{shortDay(daily[daily.length - 1].date)}</span>
        </p>
      )}
      <p className="mt-2 text-xs text-ink-3">
        {max === 0 || !peak
          ? "No recorded usage in this period."
          : `Avg ${metricValue(average, metric)} a day · peak ${metricValue(peak[metric], metric)} on ${shortDay(peak.date)}`}
      </p>
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
