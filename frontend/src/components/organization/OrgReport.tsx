import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api } from "../../api/client";
import EmailAddress from "../EmailAddress";
import DismissibleMessage from "../DismissibleMessage";
import {
  metricLabels,
  metricValue,
  SpendTrend,
  UsageBars,
  type UsageMetric,
} from "../OrganizationCharts";
import type { Group } from "./orgModel";

const inputClass =
  "min-h-10 rounded-lg border border-line-input bg-card px-3 py-2 text-sm text-ink";
const money = (value: number | null) =>
  value === null ? "No cap" : metricValue(value, "spend");

/** Usage charts and member list for one group, or all groups when `nodeId` is "". */
export default function OrgReport({
  nodeId,
  selected,
  nextLevel,
  totalUsers,
  onSelectChild,
}: {
  nodeId: string;
  selected?: Group;
  nextLevel?: string;
  totalUsers?: number;
  onSelectChild: (id: string) => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [page, setPage] = useState(1);
  const [pageNode, setPageNode] = useState(nodeId);
  if (pageNode !== nodeId) {
    setPageNode(nodeId);
    setPage(1);
  }
  const [metric, setMetric] = useState<UsageMetric>("spend");
  const [startDate, setStartDate] = useState(() =>
    new Date(Date.now() - 29 * 86400000).toISOString().slice(0, 10),
  );
  const [endDate, setEndDate] = useState(today);
  const usage = useQuery({
    queryKey: ["organization-usage", nodeId, startDate, endDate],
    queryFn: () => api.organizationUsage(nodeId, startDate, endDate),
    staleTime: 60000,
  });
  const users = useQuery({
    queryKey: ["organization-users", nodeId, page],
    queryFn: () => api.organizationUsers(nodeId, page),
    staleTime: 60000,
    refetchInterval: 60000,
  });
  const showMembers = !!selected && !selected.has_children;
  const hasMemberUsage = Array.isArray(usage.data?.by_user);

  return (
    <section
      aria-label="Usage report"
      className="flex flex-col gap-5 rounded-xl border border-line bg-card p-5"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-base font-bold text-ink">
          Usage in {selected?.name ?? "all groups"}
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-ink-4">
            From (UTC)
            <input
              type="date"
              aria-label="Usage start date"
              className={inputClass}
              value={startDate}
              max={endDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-4">
            Through (UTC)
            <input
              type="date"
              aria-label="Usage end date"
              className={inputClass}
              value={endDate}
              min={startDate}
              max={today}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-4">
            Chart metric
            <select
              aria-label="Chart metric"
              className={inputClass}
              value={metric}
              onChange={(event) => setMetric(event.target.value as UsageMetric)}
            >
              {Object.entries(metricLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <p className="text-xs text-ink-4">
        Reports use current group membership and UTC daily aggregates. Logged
        requests count upstream attempts. Reporting totals are independent of
        budget resets. Member charts use the selected dates; the table shows
        budget-period spending.
      </p>
      {usage.error && (
        <DismissibleMessage
          role="alert"
          messageKey={usage.error.message}
          className="rounded-lg border border-danger-line bg-danger-tint p-4 text-sm text-danger"
        >
          {usage.error.message}{" "}
          <button
            type="button"
            className="font-semibold underline"
            onClick={() => void usage.refetch()}
          >
            Retry usage
          </button>
        </DismissibleMessage>
      )}
      {usage.isPending && <p className="text-sm text-ink-4">Loading usage…</p>}
      {usage.data && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            {(["spend", "requests", "tokens"] as const).map((item) => (
              <div
                key={item}
                className="rounded-[10px] border border-line bg-card p-4"
              >
                <p className="text-xs text-ink-4">{metricLabels[item]}</p>
                <p className="mt-1 text-xl font-semibold text-ink">
                  {metricValue(usage.data.totals[item], item)}
                </p>
              </div>
            ))}
          </div>
          <SpendTrend daily={usage.data.daily} metric={metric} />
          {showMembers && !hasMemberUsage && (
            <p className="text-sm text-ink-4">
              Per-member usage is unavailable in this report. Showing group
              totals.
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <UsageBars
              title={
                showMembers && hasMemberUsage
                  ? "Usage by member"
                  : !showMembers && nextLevel
                    ? `Usage by ${nextLevel}`
                    : "Usage in this group"
              }
              values={
                showMembers && hasMemberUsage
                  ? usage.data.by_user
                  : usage.data.by_group
              }
              metric={metric}
              emailLabels={showMembers && hasMemberUsage}
              onSelect={!showMembers && nextLevel ? onSelectChild : undefined}
            />
            <UsageBars
              title="Usage by model"
              values={usage.data.by_model}
              metric={metric}
            />
          </div>
        </>
      )}
      <section className="overflow-hidden rounded-[10px] border border-line">
        <h2 className="flex items-center gap-2 border-b border-line p-4 text-sm font-semibold text-ink">
          <Users size={16} aria-hidden="true" /> Users{" "}
          <span className="text-ink-4">
            ({users.data?.total ?? selected?.members ?? totalUsers})
          </span>
        </h2>
        {users.error ? (
          <p role="alert" className="p-4 text-sm text-danger">
            {users.error.message}{" "}
            <button
              type="button"
              className="font-semibold underline"
              onClick={() => void users.refetch()}
            >
              Retry users
            </button>
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-canvas text-ink-4">
                <tr>
                  <th className="px-4 py-3">User</th>
                  <th className="px-4 py-3">Organization</th>
                  <th className="px-4 py-3">
                    Budget-period spend / per-key allowance
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {users.data?.users.map((user) => (
                  <tr key={user.user_id}>
                    <td className="px-4 py-3">
                      {user.email ? (
                        <EmailAddress
                          email={user.email}
                          className="font-medium text-ink-2"
                        />
                      ) : (
                        <p className="break-all font-medium text-ink-2">
                          {user.user_id}
                        </p>
                      )}
                      {user.email && (
                        <p className="mt-1 text-ink-4">{user.user_id}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-ink-3">
                      {user.path.join(" › ")}
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-ink-2">
                        {user.budget_spend === null
                          ? "Unavailable"
                          : metricValue(user.budget_spend, "spend")}{" "}
                        / {money(user.per_user)}
                      </p>
                      {user.sync_error && (
                        <p className="mt-1 text-sand-ink">{user.sync_error}</p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!users.isPending && !users.data?.users.length && (
              <p className="p-6 text-center text-sm text-ink-4">
                No mapped users in this group yet. SSO users appear after
                signing in.
              </p>
            )}
          </div>
        )}
        <div className="flex items-center justify-between border-t border-line px-4 py-3 text-xs text-ink-4">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            className="min-h-9 px-2 disabled:opacity-40"
          >
            Previous
          </button>
          <span>
            Page {page} of {users.data?.total_pages ?? 1}
          </span>
          <button
            type="button"
            disabled={page >= (users.data?.total_pages ?? 1)}
            onClick={() => setPage(page + 1)}
            className="min-h-9 px-2 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </section>
    </section>
  );
}
