export interface OrganizationGroup {
  id: string;
  name: string;
  level: number;
  path: string[];
  parent_id: string | null;
  team_id: string;
  members: number;
  per_user: number | null;
  duration: string | null;
  budget_source: string | null;
  group_total: number | null;
  group_spend: number | null;
  sync_error: string | null;
}

export interface OrganizationOverview {
  enabled: boolean;
  levels: string[];
  groups: OrganizationGroup[];
  total_users: number;
  issues: Array<{ user_id: string; error: string }>;
}

export interface OrganizationUserPage {
  users: Array<{
    user_id: string;
    email: string;
    path: string[];
    per_user: number | null;
    duration: string | null;
    budget_spend: number | null;
    sync_error: string | null;
  }>;
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface UsageMetrics {
  spend: number;
  tokens: number;
  requests: number;
}

export interface OrganizationUsage {
  start_date: string;
  end_date: string;
  totals: UsageMetrics;
  daily: Array<UsageMetrics & { date: string }>;
  by_group: Array<UsageMetrics & { id: string | null; name: string }>;
  by_model: Array<UsageMetrics & { name: string }>;
  users: number;
  attribution: "current_membership";
  issues: Array<{ user_id: string; error: string }>;
}
