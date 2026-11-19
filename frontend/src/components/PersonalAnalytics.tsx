import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { formatUsd as dollars } from "../formatUsd";
import { PageHeader, UsageBar } from "./Page";
import { buttonSecondary, card, cardHeader, cardTitle, tableHead } from "./ui";

const number = (value: number | null) =>
  value == null ? "Unavailable" : value.toLocaleString();

const accents = [
  "border-t-blue",
  "border-t-cyan",
  "border-t-periwinkle",
  "border-t-teal",
  "border-t-mint",
];

export default function PersonalAnalytics() {
  const query = useQuery({
    queryKey: ["personal-analytics"],
    queryFn: api.personalAnalytics,
    refetchInterval: 60_000,
  });
  if (query.isPending)
    return (
      <p role="status" className="text-sm text-ink-4">
        Loading your analytics…
      </p>
    );
  if (query.isError && !query.data)
    return (
      <div
        role="alert"
        className="flex flex-wrap items-center gap-3 rounded-xl border border-danger-line bg-danger-tint px-4 py-3 text-sm text-danger"
      >
        Could not load your analytics.
        <button
          type="button"
          onClick={() => void query.refetch()}
          className={buttonSecondary}
        >
          Retry
        </button>
      </div>
    );
  const data = query.data;
  if (!data.available)
    return (
      <div className="flex flex-col gap-6">
        <PageHeader eyebrow="Workspace" title="Your analytics" />
        <div className={`${card} p-6`}>
          <p className="text-sm text-ink-3">
            {data.refresh_failed
              ? "Usage data is temporarily unavailable. The next hourly refresh will retry."
              : "Your first usage snapshot is pending. Analytics refresh once per hour."}
          </p>
        </div>
      </div>
    );
  const stats = [
    ["Requests", number(data.totals.requests)],
    ["Input tokens", number(data.totals.input_tokens)],
    ["Output tokens", number(data.totals.output_tokens)],
    ["Total tokens", number(data.totals.tokens)],
    ["Usage cost", dollars(data.totals.cost)],
  ];
  const maxCost = Math.max(0.000001, ...data.daily.map((day) => day.cost));
  // Each day gets an equal slot across the chart; bars stay at most 40 wide
  // and sit centred in their slot, so a few days spread out evenly.
  const slot = 600 / Math.max(1, data.daily.length);
  const barWidth = Math.max(1, Math.min(slot - 2, 40));
  const centre = (index: number) => ((index + 0.5) * slot) / 6;
  const lastIndex = data.daily.length - 1;
  return (
    <section className="flex flex-col gap-6" aria-label="Personal analytics">
      <div>
        <PageHeader
          eyebrow="Workspace"
          title="Your analytics"
          description="Your latest 30 days of usage. Data is aggregated once per hour."
        />
        <p className="mt-2 text-xs text-ink-4">
          Last successful refresh:{" "}
          {data.last_refreshed_at
            ? new Date(data.last_refreshed_at).toLocaleString()
            : "Pending"}
          . Stored coverage: {data.coverage_start} – {data.coverage_end}.
        </p>
        {(data.stale || query.isError) && (
          <p
            role="status"
            className="mt-3 rounded-lg border border-sand/40 bg-sand-tint px-3 py-2 text-sm text-sand-ink"
          >
            Showing the previous successful refresh. New data is delayed.
          </p>
        )}
      </div>
      <dl className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-5">
        {stats.map(([label, value], index) => (
          <div
            key={label}
            className={`rounded-[10px] border border-t-[3px] border-line bg-card px-[18px] pb-4 pt-3.5 ${accents[index]}`}
          >
            <dt className="text-xs font-semibold tracking-[0.04em] text-ink-4">
              {label}
            </dt>
            <dd className="mt-1 text-2xl font-semibold text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      <div className={`${card} p-5`}>
        <h2 className={cardTitle}>Usage over time</h2>
        <svg
          viewBox="0 0 600 160"
          role="img"
          aria-label="Daily usage cost"
          className="mt-4 w-full text-blue"
        >
          {[0.5, 1].map((ratio) => (
            <line
              key={ratio}
              x1="0"
              x2="600"
              y1={150 - ratio * 140}
              y2={150 - ratio * 140}
              stroke="rgb(var(--line))"
              strokeDasharray="3 4"
            />
          ))}
          {data.daily.map((day, index) => (
            <rect
              key={day.date}
              x={index * slot + (slot - barWidth) / 2}
              y={150 - (day.cost / maxCost) * 140}
              width={barWidth}
              height={(day.cost / maxCost) * 140}
              rx={Math.min(3, barWidth / 4)}
              fill="currentColor"
            >
              <title>
                {day.date}: {dollars(day.cost)}, {number(day.requests)} requests
              </title>
            </rect>
          ))}
          <line
            x1="0"
            x2="600"
            y1="151"
            y2="151"
            stroke="rgb(var(--line-input))"
          />
        </svg>
        {!data.daily.length ? (
          <p className="mt-1 text-xs text-ink-4">
            No usage recorded in this period.
          </p>
        ) : data.daily.length >= 8 ? (
          <div className="mt-1 flex justify-between text-xs text-ink-4">
            <span>{data.daily[0]?.date}</span>
            <span>{data.daily[lastIndex]?.date}</span>
          </div>
        ) : (
          // Few days: label the first and last bars directly beneath them.
          <div className="relative mt-1 h-4 text-xs text-ink-4">
            {[...new Set([0, lastIndex])].map((index) => (
              <span
                key={index}
                className="absolute -translate-x-1/2 whitespace-nowrap"
                style={{ left: `${centre(index)}%` }}
              >
                {data.daily[index].date}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className={`overflow-hidden ${card}`}>
        <div className={cardHeader}>
          <h2 className={cardTitle}>Usage by model</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead className={tableHead}>
              <tr>
                <th className="px-5 py-2.5 font-semibold">Model</th>
                <th className="px-3 py-2.5 text-right font-semibold">
                  Requests
                </th>
                <th className="px-3 py-2.5 text-right font-semibold">Tokens</th>
                <th className="px-5 py-2.5 text-right font-semibold">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {data.models.map((model) => (
                <tr key={model.model}>
                  <td className="break-all px-5 py-3 font-mono text-[13px] text-ink">
                    {model.model}
                  </td>
                  <td className="px-3 py-3 text-right text-ink-2">
                    {number(model.requests)}
                  </td>
                  <td className="px-3 py-3 text-right text-ink-2">
                    {number(model.tokens)}
                  </td>
                  <td className="px-5 py-3 text-right font-semibold text-ink">
                    {dollars(model.cost)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!data.models.length && (
          <p className="px-5 py-4 text-sm text-ink-4">
            No model usage was reported in this period.
          </p>
        )}
      </div>
      {data.budgets.length > 0 && (
        <div className={`${card} p-5`}>
          <h2 className={cardTitle}>Personal allowances</h2>
          <p className="mt-1 text-[13px] text-ink-4">
            Budget values are from the last successful refresh. Separate key
            reset windows are shown separately.
          </p>
          <ul className="mt-3 flex flex-col gap-3">
            {data.budgets.map((budget, index) => (
              <li key={index} className="flex flex-col gap-1.5 text-sm">
                <p className="text-ink-2">
                  {!budget.available
                    ? "Current allowance unavailable"
                    : `Key ${budget.number}: ${budget.limit == null ? "No configured limit" : `${budget.remaining == null ? "Unavailable" : dollars(budget.remaining)} remaining of ${dollars(budget.limit)}`} ${budget.duration ? `(${budget.duration})` : ""}`}
                </p>
                {budget.available &&
                  budget.limit != null &&
                  budget.limit > 0 &&
                  budget.remaining != null && (
                    <UsageBar
                      className="max-w-md"
                      percent={
                        ((budget.limit - budget.remaining) / budget.limit) * 100
                      }
                    />
                  )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
