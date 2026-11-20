import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Users, X } from "lucide-react";
import { api } from "../../api/client";
import EmailAddress from "../EmailAddress";
import DismissibleMessage from "../DismissibleMessage";
import {
  BarCard,
  DonutCard,
  metricValue,
  UsageBars,
  weekly,
} from "../OrganizationCharts";
import type { OrganizationUsage, UsageMetrics } from "../../types/organization";
import type { Group } from "./orgModel";

const inputClass =
  "min-h-10 rounded-lg border border-line-input bg-card px-3 py-2 text-sm text-ink";
const money = (value: number | null) =>
  value === null ? "No cap" : metricValue(value, "spend");

/** Usage charts and member list for some groups, or all groups when empty. */
export default function OrgReport({
  nodeIds,
  title,
  selected,
  nextLevel,
  totalUsers,
  onSelectChild,
  onClose,
}: {
  nodeIds: string[];
  title: string;
  selected?: Group;
  nextLevel?: string;
  totalUsers?: number;
  onSelectChild: (id: string) => void;
  /** Hides the report; absent when the report is the whole view. */
  onClose?: () => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [page, setPage] = useState(1);
  const nodeKey = nodeIds.join(",");
  const [pageNode, setPageNode] = useState(nodeKey);
  if (pageNode !== nodeKey) {
    setPageNode(nodeKey);
    setPage(1);
  }
  const [startDate, setStartDate] = useState(() =>
    new Date(Date.now() - 29 * 86400000).toISOString().slice(0, 10),
  );
  const [endDate, setEndDate] = useState(today);
  const usage = useQuery({
    queryKey: ["organization-usage", nodeKey, startDate, endDate],
    queryFn: () => api.organizationUsage(nodeIds, startDate, endDate),
    staleTime: 60000,
  });
  const users = useQuery({
    queryKey: ["organization-users", nodeKey, page],
    queryFn: () => api.organizationUsers(nodeIds, page),
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
        <h2 className="text-base font-bold text-ink">Usage in {title}</h2>
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
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close usage report"
              title="Close usage report"
              className="grid h-10 w-10 place-items-center rounded-lg border border-line-input bg-card text-ink-3 hover:bg-canvas focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue"
            >
              <X size={16} aria-hidden="true" />
            </button>
          )}
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
          <UsageCards
            usage={usage.data}
            ranked={
              showMembers && hasMemberUsage
                ? usage.data.by_user
                : usage.data.by_group
            }
            rankedLabel={
              showMembers && hasMemberUsage
                ? "member"
                : (nextLevel?.toLowerCase() ?? "group")
            }
          />
          {showMembers && !hasMemberUsage && (
            <p className="text-sm text-ink-4">
              Per-member usage is unavailable in this report. Showing group
              totals.
            </p>
          )}
          <div>
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
              metric="spend"
              emailLabels={showMembers && hasMemberUsage}
              onSelect={!showMembers && nextLevel ? onSelectChild : undefined}
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
          <div className="relative overflow-x-auto">
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
                    <td className="min-w-[13rem] px-4 py-3">
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

/** Small report cards: weekly spend and requests, top token users, models. */
function UsageCards({
  usage,
  ranked,
  rankedLabel,
}: {
  usage: OrganizationUsage;
  ranked: Array<UsageMetrics & { name: string }>;
  rankedLabel: string;
}) {
  const days = usage.daily.length || 1;
  const spendWeeks = weekly(usage.daily, "spend");
  const requestWeeks = weekly(usage.daily, "requests");
  const busiest = (weeks: typeof spendWeeks) =>
    weeks.reduce<(typeof weeks)[number] | undefined>(
      (best, week) => (!best || week.value > best.value ? week : best),
      undefined,
    );
  const topSpend = busiest(spendWeeks);
  const topRequests = busiest(requestWeeks);
  const byTokens = [...ranked]
    .filter((item) => item.tokens > 0)
    .sort((left, right) => right.tokens - left.tokens);
  const range = `${usage.start_date} – ${usage.end_date}`;
  const usedModels = usage.by_model.filter((model) => model.spend > 0);
  const topModel = usedModels.reduce<(typeof usedModels)[number] | undefined>(
    (best, model) => (!best || model.spend > best.spend ? model : best),
    undefined,
  );
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <BarCard
        title="Spend history"
        subtitle={`By week · ${range}`}
        metric="spend"
        bars={spendWeeks}
        tiles={[
          {
            caption: "Busiest week",
            value: topSpend ? metricValue(topSpend.value, "spend") : "—",
            sub: topSpend ? `Week of ${topSpend.label}` : "No spend",
          },
          {
            caption: "Daily average",
            value: metricValue(usage.totals.spend / days, "spend"),
            sub: `${metricValue(usage.totals.spend, "spend")} in total`,
          },
        ]}
      />
      <BarCard
        title={`Tokens by ${rankedLabel}`}
        subtitle="Most tokens first"
        metric="tokens"
        bars={byTokens.slice(0, 6).map((item) => ({
          label: item.name,
          value: item.tokens,
        }))}
        tiles={[
          {
            caption: `Top ${rankedLabel}`,
            value: byTokens[0]?.name ?? "—",
            sub: byTokens[0]
              ? `${metricValue(byTokens[0].tokens, "tokens")} tokens`
              : "No tokens",
          },
          {
            caption: "Total tokens",
            value: metricValue(usage.totals.tokens, "tokens"),
            sub: `across ${byTokens.length} ${byTokens.length === 1 ? rankedLabel : `${rankedLabel}s`}`,
          },
        ]}
      />
      <DonutCard
        title="Spend by model"
        subtitle="Share of spend in this period"
        metric="spend"
        slices={usage.by_model.map((model) => ({
          label: model.name,
          value: model.spend,
        }))}
        tiles={[
          {
            caption: "Top model",
            value: topModel?.name ?? "—",
            sub: topModel
              ? `${metricValue(topModel.spend, "spend")} spent`
              : "No spend",
          },
          {
            caption: "Models used",
            value: metricValue(usedModels.length, "requests"),
            sub: `${metricValue(usage.totals.spend, "spend")} in total`,
          },
        ]}
      />
      <BarCard
        title="Requests history"
        subtitle={`By week · ${range}`}
        metric="requests"
        bars={requestWeeks}
        tiles={[
          {
            caption: "Total requests",
            value: metricValue(usage.totals.requests, "requests"),
            sub: `${metricValue(Math.round(usage.totals.requests / days), "requests")} a day`,
          },
          {
            caption: "Busiest week",
            value: topRequests
              ? metricValue(topRequests.value, "requests")
              : "—",
            sub: topRequests ? `Week of ${topRequests.label}` : "No requests",
          },
        ]}
      />
    </div>
  );
}
