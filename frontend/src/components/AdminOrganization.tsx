import { useEffect, useRef, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { BarChart3, Network } from "lucide-react";
import { api } from "../api/client";
import DismissibleMessage from "./DismissibleMessage";
import GroupPanel from "./organization/GroupPanel";
import OrgReport from "./organization/OrgReport";
import {
  groupInitials,
  hueFor,
  palette,
  limitOrigin,
  percent,
  plural,
  reached,
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
      <span className="text-xs font-semibold uppercase tracking-[0.04em] text-ink-4">
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
  // Selected top-level departments; empty means the first one.
  const [rootChoices, setRootChoices] = useState<string[]>([]);
  const [tableChoice, setTableChoice] = useState<string | null>(null);
  const [nodeId, setNodeId] = useState<string | null>(null);
  const [allGroupsReport, setAllGroupsReport] = useState(false);
  const [requestedParents, setRequestedParents] = useState<Set<string>>(
    () => new Set(),
  );
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [expandAll, setExpandAll] = useState(false);
  const [showIssues, setShowIssues] = useState(false);
  const [showAllAttention, setShowAllAttention] = useState(false);
  const opener = useRef<HTMLElement | null>(null);
  const reportButton = useRef<HTMLButtonElement | null>(null);

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
  // Descendant spend totals from the server's shared, minute-old team listing.
  const totals = useQuery({
    queryKey: ["organization-overview"],
    queryFn: api.organization,
    enabled,
    // Once per page open (and on Refresh); served from the shared team listing.
    staleTime: 60000,
    refetchOnWindowFocus: false,
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

  const chosen = roots.filter((item) => rootChoices.includes(item.id));
  const activeRoots = (chosen.length ? chosen : roots.slice(0, 1)).map(
    (item): Group => byId.get(item.id) ?? item,
  );
  const activeIds = activeRoots.map((item) => item.id);
  const multi = activeRoots.length > 1;
  const allActive = activeRoots.length === roots.length;
  // With one department the page works inside it; with several it combines them.
  const root = multi ? undefined : activeRoots[0];
  const ownerOf = (group: Group) =>
    activeRoots.find((item) => item.id === group.id || within(group, item));
  const drilled = byId.get(tableChoice ?? "");
  const tableRoot = drilled && ownerOf(drilled) ? drilled : root;
  // Rows indent from the table base; several departments start one level up.
  const baseLevel = tableRoot
    ? tableRoot.level
    : (activeRoots[0]?.level ?? 0) - 1;
  const rootChildren = groups
    .filter((group) => group.parent_id === root?.id)
    .map((group) => group.id);
  const hue = (group: Group) =>
    multi || group.id === root?.id
      ? hueFor(
          group,
          null,
          byId,
          roots.map((item) => item.id),
        )
      : hueFor(group, root?.id ?? null, byId, rootChildren);
  const depth = (group: Group) => group.level - baseLevel - 1;
  const isExpanded = (id: string) => {
    const group = byId.get(id);
    if (!group?.has_children) return false;
    return expanded.has(id) || (expandAll && depth(group) < MAX_DEPTH - 1);
  };
  // A single team without sub-teams lists itself, like the admin view's rows.
  const rows = tableRoot
    ? tableRoot.has_children
      ? treeOrder(groups, isExpanded, tableRoot.id)
      : [tableRoot]
    : activeRoots.flatMap((item) => [
        item,
        ...(isExpanded(item.id) ? treeOrder(groups, isExpanded, item.id) : []),
      ]);

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
  function closeGroup() {
    setNodeId(null);
    // The panel unmounts; put focus back where the user started.
    requestAnimationFrame(() => {
      if (opener.current?.isConnected) opener.current.focus();
      opener.current = null;
    });
  }
  function closeAllGroupsReport() {
    setAllGroupsReport(false);
    requestAnimationFrame(() => reportButton.current?.focus());
  }
  function select(id: string) {
    const group = byId.get(id);
    if (!group) return;
    const active = document.activeElement;
    if (active instanceof HTMLElement && !active.closest("[data-group-panel]"))
      opener.current = active;
    setNodeId(id);
    setAllGroupsReport(false);
    request(id);
    const owner = roots.find((item) => item.id === id || within(group, item));
    const combined = multi && !!owner;
    if (owner && !activeIds.includes(owner.id))
      setRootChoices(multi ? [...activeIds, owner.id] : [owner.id]);
    // Reveal the row: expand its ancestors, re-rooting when it sits too deep.
    // In a combined view the department row itself must be open too.
    const chain: Group[] = combined && owner && owner.id !== id ? [owner] : [];
    let parent = group.parent_id ? byId.get(group.parent_id) : undefined;
    while (parent && parent.id !== (owner?.id ?? null)) {
      chain.splice(combined ? 1 : 0, 0, parent);
      parent = parent.parent_id ? byId.get(parent.parent_id) : undefined;
    }
    const base = owner ?? root;
    const relative = group.level - (base?.level ?? 0) - (combined ? 0 : 1);
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
  function chooseRoots(ids: string[]) {
    if (!ids.length) return;
    // Keep configuration order, and open each department in a combined view.
    const next = roots.map((item) => item.id).filter((id) => ids.includes(id));
    setRootChoices(next);
    setTableChoice(null);
    setNodeId(null);
    setShowAllAttention(false);
    if (next.length > 1) {
      setExpanded((current) => new Set([...current, ...next]));
      next.forEach(request);
    }
  }
  const toggleRoot = (id: string) =>
    chooseRoots(
      activeIds.includes(id)
        ? activeIds.filter((item) => item !== id)
        : [...activeIds, id],
    );

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

  const rootTotals = activeRoots
    .map((item) => full.get(item.id))
    .filter((item): item is OrganizationGroup => !!item);
  const subtree = [...full.values()].filter((group) =>
    activeRoots.some((item) => within(group, item)),
  );
  // Health checks cover the selected departments themselves, not only their
  // descendants: their own LiteLLM teams can fail or near budget too.
  const checked = [...rootTotals, ...subtree];
  const spendKnown =
    rootTotals.length === activeRoots.length &&
    rootTotals.every((item) => item.group_spend != null);
  const combinedSpend = spendKnown
    ? rootTotals.reduce((sum, item) => sum + (item.group_spend ?? 0), 0)
    : undefined;
  const combinedTarget = activeRoots.every((item) => item.group_total != null)
    ? activeRoots.reduce((sum, item) => sum + (item.group_total ?? 0), 0)
    : null;
  const combinedMembers = activeRoots.reduce(
    (sum, item) => sum + item.members,
    0,
  );
  const scopeName = activeRoots.map((item) => item.name).join(" + ");
  const near = checked.filter((group) =>
    reached(group.group_spend, group.group_total, NEAR),
  );
  const issues = rootsQuery.data?.issues ?? [];
  const syncErrors = checked.filter((group) => group.sync_error);
  const attention: Array<{
    key: string;
    tone: string;
    title: string;
    sub: string;
    action: string;
    button: string;
    onClick: () => void;
  }> = [
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
    // Budget warnings come last so they never push problems out of view.
    ...checked
      .filter((group) =>
        reached(group.group_spend, group.group_total, ATTENTION),
      )
      .map((group) => ({
        group,
        used: percent(group.group_spend, group.group_total) ?? 0,
      }))
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
  ];
  const attentionExpanded = showAllAttention && attention.length > 3;
  // A list that shrinks to three or fewer starts collapsed when it grows again.
  if (showAllAttention && attention.length <= 3) setShowAllAttention(false);
  const shownAttention = attentionExpanded ? attention : attention.slice(0, 3);
  // Only claim health once every signal shown here has actually loaded.
  const gatewayReady = isAdmin ? status.data?.ready === true : true;
  const healthy =
    gatewayReady &&
    !totals.isPending &&
    !totals.isError &&
    !issues.length &&
    !syncErrors.length;
  // A single department splits by its children; several by department.
  const directChildren = multi
    ? activeRoots
    : groups.filter((group) => group.parent_id === root?.id);
  const splitTotal = directChildren.reduce(
    (sum, group) => sum + (group.group_spend ?? 0),
    0,
  );
  const rootLevel = activeRoots[0] ? levels[activeRoots[0].level] : undefined;
  const childLevel = (group: Group) => levels[group.level + 1];
  const splitLevel = multi ? rootLevel : root && childLevel(root);
  const chainRoot = tableRoot ? ownerOf(tableRoot) : undefined;
  const tableChain: Group[] = [];
  for (
    let item: Group | undefined = tableRoot;
    item && chainRoot && item.id !== chainRoot.id;
    item = item.parent_id ? byId.get(item.parent_id) : undefined
  )
    tableChain.unshift(item);
  const childCount = (group: Group) =>
    groups.filter((item) => item.parent_id === group.id).length;
  // A single team without sub-teams has nothing to drill into.
  const leafScope = !multi && !!root && !root.has_children;
  // Every department selected reports on all groups; otherwise the selection.
  const reportNodes = selected
    ? [selected.id]
    : allGroupsReport
      ? allActive
        ? []
        : activeIds
      : null;
  // "All groups" only when several departments are combined; a single one
  // (for example a team owner's own team) is named.
  const reportScope = allActive && roots.length > 1 ? "all groups" : scopeName;
  // Owners see their team's budget plan in place of the admin-only gateway.
  const plannedRows =
    budgets.data?.groups.filter((group) => activeIds.includes(group.id)) ?? [];
  const planned =
    plannedRows.length === activeRoots.length && plannedRows.length > 0
      ? {
          assigned: plannedRows.reduce((sum, group) => sum + group.assigned, 0),
          allocated: plannedRows.every((group) => group.allocated != null)
            ? plannedRows.reduce((sum, group) => sum + group.allocated!, 0)
            : null,
        }
      : null;
  const splitOut = planned?.allocated ?? null;
  // A planned budget is the team's effective target.
  const spendTarget = planned ? planned.assigned : combinedTarget;
  const reportUsers = allActive
    ? (rootsQuery.data?.total_users ?? 0)
    : combinedMembers;

  return (
    <div className="flex flex-wrap content-start min-[1140px]:flex-nowrap">
      {/* First in the page so narrow screens show it above the report;
          wide screens move it beside the report. */}
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
            // Descendants share their branch colour in the table; in the
            // panel each sub-group needs its own to tell segments apart.
            .map((group, index) => ({
              group,
              hue: palette[index % palette.length],
            }))}
          totalSpend={totals.isPending ? undefined : selected.group_spend}
          ownSpend={detail.data?.group_spend}
          ownSpendState={
            detail.isPending ? "loading" : detail.error ? "error" : "ready"
          }
          budgetGroup={budgets.data?.groups.find(
            (group) => group.id === selected.id,
          )}
          revision={budgets.data?.revision}
          onClose={closeGroup}
          onSelect={select}
        />
      )}
      <div className="flex min-w-0 flex-[999_1_560px] flex-col gap-[22px] px-4 py-7 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-3.5">
          <div>
            <h1 className="text-xs font-semibold uppercase tracking-[0.06em] text-ink-4">
              Organization
            </h1>
            <p className="mt-0.5 text-[28px] font-bold tracking-[-0.01em] text-ink">
              {greeting(email)}
            </p>
            <p className="mt-1 text-[15px] text-ink-3">
              {status.data && !status.data.ready
                ? "The gateway is not ready."
                : healthy
                  ? "Everything is healthy."
                  : issues.length || syncErrors.length
                    ? "Some items need attention."
                    : isAdmin && status.isError
                      ? "Gateway status is unavailable."
                      : totals.isError
                        ? "Group spend is unavailable."
                        : "Checking status…"}
              {near.length > 0 && (
                <>
                  {" "}
                  <span className="font-semibold text-sand-ink">
                    {plural(near.length, "group")}
                  </span>{" "}
                  {near.length === 1 ? "is" : "are"} at {NEAR}% or more of their
                  budget
                </>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            {roots.length === 1 && rootLevel && (
              // One team (a team owner's): name it where the picker would be.
              <>
                <span className="text-xs font-semibold uppercase tracking-[0.04em] text-ink-4">
                  {rootLevel}
                </span>
                <span className="flex rounded-[10px] bg-well p-1">
                  <span className="flex min-h-9 items-center rounded-[7px] bg-card px-3.5 text-sm font-semibold text-ink shadow-[0_1px_2px_rgba(0,0,0,0.06)]">
                    {roots[0].name}
                  </span>
                </span>
              </>
            )}
            {roots.length > 1 && (
              <>
                {rootLevel && (
                  <span className="text-xs font-semibold uppercase tracking-[0.04em] text-ink-4">
                    {rootLevel}
                  </span>
                )}
                <div
                  role="group"
                  aria-label={rootLevel ?? "Organization root"}
                  className="flex flex-wrap gap-1 rounded-[10px] bg-well p-1"
                >
                  {[
                    {
                      id: "all",
                      name: "All",
                      pressed: allActive,
                      onClick: () => chooseRoots(roots.map((item) => item.id)),
                    },
                    ...roots.map((item) => ({
                      id: item.id,
                      name: item.name,
                      pressed: activeIds.includes(item.id),
                      onClick: () => toggleRoot(item.id),
                    })),
                  ].map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      aria-pressed={item.pressed}
                      onClick={item.onClick}
                      className={`min-h-9 rounded-[7px] px-3.5 text-sm ${
                        item.pressed
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

        {activeRoots.length > 0 && (
          <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              accent="border-t-teal"
              caption="Spend this period"
              sub={`of ${spendTarget == null ? "no target" : shortMoney(spendTarget)} · ${scopeName}${leafScope ? "" : " + all sub-groups"}`}
              bar={percent(combinedSpend, spendTarget)}
            >
              {totals.isPending ? (
                <span className="h-8 w-24 animate-pulse rounded bg-line-soft" />
              ) : (
                shortMoney(combinedSpend)
              )}
            </Metric>
            <Metric
              accent="border-t-blue"
              caption="People"
              sub={
                leafScope
                  ? `in ${scopeName}`
                  : `across ${plural(subtree.length || activeRoots.reduce((sum, item) => sum + childCount(item), 0), "group")}`
              }
            >
              {combinedMembers.toLocaleString()}
            </Metric>
            <Metric
              accent="border-t-sand"
              caption="Near budget"
              sub={`groups at ${NEAR}% or more used`}
            >
              {totals.isPending ? "—" : near.length}
            </Metric>
            {isAdmin && (
              <Metric
                accent="border-t-mint"
                caption="LiteLLM gateway"
                sub={
                  status.data
                    ? `DB ${status.data.dependencies?.database?.ok ? "ok" : "not ok"} · LiteLLM ${status.data.dependencies?.litellm?.ok ? "ok" : "not ok"}`
                    : status.isError
                      ? "Status unavailable"
                      : "Checking…"
                }
              >
                <span
                  aria-hidden="true"
                  className={`h-2 w-2 rounded-full ${
                    !status.data
                      ? "bg-ink-5"
                      : status.data.ready
                        ? "bg-mint"
                        : "bg-danger"
                  }`}
                />
                {status.data
                  ? status.data.ready
                    ? "Ready"
                    : "Not ready"
                  : "—"}
              </Metric>
            )}
            {!isAdmin && (
              <Metric
                accent="border-t-mint"
                caption="Team budget"
                sub={
                  planned
                    ? splitOut == null
                      ? "Allocation needs repair"
                      : `${shortMoney(splitOut)} split out · ${shortMoney(planned.assigned - splitOut)} left`
                    : root?.per_user != null
                      ? `${shortMoney(root.per_user)} per person`
                      : "No per-person limit"
                }
              >
                {planned
                  ? shortMoney(planned.assigned)
                  : combinedTarget == null
                    ? "No target"
                    : shortMoney(combinedTarget)}
              </Metric>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-4">
          {activeRoots.length > 0 && directChildren.length > 0 && (
            <section
              aria-label="Spend split"
              className="flex min-w-0 flex-[999_1_420px] flex-col gap-3.5 rounded-xl border border-line bg-card px-5 py-[18px]"
            >
              <div className="flex flex-wrap justify-between gap-2 text-sm">
                <span className="font-semibold text-ink">
                  Where {scopeName}’s budget goes{" "}
                  <span className="font-normal text-ink-4">
                    · by {splitLevel?.toLowerCase() ?? "group"}, incl.
                    sub-groups
                  </span>
                </span>
                <span className="text-ink-4">
                  {totals.isPending
                    ? "Loading…"
                    : `${shortMoney(combinedSpend)} spent`}
                </span>
              </div>
              {totals.isPending ? (
                <span className="h-3.5 animate-pulse rounded-[7px] bg-line-soft" />
              ) : splitTotal > 0 ? (
                <div
                  role="img"
                  aria-label={`Spend split across ${plural(directChildren.length, splitLevel ?? "group")}`}
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
              shownAttention.map((item) => (
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
            {attention.length > 3 && (
              <button
                type="button"
                onClick={() => setShowAllAttention(!attentionExpanded)}
                aria-expanded={attentionExpanded}
                className="mt-1 self-start rounded-lg px-1 py-1.5 text-[13px] font-semibold text-blue-ink hover:underline"
              >
                {attentionExpanded
                  ? "Show fewer"
                  : `Show ${attention.length - 3} more`}
              </button>
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

        {activeRoots.length > 0 && (
          <section
            aria-label="Groups"
            className="overflow-hidden rounded-xl border border-line bg-card"
          >
            <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-line px-5 py-3.5">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-base font-bold text-ink">
                  {leafScope
                    ? root.name
                    : `Groups in ${tableRoot ? tableRoot.name : scopeName}`}
                </h2>
                {tableRoot && !leafScope && (
                  <button
                    type="button"
                    aria-pressed={nodeId === tableRoot.id}
                    aria-label={`${tableRoot.name}, ${plural(tableRoot.members, "user")}`}
                    onClick={() => select(tableRoot.id)}
                    className="min-h-8 rounded-lg px-2 text-[13px] font-semibold text-blue-ink hover:bg-blue-tint"
                  >
                    Open {tableRoot.name}
                  </button>
                )}
                <nav
                  aria-label={tableChain.length ? "Table path" : "Levels"}
                  className="inline-flex flex-wrap items-center gap-1.5 text-xs text-ink-3"
                >
                  {tableChain.length
                    ? [chainRoot!, ...tableChain].map((item, index, all) => (
                        <span key={item.id} className="inline-flex gap-1.5">
                          {index > 0 && <span aria-hidden="true">›</span>}
                          {index < all.length - 1 ? (
                            <button
                              type="button"
                              onClick={() =>
                                setTableChoice(
                                  item.id === chainRoot!.id ? null : item.id,
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
                    : levels.slice(baseLevel + 1).map((level, index) => (
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
                {!leafScope && (
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
                )}
                {!selected && (
                  <button
                    type="button"
                    ref={reportButton}
                    onClick={() => setAllGroupsReport((open) => !open)}
                    aria-label={`${allGroupsReport ? "Hide report" : "Usage report"}, ${reportScope}, ${plural(reportUsers, "user")}`}
                    className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-teal-solid px-3.5 text-sm font-semibold text-paper hover:brightness-90"
                  >
                    <BarChart3 size={15} aria-hidden="true" />
                    {allGroupsReport ? "Hide report" : "Usage report"}
                  </button>
                )}
              </div>
            </div>
            <div className="overflow-x-auto">
              <div
                className={`${columns} border-b border-line-soft bg-canvas px-5 py-2.5 text-xs font-semibold uppercase tracking-[0.04em] text-ink-4`}
              >
                <span>Group</span>
                <span>People</span>
                <span>Spend · incl. sub-groups</span>
                <span>Per person</span>
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
                  const tag = limitOrigin(group, parent).tag;
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
              {!leafScope && (
                <p className="px-5 pb-3 pt-2.5 text-[13px] text-ink-4">
                  Sub-groups load when you open them
                  {levels.length - baseLevel - 2 > MAX_DEPTH
                    ? " · deeper levels open in their own view"
                    : ""}
                </p>
              )}
            </div>
          </section>
        )}

        {reportNodes !== null && (
          <OrgReport
            key={reportNodes.join(",") || "all"}
            nodeIds={reportNodes}
            title={selected?.name ?? reportScope}
            selected={selected ?? (leafScope ? root : undefined)}
            nextLevel={
              selected
                ? childLevel(selected)
                : multi || allActive
                  ? rootLevel
                  : root && childLevel(root)
            }
            totalUsers={reportUsers}
            onSelectChild={select}
            // A childless team's report is the whole view, so it stays open.
            onClose={
              selected
                ? closeGroup
                : allGroupsReport
                  ? closeAllGroupsReport
                  : undefined
            }
          />
        )}
      </div>
    </div>
  );
}
