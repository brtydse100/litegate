import type {
  OrganizationGroup,
  OrganizationOverview,
  OrganizationUsage,
  OrganizationUserPage,
  UsageMetrics,
} from "../types/organization";
import type { TeamInfo } from "../types";

const groups: OrganizationGroup[] = [
  {
    id: "engineering",
    name: "Engineering",
    level: 0,
    path: ["Engineering"],
    parent_id: null,
    team_id: "demo-engineering",
    per_user: 50,
    duration: "30d",
    budget_source: "engineering",
    group_total: 1000,
    group_spend: 92.13,
    members: 3,
    sync_error: null,
  },
  {
    id: "marketing",
    name: "Marketing",
    level: 0,
    path: ["Marketing"],
    parent_id: null,
    team_id: "demo-marketing",
    per_user: 50,
    duration: "30d",
    budget_source: "marketing",
    group_total: 500,
    group_spend: 31.09,
    members: 1,
    sync_error: null,
  },
  {
    id: "infrastructure",
    name: "Infrastructure",
    level: 1,
    path: ["Engineering", "Infrastructure"],
    parent_id: "engineering",
    team_id: "demo-engineering",
    per_user: 50,
    duration: "30d",
    budget_source: "engineering",
    group_total: 1000,
    group_spend: 92.13,
    members: 2,
    sync_error: null,
  },
  {
    id: "applications",
    name: "Applications",
    level: 1,
    path: ["Engineering", "Applications"],
    parent_id: "engineering",
    team_id: "demo-engineering",
    per_user: 50,
    duration: "30d",
    budget_source: "engineering",
    group_total: 1000,
    group_spend: 92.13,
    members: 1,
    sync_error: null,
  },
  {
    id: "digital",
    name: "Digital",
    level: 1,
    path: ["Marketing", "Digital"],
    parent_id: "marketing",
    team_id: "demo-marketing",
    per_user: 50,
    duration: "30d",
    budget_source: "marketing",
    group_total: 500,
    group_spend: 31.09,
    members: 1,
    sync_error: null,
  },
  {
    id: "platform",
    name: "Platform",
    level: 2,
    path: ["Engineering", "Infrastructure", "Platform"],
    parent_id: "infrastructure",
    team_id: "demo-engineering",
    per_user: 100,
    duration: "30d",
    budget_source: "platform",
    group_total: 1000,
    group_spend: 92.13,
    members: 1,
    sync_error: null,
  },
  {
    id: "cloud",
    name: "Cloud",
    level: 2,
    path: ["Engineering", "Infrastructure", "Cloud"],
    parent_id: "infrastructure",
    team_id: "demo-engineering",
    per_user: 50,
    duration: "30d",
    budget_source: "engineering",
    group_total: 1000,
    group_spend: 92.13,
    members: 1,
    sync_error: null,
  },
  {
    id: "backend",
    name: "Backend",
    level: 2,
    path: ["Engineering", "Applications", "Backend"],
    parent_id: "applications",
    team_id: "demo-engineering",
    per_user: 50,
    duration: "30d",
    budget_source: "engineering",
    group_total: 1000,
    group_spend: 92.13,
    members: 1,
    sync_error: null,
  },
  {
    id: "social",
    name: "Social Media",
    level: 2,
    path: ["Marketing", "Digital", "Social Media"],
    parent_id: "digital",
    team_id: "demo-marketing",
    per_user: 50,
    duration: "30d",
    budget_source: "marketing",
    group_total: 500,
    group_spend: 31.09,
    members: 1,
    sync_error: null,
  },
];

const members = [
  {
    user_id: "demo-admin",
    email: "alex@example.com",
    node: "platform",
    budget_spend: 18.42,
  },
  {
    user_id: "priya",
    email: "priya@example.com",
    node: "cloud",
    budget_spend: 29.93,
  },
  {
    user_id: "maya",
    email: "maya@example.com",
    node: "backend",
    budget_spend: 43.78,
  },
  {
    user_id: "sam",
    email: "sam@example.com",
    node: "social",
    budget_spend: 31.09,
  },
];

export function organizationOverview(): OrganizationOverview {
  return {
    enabled: true,
    levels: ["Department", "Branch", "Team"],
    groups: groups.map((group) => ({
      ...group,
      team_id: `demo-${group.id}`,
      group_total: group.parent_id ? null : group.group_total,
      group_spend: selectedMembers(group.id).reduce(
        (total, member) => total + member.budget_spend,
        0,
      ),
    })),
    total_users: members.length,
    issues: [],
  };
}

export function organizationKeyPolicy(userId: string) {
  const member = members.find((item) => item.user_id === userId);
  const group = groups.find((item) => item.id === member?.node);
  return group && member
    ? {
        team_id: `demo-${group.id}`,
        max_budget: group.per_user,
        budget_duration: group.duration,
        spend: member.budget_spend,
      }
    : null;
}

