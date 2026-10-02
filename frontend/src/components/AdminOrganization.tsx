import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Network, Users } from "lucide-react";
import { api } from "../api/client";
import type { OrganizationGroup } from "../types/organization";
import {
  metricLabels,
  metricValue,
  SpendTrend,
  UsageBars,
  type UsageMetric,
} from "./OrganizationCharts";

const inputClass =
  "rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900";
const money = (value: number | null) =>
  value === null ? "No cap" : metricValue(value, "spend");

function treeOrder(
  groups: OrganizationGroup[],
  expanded: Set<string>,
  parent: string | null = null,
): OrganizationGroup[] {
  return groups
    .filter((group) => group.parent_id === parent)
    .flatMap((group) => [
      group,
      ...(expanded.has(group.id) ? treeOrder(groups, expanded, group.id) : []),
    ]);
}

export default function AdminOrganization() {
  const today = new Date().toISOString().slice(0, 10);
  const [nodeId, setNodeId] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [page, setPage] = useState(1);
  const [metric, setMetric] = useState<UsageMetric>("spend");
  const [startDate, setStartDate] = useState(() =>
    new Date(Date.now() - 29 * 86400000).toISOString().slice(0, 10),
  );
  const [endDate, setEndDate] = useState(today);
  const overview = useQuery({
    queryKey: ["organization"],
    queryFn: api.organization,
    refetchInterval: 60000,
  });
  const enabled = overview.data?.enabled === true;
  const usage = useQuery({
    queryKey: ["organization-usage", nodeId, startDate, endDate],
    queryFn: () => api.organizationUsage(nodeId, startDate, endDate),
    enabled,
    staleTime: 60000,
  });
  const users = useQuery({
    queryKey: ["organization-users", nodeId, page],
    queryFn: () => api.organizationUsers(nodeId, page),
    enabled,
    refetchInterval: 60000,
  });
  const groups = overview.data?.groups ?? [];
  const selected = groups.find((group) => group.id === nodeId);
  const budgetSource = groups.find(
    (group) => group.id === selected?.budget_source,
  );
  const nextLevel = overview.data?.levels[(selected?.level ?? -1) + 1];

  function selectGroup(id: string) {
    setNodeId(id);
    setPage(1);
    setExpanded((current) => {
      const next = new Set(current);
      let parent = groups.find((group) => group.id === id)?.parent_id;
      while (parent) {
        next.add(parent);
        parent = groups.find((group) => group.id === parent)?.parent_id;
      }
      return next;
    });
  }
  function toggleGroup(id: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function selectChild(id: string) {
    const child = groups.find(
      (group) => group.id === id && group.parent_id === (selected?.id ?? null),
    );
    if (child) selectGroup(child.id);
  }

  if (overview.isPending)
    return <p className="text-sm text-slate-500">Loading organization…</p>;
  if (overview.error)
    return (
      <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-700">
        {overview.error.message}
      </p>
    );
  if (!enabled)
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-8">
        <Network className="text-indigo-500" />
        <h1 className="mt-4 text-lg font-semibold">Organization</h1>
        <p className="mt-2 text-sm text-slate-500">
          Configure organizationHierarchy in your Helm values to organize users
          and manage their budgets.
        </p>
      </section>
    );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-950">Organization</h1>
          <p className="mt-1 text-sm text-slate-500">
            Usage, membership, and budgets across your organization.
          </p>
        </div>
        <span className="rounded-md border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700">
          Policies managed through Helm
        </span>
      </div>
      {!!overview.data?.issues.length && (
        <div
          role="alert"
          className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
        >
          <p className="font-medium">Some memberships need attention</p>
          <ul className="mt-2 space-y-1">
            {overview.data.issues.map((issue, index) => (
              <li key={`${issue.user_id}-${index}`}>
                {issue.user_id}: {issue.error}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="self-start rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
          <p className="px-2 pb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {overview.data?.levels.join(" / ")}
          </p>
          <nav aria-label="Organization groups" className="space-y-1">
            <button
              type="button"
              aria-label={`All groups, ${overview.data?.total_users} users`}
              aria-pressed={!nodeId}
              onClick={() => selectGroup("")}
              className={`flex w-full justify-between rounded-md px-3 py-2 text-sm ${!nodeId ? "bg-indigo-50 font-medium text-indigo-700" : "text-slate-600 hover:bg-slate-50"}`}
            >
              All groups<span>{overview.data?.total_users}</span>
            </button>
            {treeOrder(groups, expanded).map((group) => (
              <div
                key={group.id}
                style={{ paddingLeft: 4 + group.level * 14 }}
                className={`flex items-center rounded-md text-sm ${nodeId === group.id ? "bg-indigo-50 font-medium text-indigo-700" : "text-slate-600 hover:bg-slate-50"}`}
              >
                {groups.some((child) => child.parent_id === group.id) ? (
                  <button
                    type="button"
                    aria-label={`${expanded.has(group.id) ? "Collapse" : "Expand"} ${group.path.join(" → ")}`}
                    aria-expanded={expanded.has(group.id)}
                    onClick={() => toggleGroup(group.id)}
                    className="shrink-0 rounded p-1 hover:bg-slate-100 focus-visible:outline-indigo-500"
                  >
                    <ChevronRight
                      size={16}
                      aria-hidden="true"
                      className={expanded.has(group.id) ? "rotate-90" : ""}
                    />
                  </button>
                ) : (
                  <span className="w-6 shrink-0" />
                )}
                <button
                  type="button"
                  aria-label={`${group.name}, ${group.members} ${group.members === 1 ? "user" : "users"}`}
                  aria-pressed={nodeId === group.id}
                  onClick={() => selectGroup(group.id)}
                  className="flex min-w-0 flex-1 items-center justify-between gap-2 rounded-md py-2 pl-1 pr-3 text-left focus-visible:outline-indigo-500"
                >
                  <span className="truncate" title={group.path.join(" → ")}>
                    {group.name}
                  </span>
                  <span className="text-xs">{group.members}</span>
                </button>
              </div>
            ))}
          </nav>
        </aside>
        <div className="min-w-0 space-y-5">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
            {selected ? (
              selected.path.map((name, index) => (
                <span key={index} className="flex items-center gap-2">
                  {index > 0 && <ChevronRight size={14} />}
                  {name}
                </span>
              ))
            ) : (
              <span>All groups</span>
            )}
          </div>
          {selected && (
            <section
              aria-label="Effective budget policy"
              className="rounded-lg border border-indigo-100 bg-indigo-50 p-4"
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs text-slate-500">Per-user allowance</p>
                  <p className="mt-1 font-semibold text-slate-950">
                    {money(selected.per_user)}
                    {selected.duration && (
                      <span className="ml-2 text-xs font-normal text-slate-500">
                        {" "}
                        per {selected.duration}
                      </span>
                    )}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {budgetSource && budgetSource.id !== selected.id
                      ? `Inherited from ${budgetSource.name}`
                      : "Defined on this group"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">
                    {selected.path[0]} shared pool
                  </p>
                  <p className="mt-1 font-semibold text-slate-950">
                    {selected.group_spend === null
                      ? "Unavailable"
                      : metricValue(selected.group_spend, "spend")}{" "}
                    / {money(selected.group_total)}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Current budget-cycle spend across the top-level group
                  </p>
                </div>
              </div>
              {selected.sync_error && (
                <p role="alert" className="mt-3 text-sm text-amber-800">
                  {selected.sync_error}
                </p>
              )}
            </section>
          )}
          <div className="flex flex-wrap items-end gap-3">
            <label className="space-y-1 text-xs text-slate-500">
              <span className="block">From (UTC)</span>
              <input
                type="date"
                aria-label="Usage start date"
                className={inputClass}
                value={startDate}
                max={endDate}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </label>
            <label className="space-y-1 text-xs text-slate-500">
              <span className="block">Through (UTC)</span>
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
            <label className="space-y-1 text-xs text-slate-500">
              <span className="block">Chart metric</span>
              <select
                aria-label="Chart metric"
                className={inputClass}
                value={metric}
                onChange={(event) =>
                  setMetric(event.target.value as UsageMetric)
                }
              >
                {Object.entries(metricLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="text-xs text-slate-500">
            Reports use current group membership and UTC daily aggregates.
            Logged requests count upstream attempts. Reporting totals are
            independent of budget resets.
          </p>
          {usage.error && (
            <p
              role="alert"
              className="rounded-lg bg-red-50 p-4 text-sm text-red-700"
            >
              {usage.error.message}
            </p>
          )}
          {usage.isPending && (
            <p className="text-sm text-slate-500">Loading usage…</p>
          )}
          {usage.data && (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                {(["spend", "requests", "tokens"] as const).map((item) => (
                  <div
                    key={item}
                    className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
                  >
                    <p className="text-xs text-slate-500">
                      {metricLabels[item]}
                    </p>
                    <p className="mt-1 text-xl font-semibold text-slate-950">
                      {metricValue(usage.data.totals[item], item)}
                    </p>
                  </div>
                ))}
              </div>
              <SpendTrend daily={usage.data.daily} metric={metric} />
              <div className="grid gap-4 sm:grid-cols-2">
                <UsageBars
                  title={
                    nextLevel ? `Usage by ${nextLevel}` : "Usage in this group"
                  }
                  values={usage.data.by_group}
                  metric={metric}
                  onSelect={nextLevel ? selectChild : undefined}
                />
                <UsageBars
                  title="Usage by model"
                  values={usage.data.by_model}
                  metric={metric}
                />
              </div>
            </>
          )}
          <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            <h2 className="flex items-center gap-2 border-b border-slate-200 p-4 text-sm font-semibold text-slate-950">
              <Users size={16} /> Users{" "}
              <span className="text-slate-500">
                (
                {users.data?.total ??
                  selected?.members ??
                  overview.data?.total_users}
                )
              </span>
            </h2>
            {users.error ? (
              <p role="alert" className="p-4 text-sm text-red-700">
                {users.error.message}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500">
                    <tr>
                      <th className="px-4 py-3">User</th>
                      <th className="px-4 py-3">Organization</th>
                      <th className="px-4 py-3">Cycle spend / allowance</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {users.data?.users.map((user) => (
                      <tr key={user.user_id}>
                        <td className="px-4 py-3">
                          <p className="font-medium text-slate-800">
                            {user.email || user.user_id}
                          </p>
                          {user.email && (
                            <p className="mt-1 text-slate-500">
                              {user.user_id}
                            </p>
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-600">
                          {user.path.join(" → ")}
                        </td>
                        <td className="px-4 py-3">
                          <p className="text-slate-800">
                            {user.budget_spend === null
                              ? "Unavailable"
                              : metricValue(user.budget_spend, "spend")}{" "}
                            / {money(user.per_user)}
                          </p>
                          {user.sync_error && (
                            <p className="mt-1 text-amber-700">
                              {user.sync_error}
                            </p>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!users.isPending && !users.data?.users.length && (
                  <p className="p-6 text-center text-sm text-slate-500">
                    No mapped users in this group yet. SSO users appear after
                    signing in.
                  </p>
                )}
              </div>
            )}
            <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-xs text-slate-500">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="disabled:opacity-40"
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
                className="disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
