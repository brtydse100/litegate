import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

const number = (value: number | null) =>
  value == null ? "Unavailable" : value.toLocaleString();
const dollars = (value: number) => `$${value.toFixed(6)}`;

export default function PersonalAnalytics() {
  const query = useQuery({
    queryKey: ["personal-analytics"],
    queryFn: api.personalAnalytics,
    refetchInterval: 60_000,
  });
  if (query.isPending) return <p role="status">Loading your analytics…</p>;
  if (query.isError && !query.data)
    return (
      <div role="alert">
        Could not load your analytics.{" "}
        <button onClick={() => void query.refetch()} className="underline">
          Retry
        </button>
      </div>
    );
  const data = query.data;
  if (!data.available)
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold">Your analytics</h2>
        <p className="mt-2 text-sm text-slate-600">
          {data.refresh_failed
            ? "Usage data is temporarily unavailable. The next hourly refresh will retry."
            : "Your first usage snapshot is pending. Analytics refresh once per hour."}
        </p>
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
  const barWidth = 600 / Math.max(1, data.daily.length);
  return (
    <section className="space-y-6" aria-label="Personal analytics">
      <div>
        <h2 className="text-xl font-semibold text-slate-950">Your analytics</h2>
        <p className="mt-1 text-sm text-slate-600">
          Your latest 30 days of usage. Data is aggregated once per hour.
        </p>
        <p className="mt-2 text-xs text-slate-500">
          Last successful refresh:{" "}
          {data.last_refreshed_at
            ? new Date(data.last_refreshed_at).toLocaleString()
            : "Pending"}
          . Stored coverage: {data.coverage_start} – {data.coverage_end}.
        </p>
        {(data.stale || query.isError) && (
          <p role="status" className="mt-2 text-sm text-amber-700">
            Showing the previous successful refresh. New data is delayed.
          </p>
        )}
      </div>
      <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {stats.map(([label, value]) => (
          <div
            key={label}
            className="rounded-lg border border-slate-200 bg-white p-4"
          >
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="mt-2 text-lg font-semibold text-slate-950">
              {value}
            </dd>
          </div>
        ))}
      </dl>
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h3 className="font-medium text-slate-900">Usage over time</h3>
        <svg
          viewBox="0 0 600 160"
          role="img"
          aria-label="Daily usage cost"
          className="mt-4 w-full text-indigo-500"
        >
          {data.daily.map((day, index) => (
            <rect
              key={day.date}
              x={index * barWidth + 1}
              y={150 - (day.cost / maxCost) * 140}
              width={Math.max(1, barWidth - 2)}
              height={(day.cost / maxCost) * 140}
              fill="currentColor"
            >
              <title>
                {day.date}: {dollars(day.cost)}, {number(day.requests)} requests
              </title>
            </rect>
          ))}
          <line x1="0" x2="600" y1="151" y2="151" stroke="currentColor" />
        </svg>
        <div className="flex justify-between text-xs text-slate-500">
          <span>{data.daily[0]?.date}</span>
          <span>{data.daily[data.daily.length - 1]?.date}</span>
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white p-5">
        <h3 className="mb-3 font-medium text-slate-900">Usage by model</h3>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-slate-500">
              <th className="p-2">Model</th>
              <th className="p-2">Requests</th>
              <th className="p-2">Tokens</th>
              <th className="p-2">Cost</th>
            </tr>
          </thead>
          <tbody>
            {data.models.map((model) => (
              <tr key={model.model} className="border-t border-slate-100">
                <td className="break-all p-2">{model.model}</td>
                <td className="p-2">{number(model.requests)}</td>
                <td className="p-2">{number(model.tokens)}</td>
                <td className="p-2">{dollars(model.cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.models.length && (
          <p className="text-sm text-slate-500">
            No model usage was reported in this period.
          </p>
        )}
      </div>
      {data.budgets.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h3 className="font-medium text-slate-900">Personal allowances</h3>
          <p className="mt-1 text-xs text-slate-500">
            Budget values are from the last successful refresh. Separate key
            reset windows are shown separately.
          </p>
          {data.budgets.map((budget, index) => (
            <p key={index} className="mt-3 text-sm">
              {!budget.available
                ? "Current allowance unavailable"
                : `Key ${budget.number}: ${budget.limit == null ? "No configured limit" : `${budget.remaining == null ? "Unavailable" : dollars(budget.remaining)} remaining of ${dollars(budget.limit)}`} ${budget.duration ? `(${budget.duration})` : ""}`}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
