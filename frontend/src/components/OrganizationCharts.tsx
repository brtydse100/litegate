import type { OrganizationUsage, UsageMetrics } from "../types/organization";

export type UsageMetric = keyof UsageMetrics;

export const metricLabels: Record<UsageMetric, string> = {
  spend: "Spend (USD)",
  tokens: "Tokens",
  requests: "Logged requests",
};

export function metricValue(value: number, metric: UsageMetric): string {
  return metric === "spend"
    ? `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : value.toLocaleString();
}

export function SpendTrend({
  daily,
  metric,
}: {
  daily: OrganizationUsage["daily"];
  metric: UsageMetric;
}) {
  const max = Math.max(...daily.map((day) => day[metric]), 0);
  const scale = max || 1;
  const x = (index: number) =>
    48 + (index / Math.max(1, daily.length - 1)) * 584;
  const y = (value: number) => 176 - (value / scale) * 144;
  const points = daily
    .map((day, index) => `${x(index)},${y(day[metric])}`)
    .join(" ");
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-950">
        {metricLabels[metric]} over time
      </h2>
      <svg
        role="img"
        aria-label={`${metricLabels[metric]} over time`}
        viewBox="0 0 656 216"
        className="mt-3 w-full text-indigo-600"
      >
        <title>{metricLabels[metric]} by day</title>
        {[0, 0.5, 1].map((ratio) => (
          <g key={ratio}>
            <line
              x1="48"
              x2="632"
              y1={y(scale * ratio)}
              y2={y(scale * ratio)}
              stroke="currentColor"
              className="text-slate-200"
            />
            <text
              x="42"
              y={y(scale * ratio) + 4}
              textAnchor="end"
              fontSize="10"
              fill="currentColor"
              className="text-slate-500"
            >
              {metric === "spend" ? "$" : ""}
              {(scale * ratio).toLocaleString(undefined, {
                maximumFractionDigits: 1,
                notation: "compact",
              })}
            </text>
          </g>
        ))}
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          points={points}
        />
        {daily.map((day, index) => (
          <circle
            key={day.date}
            cx={x(index)}
            cy={y(day[metric])}
            r="3"
            fill="currentColor"
          >
            <title>
              {day.date}: {metricValue(day[metric], metric)}
            </title>
          </circle>
        ))}
        <text
          x="48"
          y="203"
          fontSize="11"
          fill="currentColor"
          className="text-slate-500"
        >
          {daily[0]?.date}
        </text>
        <text
          x="632"
          y="203"
          textAnchor="end"
          fontSize="11"
          fill="currentColor"
          className="text-slate-500"
        >
          {daily[daily.length - 1]?.date}
        </text>
      </svg>
      {max === 0 && (
        <p className="text-xs text-slate-500">
          No recorded usage in this period.
        </p>
      )}
      <details className="mt-2 text-xs text-slate-500">
        <summary className="cursor-pointer">View daily values</summary>
        <div className="mt-2 max-h-52 overflow-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th>Date</th>
                <th className="text-right">{metricLabels[metric]}</th>
              </tr>
            </thead>
            <tbody>
              {daily.map((day) => (
                <tr key={day.date}>
                  <td>{day.date}</td>
                  <td className="text-right">
                    {metricValue(day[metric], metric)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

export function UsageBars({
  title,
  values,
  metric,
  onSelect,
}: {
  title: string;
  values: OrganizationUsage["by_group"];
  metric: UsageMetric;
  onSelect?: (name: string) => void;
}) {
  const sorted = [...values].sort((a, b) => b[metric] - a[metric]);
  const max = Math.max(...sorted.map((row) => row[metric]), 1);
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-950">{title}</h2>
      <div className="mt-4 space-y-4">
        {sorted.map((row) => {
          const content = (
            <>
              <span className="flex justify-between gap-3 text-xs">
                <span className="truncate font-medium text-slate-700">
                  {row.name}
                </span>
                <span className="shrink-0 text-slate-500">
                  {metricValue(row[metric], metric)}
                </span>
              </span>
              <span className="mt-2 block h-2 overflow-hidden rounded-full bg-slate-100">
                <span
                  className="block h-full rounded-full bg-indigo-500"
                  style={{ width: `${(row[metric] / max) * 100}%` }}
                />
              </span>
            </>
          );
          return onSelect && row.name !== "Direct members" ? (
            <button
              key={row.name}
              type="button"
              aria-label={`Select ${row.name}`}
              onClick={() => onSelect(row.name)}
              className="block w-full text-left hover:opacity-75"
            >
              {content}
            </button>
          ) : (
            <div key={row.name}>{content}</div>
          );
        })}
        {!sorted.length && (
          <p className="text-sm text-slate-500">No recorded usage.</p>
        )}
      </div>
    </section>
  );
}
