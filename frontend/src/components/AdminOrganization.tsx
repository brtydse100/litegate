import { useEffect, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { BarChart3, Network } from "lucide-react";
import { api } from "../api/client";
import DismissibleMessage from "./DismissibleMessage";
import GroupPanel from "./organization/GroupPanel";
import OrgReport from "./organization/OrgReport";
import {
  groupInitials,
  hueFor,
  percent,
  plural,
  shortMoney,
  type Group,
} from "./organization/orgModel";
import type { OrganizationGroup } from "../types/organization";

const NEAR = 80;
const ATTENTION = 85;
/** Rows indent up to this many levels before the table re-roots. */
const MAX_DEPTH = 3;
const columns =
  "grid min-w-[700px] grid-cols-[minmax(0,2fr)_minmax(0,0.7fr)_minmax(0,1.9fr)_minmax(0,0.8fr)] items-center gap-4";

function greeting(email?: string) {
  const hour = new Date().getHours();
  const part = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  const local = email?.split("@")[0]?.split(/[._-]/)[0] ?? "";
  const name = local ? local[0].toUpperCase() + local.slice(1) : "";
  return `Good ${part}${name ? `, ${name}` : ""}`;
}

function within(group: Pick<Group, "path">, ancestor: Pick<Group, "path">) {
  return (
    group.path.length > ancestor.path.length &&
    ancestor.path.every((name, index) => group.path[index] === name)
  );
}

function treeOrder(
  groups: Group[],
  expanded: (id: string) => boolean,
  parent: string | null,
): Group[] {
  return groups
    .filter((group) => group.parent_id === parent)
    .flatMap((group) => [
      group,
      ...(expanded(group.id) ? treeOrder(groups, expanded, group.id) : []),
    ]);
}

function Metric({
  accent,
  caption,
  children,
  sub,
  bar,
}: {
  accent: string;
  caption: string;
  children: React.ReactNode;
  sub: string;
  bar?: number | null;
}) {
  return (
    <div
      className={`flex flex-col gap-1 rounded-[10px] border border-t-[3px] border-line bg-card px-[18px] pb-[18px] pt-4 ${accent}`}
    >
      <span className="text-xs font-semibold tracking-[0.04em] text-ink-4">
        {caption}
      </span>
      <span className="inline-flex items-center gap-2.5 text-[28px] font-semibold text-ink">
        {children}
      </span>
      <span className="text-[13px] text-ink-3">{sub}</span>
      {bar != null && (
        <span className="mt-2 block h-1 rounded-sm bg-line-soft">
          <span
            className="block h-1 rounded-sm bg-teal"
            style={{ width: `${Math.min(100, bar)}%` }}
          />
        </span>
      )}
    </div>
  );
}

export default function AdminOrganization({
  budgetsEnabled = false,
  email,
  isAdmin = false,
}: {
  budgetsEnabled?: boolean;
  email?: string;
  /** Global administrators also see gateway readiness. */
  isAdmin?: boolean;
}) {
  const [rootChoice, setRootChoice] = useState<string | null>(null);
  const [tableChoice, setTableChoice] = useState<string | null>(null);
  const [nodeId, setNodeId] = useState<string | null>(null);
  const [allGroupsReport, setAllGroupsReport] = useState(false);
  const [requestedParents, setRequestedParents] = useState<Set<string>>(
    () => new Set(),
  );
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [expandAll, setExpandAll] = useState(false);
  const [showIssues, setShowIssues] = useState(false);

  const rootsQuery = useQuery({
    queryKey: ["organization-children", ""],
    queryFn: () => api.organizationChildren(),
    staleTime: 60000,
    refetchInterval: 60000,
  });
  const enabled = rootsQuery.data?.enabled === true;
  const childQueries = useQueries({
    queries: [...requestedParents].map((parent) => ({
      queryKey: ["organization-children", parent],
      queryFn: () => api.organizationChildren(parent),
      staleTime: 60000,
      refetchInterval: expanded.has(parent) ? 60000 : (false as const),
    })),
  });
  // Descendant spend totals; the server caches each team for 60 seconds.
  const totals = useQuery({
    queryKey: ["organization-overview"],
    queryFn: api.organization,
    enabled,
    // Once per page open (and on Refresh); served from the shared team listing.
    staleTime: 60000,
  });
  const status = useQuery({
    queryKey: ["system-status"],
    queryFn: api.getSystemStatus,
    enabled: enabled && isAdmin,
    refetchInterval: 30_000,
  });
  const budgets = useQuery({
    queryKey: ["organization-budgets"],
    queryFn: api.organizationBudgets,
    enabled: enabled && budgetsEnabled,
    retry: false,
  });

  const levels = rootsQuery.data?.levels ?? [];
  const roots = rootsQuery.data?.groups ?? [];
  const loaded = new Map<string, Group>();
  for (const group of [
    ...roots,
    ...childQueries.flatMap((query) => query.data?.groups ?? []),
  ])
    loaded.set(group.id, group);
  const full = new Map<string, OrganizationGroup>(
    (totals.data?.groups ?? []).map((group) => [group.id, group]),
  );
  // Overview groups fill in rows that were not expanded yet (e.g. from
  // "Needs attention"); loaded nodes keep their own has_children flag.
  for (const group of full.values())
    if (!loaded.has(group.id))
      loaded.set(group.id, {
        ...group,
        has_children: [...full.values()].some(
          (other) => other.parent_id === group.id,
        ),
      });
  const withSpend = (group: Group): Group => ({
    ...group,
    group_spend: full.get(group.id)?.group_spend ?? group.group_spend,
    sync_error: full.get(group.id)?.sync_error ?? group.sync_error,
  });
  const groups = [...loaded.values()].map(withSpend);
  const byId = new Map(groups.map((group) => [group.id, group]));

  const root = byId.get(rootChoice ?? "") ?? roots[0];
  const tableRoot =
    byId.get(tableChoice ?? "") && root && within(byId.get(tableChoice!)!, root)
      ? byId.get(tableChoice!)!
      : root;
  const rootChildren = groups
    .filter((group) => group.parent_id === root?.id)
    .map((group) => group.id);
  const hue = (group: Group) =>
    group.id === root?.id
      ? hueFor(
          group,
          null,
          byId,
          roots.map((item) => item.id),
        )
      : hueFor(group, root?.id ?? null, byId, rootChildren);
  const depth = (group: Group) => group.level - (tableRoot?.level ?? 0) - 1;
  const isExpanded = (id: string) => {
    const group = byId.get(id);
    if (!group?.has_children) return false;
    return expanded.has(id) || (expandAll && depth(group) < MAX_DEPTH - 1);
  };
  const rows = tableRoot ? treeOrder(groups, isExpanded, tableRoot.id) : [];

  // Load the table root's children and, in expand-all mode, every visible branch.
  const wanted = [
    tableRoot?.has_children ? tableRoot.id : null,
    ...rows
      .filter((group) => group.has_children && isExpanded(group.id))
      .map((group) => group.id),
  ]
    .filter((id): id is string => !!id && !requestedParents.has(id))
    .join("\n");
  useEffect(() => {
    if (wanted)
      setRequestedParents(
        (current) => new Set([...current, ...wanted.split("\n")]),
      );
  }, [wanted]);

  const selected = nodeId ? byId.get(nodeId) : undefined;
  if (nodeId && rootsQuery.data && !selected && !totals.isPending)
    setNodeId(null);
  const detail = useQuery({
    queryKey: ["organization-group", nodeId],
    queryFn: () => api.organizationGroup(nodeId!),
    enabled: enabled && !!selected,
    staleTime: 60000,
    refetchInterval: 60000,
  });

  function request(id: string) {
    if (byId.get(id)?.has_children)
      setRequestedParents((current) => new Set(current).add(id));
  }
  function select(id: string) {
    const group = byId.get(id);
    if (!group) return;
    setNodeId(id);
    setAllGroupsReport(false);
    request(id);
    const owner = roots.find((item) => item.id === id || within(group, item));
    if (owner && owner.id !== root?.id) setRootChoice(owner.id);
    // Reveal the row: expand its ancestors, re-rooting when it sits too deep.
    const chain: Group[] = [];
    let parent = group.parent_id ? byId.get(group.parent_id) : undefined;
    while (parent && parent.id !== (owner?.id ?? null)) {
      chain.unshift(parent);
      parent = parent.parent_id ? byId.get(parent.parent_id) : undefined;
    }
    const base = owner ?? root;
    const relative = group.level - (base?.level ?? 0) - 1;
    const anchor =
      relative >= MAX_DEPTH && group.parent_id
        ? byId.get(group.parent_id)
        : undefined;
    setTableChoice(anchor?.id ?? null);
    setExpanded((current) => {
      const next = new Set(current);
      chain.forEach((item) => next.add(item.id));
      return next;
    });
    chain.forEach((item) => request(item.id));
  }
  function toggle(group: Group) {
    if (depth(group) >= MAX_DEPTH - 1) {
      setTableChoice(group.id);
      request(group.id);
      return;
    }
    const open = isExpanded(group.id);
    setExpandAll(false);
    setExpanded((current) => {
      const next = new Set(current);
      if (expandAll)
        rows
          .filter((row) => isExpanded(row.id))
          .forEach((row) => next.add(row.id));
      if (open) next.delete(group.id);
      else next.add(group.id);
      return next;
    });
    if (!open) request(group.id);
  }
  function chooseRoot(id: string) {
    setRootChoice(id);
    setTableChoice(null);
    setNodeId(null);
  }

  const refreshing =
    rootsQuery.isFetching ||
    totals.isFetching ||
    childQueries.some((query) => query.isFetching);
  const refreshButton = (
    <button
      type="button"
      disabled={refreshing}
      onClick={() => {
        void rootsQuery.refetch();
        void totals.refetch();
        childQueries.forEach((query) => {
          void query.refetch();
        });
        if (selected) void detail.refetch();
      }}
      className="min-h-10 rounded-lg border border-line-input bg-card px-3 text-sm text-ink-2 hover:bg-canvas disabled:opacity-50"
    >
      Refresh organization
    </button>
  );

  if (rootsQuery.isPending)
    return <p className="p-8 text-sm text-ink-4">Loading organization…</p>;
  if (rootsQuery.error)
    return (
      <div className="flex flex-col items-start gap-3 p-8">
        <p
          role="alert"
          className="rounded-lg border border-danger-line bg-danger-tint p-4 text-sm text-danger"
        >
          {rootsQuery.error.message}
        </p>
        {refreshButton}
      </div>
    );
  if (!enabled)
    return (
      <div className="p-8">
        <section className="rounded-xl border border-line bg-card p-8">
          <Network className="text-blue" aria-hidden="true" />
          <h1 className="mt-4 text-lg font-semibold text-ink">Organization</h1>
          <p className="mt-2 text-sm text-ink-4">
            Configure organizationHierarchy in your deployment configuration to
            organize users and manage their budgets.
          </p>
          <div className="mt-4">{refreshButton}</div>
        </section>
      </div>
    );

  const rootTotals = root ? full.get(root.id) : undefined;
  const subtree = [...full.values()].filter(
    (group) => root && within(group, root),
  );
  const near = subtree.filter(
    (group) => (percent(group.group_spend, group.group_total) ?? 0) >= NEAR,
  );
  const issues = rootsQuery.data?.issues ?? [];
  const syncErrors = subtree.filter((group) => group.sync_error);
  const attention: Array<{
    key: string;
    tone: string;
    title: string;
    sub: string;
    action: string;
    button: string;
    onClick: () => void;
  }> = [
    ...subtree
      .map((group) => ({
        group,
        used: percent(group.group_spend, group.group_total) ?? 0,
      }))
      .filter((item) => item.used >= ATTENTION)
      .sort((left, right) => right.used - left.used)
      .map(({ group, used }) => ({
        key: `budget-${group.id}`,
        tone: "bg-sand",
        title: `${group.name} at ${used}%`,
        sub: group.path.join(" › "),
        action: "Review",
        button: "bg-sand-tint text-sand-ink",
        onClick: () => select(group.id),
      })),
    ...(issues.length
      ? [
          {
            key: "issues",
            tone: "bg-blue",
            title: `${plural(issues.length, "person")} without a group`,
            sub: issues[0].error,
            action: showIssues ? "Hide" : "Details",
            button: "bg-blue-tint text-blue-ink",
            onClick: () => setShowIssues((value) => !value),
          },
        ]
      : []),
    ...syncErrors.map((group) => ({
      key: `sync-${group.id}`,
      tone: "bg-periwinkle",
      title: `${group.name} policy not synced`,
      sub: group.sync_error ?? "",
      action: "View",
      button: "bg-periwinkle-tint text-periwinkle-ink",
      onClick: () => select(group.id),
    })),
  ].slice(0, 3);
  const healthy =
    (!status.data || status.data.ready) && !issues.length && !syncErrors.length;
  const directChildren = groups.filter((group) => group.parent_id === root?.id);
  const splitTotal = directChildren.reduce(
    (sum, group) => sum + (group.group_spend ?? 0),
    0,
  );
  const rootLevel = root ? levels[root.level] : undefined;
  const childLevel = (group: Group) => levels[group.level + 1];
  const tableChain: Group[] = [];
  for (
    let item: Group | undefined = tableRoot;
    item && root && item.id !== root.id;
    item = item.parent_id ? byId.get(item.parent_id) : undefined
  )
    tableChain.unshift(item);
  const childCount = (group: Group) =>
    groups.filter((item) => item.parent_id === group.id).length;
  const reportNode = selected ? selected.id : allGroupsReport ? "" : null;

  return (
    <div className="flex flex-wrap content-start">
      <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-[22px] px-4 py-7 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-3.5">
          <div>
            <h1 className="text-[28px] font-bold tracking-[-0.01em] text-ink">
              {greeting(email)}
            </h1>
            <p className="mt-1 text-[15px] text-ink-3">
              {status.data && !status.data.ready
                ? "The gateway is not ready."
                : healthy
                  ? "Everything is healthy."
                  : "Some items need attention."}
              {near.length > 0 && (
                <>
                  {" "}
                  <span className="font-semibold text-sand-ink">
                    {plural(near.length, "group")}
                  </span>{" "}
                  {near.length === 1 ? "is" : "are"} close to their budget
                </>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            {roots.length > 1 && (
              <>
                {rootLevel && (
                  <span className="text-xs font-semibold tracking-[0.04em] text-ink-4">
                    {rootLevel.toUpperCase()}
                  </span>
                )}
                <div
                  role="tablist"
                  aria-label={rootLevel ?? "Organization root"}
                  className="flex flex-wrap gap-1 rounded-[10px] bg-well p-1"
                >
                  {roots.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      role="tab"
                      aria-selected={item.id === root?.id}
                      onClick={() => chooseRoot(item.id)}
                      className={`min-h-9 rounded-[7px] px-3.5 text-sm ${
                        item.id === root?.id
                          ? "bg-card font-semibold text-ink shadow-[0_1px_2px_rgba(0,0,0,0.06)]"
                          : "text-ink-3 hover:text-ink"
                      }`}
                    >
                      {item.name}
                    </button>
                  ))}
                </div>
              </>
            )}
            {refreshButton}
          </div>
        </div>

        {root && (
          <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              accent="border-t-teal"
              caption="SPEND THIS PERIOD"
              sub={`of ${root.group_total == null ? "no target" : shortMoney(root.group_total)} · ${root.name} + all sub-groups`}
              bar={percent(rootTotals?.group_spend, root.group_total)}
            >
              {totals.isPending ? (
                <span className="h-8 w-24 animate-pulse rounded bg-line-soft" />
              ) : (
                shortMoney(rootTotals?.group_spend)
              )}
            </Metric>
            <Metric
              accent="border-t-blue"
              caption="PEOPLE"
              sub={`across ${plural(subtree.length || childCount(root), "group")}`}
            >
              {root.members.toLocaleString()}
            </Metric>
            <Metric
              accent="border-t-sand"
              caption="NEAR BUDGET"
              sub={`groups over ${NEAR}% used`}
            >
              {totals.isPending ? "—" : near.length}
            </Metric>
            {isAdmin && (
              <Metric
                accent="border-t-mint"
                caption="LITELLM GATEWAY"
                sub={
                  status.data
                    ? `DB ${status.data.dependencies?.database?.ok ? "ok" : "down"} · LiteLLM ${status.data.dependencies?.litellm?.ok ? "ok" : "down"}`
                    : status.isError
                      ? "Status unavailable"
                      : "Checking…"
                }
              >
                <span
                  aria-hidden="true"
                  className={`h-2 w-2 rounded-full ${
                    status.data?.ready ? "bg-mint" : "bg-danger"
                  }`}
                />
                {status.data
                  ? status.data.ready
                    ? "Ready"
                    : "Not ready"
                  : "—"}
              </Metric>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-4">
          {root && directChildren.length > 0 && (
            <section
              aria-label="Spend split"
              className="flex min-w-0 flex-[999_1_420px] flex-col gap-3.5 rounded-xl border border-line bg-card px-5 py-[18px]"
            >
              <div className="flex flex-wrap justify-between gap-2 text-sm">
                <span className="font-semibold text-ink">
                  Where {root.name}’s budget goes{" "}
                  <span className="font-normal text-ink-4">
                    · by {childLevel(root)?.toLowerCase() ?? "group"}, incl.
                    sub-groups
                  </span>
                </span>
                <span className="text-ink-4">
                  {totals.isPending
                    ? "Loading…"
                    : `${shortMoney(rootTotals?.group_spend)} spent`}
                </span>
              </div>
              {totals.isPending ? (
                <span className="h-3.5 animate-pulse rounded-[7px] bg-line-soft" />
              ) : splitTotal > 0 ? (
                <div
                  role="img"
                  aria-label={`Spend split across ${plural(directChildren.length, childLevel(root) ?? "group")}`}
                  className="flex h-3.5 gap-0.5 overflow-hidden rounded-[7px]"
                >
                  {directChildren
                    .filter((group) => (group.group_spend ?? 0) > 0)
                    .map((group) => (
                      <span
                        key={group.id}
                        className={hue(group).bar}
                        style={{ flex: `${group.group_spend} 1 0` }}
                      />
                    ))}
                </div>
              ) : (
                <p className="text-sm text-ink-4">No spend this period yet.</p>
              )}
              <div className="flex flex-wrap gap-x-[18px] gap-y-2 text-[13px] text-ink-2">
                {directChildren.map((group) => (
                  <span
                    key={group.id}
                    className="inline-flex items-center gap-1.5"
                  >
                    <span
                      aria-hidden="true"
                      className={`h-[9px] w-[9px] rounded-[3px] ${hue(group).bar}`}
                    />
                    {group.name}{" "}
                    <span className="text-ink-4">
                      {shortMoney(group.group_spend)}
                    </span>
                  </span>
                ))}
              </div>
            </section>
          )}

          <section
            aria-label="Needs attention"
            className="flex flex-[1_1_300px] flex-col rounded-xl border border-line bg-card px-5 py-4"
          >
            <h2 className="mb-1.5 text-sm font-semibold text-ink">
              Needs attention
            </h2>
            {attention.length ? (
              attention.map((item) => (
                <div
                  key={item.key}
                  className="flex items-center justify-between gap-2.5 border-t border-line-soft py-2.5"
                >
                  <span className="inline-flex min-w-0 items-center gap-2.5">
                    <span
                      aria-hidden="true"
                      className={`h-2 w-2 shrink-0 rounded-full ${item.tone}`}
                    />
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-ink">
                        {item.title}
                      </span>
                      <span className="block truncate text-xs text-ink-4">
                        {item.sub}
                      </span>
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={item.onClick}
                    aria-label={`${item.action}: ${item.title}`}
                    className={`min-h-9 shrink-0 rounded-lg px-3 text-[13px] font-semibold ${item.button}`}
                  >
                    {item.action}
                  </button>
                </div>
              ))
            ) : (
              <p className="border-t border-line-soft py-2.5 text-sm text-ink-4">
                {totals.isPending ? "Checking…" : "Nothing needs attention."}
              </p>
            )}
          </section>
        </div>

        {showIssues && issues.length > 0 && (
          <DismissibleMessage
            role="alert"
            messageKey={issues
              .map((issue) => `${issue.user_id}:${issue.error}`)
              .join("|")}
            className="rounded-xl border border-sand/40 bg-sand-tint p-4 text-sm text-sand-ink"
          >
            <p className="font-medium">Some memberships need attention</p>
            <ul className="mt-2 space-y-1">
              {issues.map((issue, index) => (
                <li key={`${issue.user_id}-${index}`}>
                  {issue.user_id}: {issue.error}
                </li>
              ))}
            </ul>
          </DismissibleMessage>
        )}

        {tableRoot && (
          <section
            aria-label="Groups"
            className="overflow-hidden rounded-xl border border-line bg-card"
          >
            <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-line px-5 py-3.5">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-base font-bold text-ink">
                  Groups in {tableRoot.name}
                </h2>
                <button
                  type="button"
                  aria-pressed={nodeId === tableRoot.id}
                  aria-label={`${tableRoot.name}, ${plural(tableRoot.members, "user")}`}
                  onClick={() => select(tableRoot.id)}
                  className="min-h-8 rounded-lg px-2 text-[13px] font-semibold text-blue-ink hover:bg-blue-tint"
                >
                  Open {tableRoot.name}
                </button>
                <nav
                  aria-label={tableChain.length ? "Table path" : "Levels"}
                  className="inline-flex flex-wrap items-center gap-1.5 text-xs text-ink-3"
                >
                  {tableChain.length
                    ? [root!, ...tableChain].map((item, index, all) => (
                        <span key={item.id} className="inline-flex gap-1.5">
                          {index > 0 && <span aria-hidden="true">›</span>}
                          {index < all.length - 1 ? (
                            <button
                              type="button"
                              onClick={() =>
                                setTableChoice(
                                  item.id === root!.id ? null : item.id,
                                )
                              }
                              className="rounded-md bg-line-soft px-2 py-[3px] text-blue-ink hover:underline"
                            >
                              {item.name}
                            </button>
                          ) : (
                            <span
                              aria-current="location"
                              className="rounded-md bg-line-soft px-2 py-[3px]"
                            >
                              {item.name}
                            </span>
                          )}
                        </span>
                      ))
                    : levels.slice(tableRoot.level).map((level, index) => (
                        <span key={level} className="inline-flex gap-1.5">
                          {index > 0 && <span aria-hidden="true">›</span>}
                          <span className="rounded-md bg-line-soft px-2 py-[3px]">
                            {level}
                          </span>
                        </span>
                      ))}
                </nav>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (expandAll) setExpanded(new Set());
                    setExpandAll((value) => !value);
                  }}
                  className="min-h-10 rounded-lg border border-line-input bg-card px-3 text-sm text-ink-2 hover:bg-canvas"
                >
                  {expandAll ? "Collapse all" : "Expand all"}
                </button>
                {!selected && (
                  <button
                    type="button"
                    onClick={() => setAllGroupsReport(true)}
                    aria-label={`All groups, ${plural(rootsQuery.data?.total_users ?? 0, "user")}`}
                    aria-pressed={allGroupsReport}
                    className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-teal px-3.5 text-sm font-semibold text-paper hover:brightness-110"
                  >
                    <BarChart3 size={15} aria-hidden="true" />
                    Usage report
                  </button>
                )}
              </div>
            </div>
            <div className="overflow-x-auto">
              <div
                className={`${columns} border-b border-line-soft bg-canvas/60 px-5 py-2.5 text-xs font-semibold tracking-[0.04em] text-ink-4`}
              >
                <span>GROUP</span>
                <span>PEOPLE</span>
                <span>SPEND · INCL. SUB-GROUPS</span>
                <span>PER PERSON</span>
              </div>
              <div role="list" aria-label="Organization groups">
                {rows.map((group) => {
                  const level = levels[group.level];
                  const children = childLevel(group);
                  const count = childCount(group);
                  const used = percent(group.group_spend, group.group_total);
                  const parent = group.parent_id
                    ? byId.get(group.parent_id)
                    : undefined;
                  const tag =
                    group.budget_source && group.budget_source !== group.id
                      ? "inherited"
                      : parent
                        ? "override"
                        : "set here";
                  const color = hue(group);
                  const active = group.id === nodeId;
                  const open = isExpanded(group.id);
                  return (
                    <div
                      role="listitem"
                      key={group.id}
                      className={`relative ${columns} border-b border-line-soft px-5 py-[11px] text-sm text-ink ${
                        active
                          ? "bg-blue-tint/60 shadow-[inset_3px_0_0_rgb(var(--blue))]"
                          : "hover:bg-canvas/70"
                      }`}
                    >
                      <button
                        type="button"
                        aria-pressed={active}
                        aria-label={`${group.name}, ${plural(group.members, "user")}`}
                        onClick={() => select(group.id)}
                        className="absolute inset-0 z-0 w-full"
                      />
                      <span
                        className="pointer-events-none relative inline-flex min-w-0 items-center gap-2"
                        style={{
                          paddingLeft: Math.max(0, depth(group)) * 34,
                        }}
                      >
                        {group.has_children ? (
                          <button
                            type="button"
                            aria-expanded={open}
                            aria-label={`${open ? "Collapse" : "Expand"} ${group.path.join(" → ")}`}
                            onClick={() => toggle(group)}
                            className="pointer-events-auto relative z-10 -ml-1.5 inline-flex h-7 w-7 items-center justify-center rounded text-sm text-ink-3 hover:bg-well"
                          >
                            <span aria-hidden="true">{open ? "▾" : "▸"}</span>
                          </button>
                        ) : (
                          <span className="w-4" />
                        )}
                        <span
                          aria-hidden="true"
                          className={`inline-flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-[7px] text-[11px] font-bold ${
                            depth(group) === 0
                              ? `${color.tint} ${color.ink}`
                              : `bg-canvas ${color.ink}`
                          }`}
                        >
                          {groupInitials(group.name)}
                        </span>
                        <span className="min-w-0">
                          <span
                            className={`block truncate ${group.has_children ? "font-semibold" : "font-medium"}`}
                          >
                            {group.name}
                          </span>
                          <span className="block text-xs text-ink-4">
                            {[
                              level,
                              group.has_children && children && count
                                ? plural(count, children)
                                : null,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </span>
                      </span>
                      <span className="pointer-events-none relative text-ink-3">
                        {group.members}
                      </span>
                      <span className="pointer-events-none relative flex flex-col gap-[5px]">
                        {totals.isPending ? (
                          <>
                            <span className="h-3.5 w-28 animate-pulse rounded bg-line-soft" />
                            <span className="h-[5px] animate-pulse rounded-[3px] bg-line-soft" />
                          </>
                        ) : (
                          <>
                            <span className="flex justify-between text-[13px]">
                              <span>
                                {shortMoney(group.group_spend)}{" "}
                                <span className="text-ink-4">
                                  /{" "}
                                  {group.group_total == null
                                    ? "no target"
                                    : shortMoney(group.group_total)}
                                </span>
                              </span>
                              {used != null && (
                                <span
                                  className={`font-semibold ${used >= NEAR ? "text-sand-ink" : "text-ink-3"}`}
                                >
                                  {used}%
                                </span>
                              )}
                            </span>
                            <span className="block h-[5px] rounded-[3px] bg-line-soft">
                              <span
                                className={`block h-[5px] rounded-[3px] ${color.bar}`}
                                style={{
                                  width: `${Math.min(100, used ?? 0)}%`,
                                }}
                              />
                            </span>
                          </>
                        )}
                      </span>
                      <span className="pointer-events-none relative text-[13px] text-ink-3">
                        {group.per_user == null
                          ? "No limit"
                          : shortMoney(group.per_user)}{" "}
                        <span className="text-xs text-ink-4">{tag}</span>
                      </span>
                    </div>
                  );
                })}
              </div>
              {childQueries.map((query, index) =>
                query.error ? (
                  <p
                    key={[...requestedParents][index]}
                    role="alert"
                    className="px-5 py-2.5 text-[13px] text-danger"
                  >
                    {query.error.message}{" "}
                    <button
                      type="button"
                      className="font-semibold underline"
                      onClick={() => void query.refetch()}
                    >
                      Retry children
                    </button>
                  </p>
                ) : query.isPending ? (
                  <p
                    key={[...requestedParents][index]}
                    className="px-5 py-2.5 text-[13px] text-ink-4"
                  >
                    Loading child groups...
                  </p>
                ) : null,
              )}
              {totals.error && (
                <p role="alert" className="px-5 py-2.5 text-[13px] text-danger">
                  Spend totals are unavailable: {totals.error.message}
                </p>
              )}
              <p className="px-5 pb-3 pt-2.5 text-[13px] text-ink-4">
                Sub-groups load when you open them
                {levels.length - tableRoot.level - 1 > MAX_DEPTH
                  ? " · deeper levels open in their own view"
                  : ""}
              </p>
            </div>
          </section>
        )}

        {reportNode !== null && (
          <OrgReport
            key={reportNode}
            nodeId={reportNode}
            selected={selected}
            nextLevel={selected ? childLevel(selected) : levels[0]}
            totalUsers={rootsQuery.data?.total_users}
            onSelectChild={select}
          />
        )}
      </div>

      {selected && (
        <GroupPanel
          key={selected.id}
          group={selected}
          hue={hue(selected)}
          parent={selected.parent_id ? byId.get(selected.parent_id) : undefined}
          source={
            selected.budget_source && selected.budget_source !== selected.id
              ? byId.get(selected.budget_source)
              : undefined
          }
          levelName={levels[selected.level]}
          childLevelName={childLevel(selected)}
          subGroups={groups
            .filter((group) => group.parent_id === selected.id)
            .map((group) => ({ group, hue: hue(group) }))}
          totalSpend={totals.isPending ? undefined : selected.group_spend}
          ownSpend={detail.data?.group_spend}
          ownSpendState={
            detail.isPending ? "loading" : detail.error ? "error" : "ready"
          }
          budgetGroup={budgets.data?.groups.find(
            (group) => group.id === selected.id,
          )}
          revision={budgets.data?.revision}
          onClose={() => setNodeId(null)}
          onSelect={select}
        />
      )}
    </div>
  );
}