export function organizationTeams(): TeamInfo[] {
  return organizationOverview().groups.map((group) => ({
    team_id: group.team_id,
    team_alias: group.path.join(" / "),
    max_budget: null,
    budget_duration: group.duration,
    spend: members
      .filter((member) => member.node === group.id)
      .reduce((total, member) => total + member.budget_spend, 0),
    models: [],
    blocked: false,
    organization_managed: true,
    members_with_roles: selectedMembers(group.id).map((member) => ({
      user_id: member.user_id,
      user_email: member.email,
      role: "user",
    })),
    mapped_groups: [],
    default_key_team: false,
  }));
}

function selectedMembers(nodeId: string | null) {
  const ancestor = groups.find((group) => group.id === nodeId);
  return members.filter((member) => {
    const group = groups.find((value) => value.id === member.node)!;
    return (
      !ancestor ||
      ancestor.path.every((name, index) => group.path[index] === name)
    );
  });
}

export function organizationUsers(
  nodeId: string | null,
  page: number,
): OrganizationUserPage {
  const selected = selectedMembers(nodeId);
  return {
    users: selected.slice((page - 1) * 25, page * 25).map((member) => {
      const group = groups.find((value) => value.id === member.node)!;
      return {
        ...member,
        path: group.path,
        per_user: group.per_user,
        duration: group.duration,
        sync_error: null,
      };
    }),
    page,
    page_size: 25,
    total: selected.length,
    total_pages: Math.max(1, Math.ceil(selected.length / 25)),
  };
}

const zero = (): UsageMetrics => ({ spend: 0, requests: 0, tokens: 0 });
function add(target: UsageMetrics, value: UsageMetrics) {
  target.spend = Math.round((target.spend + value.spend) * 100) / 100;
  target.requests += value.requests;
  target.tokens += value.tokens;
}

function memberDailyUsage(
  member: (typeof members)[number],
  time: number,
): UsageMetrics {
  const today = Date.parse(new Date().toISOString().slice(0, 10));
  const index = (time - today) / 86400000 + 29;
  if (index < 0 || index >= 30) return zero();
  const cents = Math.round(member.budget_spend * 100);
  const dailyCents = Math.floor(cents / 30) + (index < cents % 30 ? 1 : 0);
  const requests = Math.round(dailyCents / 6.5);
  return { spend: dailyCents / 100, requests, tokens: requests * 1240 };
}

export function organizationUsage(
  nodeId: string | null,
  start: string,
  end: string,
): OrganizationUsage {
  const ancestor = groups.find((group) => group.id === nodeId);
  const selected = selectedMembers(nodeId);
  const totals = zero();
  const byGroup = new Map<
    string | null,
    OrganizationUsage["by_group"][number]
  >();
  const daily: OrganizationUsage["daily"] = [];
  const byUser = selected.map((member) => ({
    id: member.user_id,
    name: member.email || member.user_id,
    ...zero(),
  }));
  const byModel = [
    { name: "gpt-5-mini", ...zero() },
    { name: "claude-sonnet-4", ...zero() },
  ];
  for (
    let time = Date.parse(start);
    time <= Date.parse(end);
    time += 86400000
  ) {
    const metrics = zero();
    selected.forEach((member, memberIndex) => {
      const group = groups.find((value) => value.id === member.node)!;
      const depth = (ancestor?.level ?? -1) + 1;
      const child = groups.find(
        (candidate) =>
          candidate.level === depth &&
          candidate.path.every((name, index) => group.path[index] === name),
      );
      const id = child?.id ?? null;
      const value = memberDailyUsage(member, time);
      const primary = {
        spend: Math.round(value.spend * 65) / 100,
        tokens: Math.round(value.tokens * 0.65),
        requests: Math.round(value.requests * 0.65),
      };
      add(byModel[0], primary);
      add(byModel[1], {
        spend: Math.round((value.spend - primary.spend) * 100) / 100,
        tokens: value.tokens - primary.tokens,
        requests: value.requests - primary.requests,
      });
      add(metrics, value);
      add(byUser[memberIndex], value);
      const bucket = byGroup.get(id) ?? {
        id,
        name: child?.name ?? "Direct members",
        ...zero(),
      };
      add(bucket, value);
      byGroup.set(id, bucket);
    });
    add(totals, metrics);
    daily.push({ date: new Date(time).toISOString().slice(0, 10), ...metrics });
  }
  return {
    start_date: start,
    end_date: end,
    totals,
    daily,
    by_group: [...byGroup.values()],
    by_user: byUser,
    by_model: byModel,
    users: selected.length,
    attribution: "current_membership",
    issues: [],
  };
}
