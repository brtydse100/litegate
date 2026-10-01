import type {
  OrganizationGroup,
  OrganizationOverview,
  OrganizationUsage,
  OrganizationUserPage,
  UsageMetrics,
} from "../types/organization";

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
    groups,
    total_users: members.length,
    issues: [],
  };
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
  target.spend += value.spend;
  target.requests += value.requests;
  target.tokens += value.tokens;
}

export function organizationUsage(
  nodeId: string | null,
  start: string,
  end: string,
): OrganizationUsage {
  const ancestor = groups.find((group) => group.id === nodeId);
  const selected = selectedMembers(nodeId);
  const totals = zero();
  const byGroup: Record<string, UsageMetrics> = {};
  const daily: OrganizationUsage["daily"] = [];
  for (
    let time = Date.parse(start);
    time <= Date.parse(end);
    time += 86400000
  ) {
    const day = new Date(time);
    const metrics = zero();
    selected.forEach((member) => {
      const group = groups.find((value) => value.id === member.node)!;
      const name = group.path[(ancestor?.level ?? -1) + 1] ?? "Direct members";
      const requests = Math.round(
        (member.budget_spend / 3) * ((day.getUTCDay() % 6) + 1),
      );
      const value = {
        spend: requests * 0.065,
        tokens: requests * 1240,
        requests,
      };
      add(metrics, value);
      add((byGroup[name] ??= zero()), value);
    });
    add(totals, metrics);
    daily.push({ date: day.toISOString().slice(0, 10), ...metrics });
  }
  return {
    start_date: start,
    end_date: end,
    totals,
    daily,
    by_group: Object.entries(byGroup).map(([name, metrics]) => ({
      name,
      ...metrics,
    })),
    by_model: [
      {
        name: "gpt-5-mini",
        spend: totals.spend * 0.65,
        tokens: Math.round(totals.tokens * 0.65),
        requests: Math.round(totals.requests * 0.65),
      },
      {
        name: "claude-sonnet-4",
        spend: totals.spend * 0.35,
        tokens: Math.round(totals.tokens * 0.35),
        requests: Math.round(totals.requests * 0.35),
      },
    ],
    users: selected.length,
    attribution: "current_membership",
    issues: [],
  };
}
