export interface User {
  user_id: string;
  email: string;
  role: "user" | "admin";
  auth_source: string;
  team_ids: string[];
}

export interface LocalUser {
  username: string;
  user_id: string;
  email: string;
  role: "user" | "admin";
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModelSelection {
  models: string[];
  all: boolean;
}

export type PolicySchemaKind = "key_update" | "team_create" | "team_update";

export interface PolicySchemaResponse {
  available: boolean;
  schemas: Partial<Record<PolicySchemaKind, Record<string, unknown>>>;
  detail?: string;
}

export interface ModelBudget {
  budget_limit: number;
  time_period: string;
}

export interface KeySettingsUpdate {
  advanced_settings?: Record<string, unknown>;
  model_max_budget?: Record<string, ModelBudget>;
  key_alias?: string;
  models?: string[];
  max_budget?: number;
  budget_duration?: string;
  tpm_limit?: number;
  rpm_limit?: number;
  duration?: string;
  blocked?: boolean;
}

export interface BulkKeyUpdateResponse {
  updated: number;
  failed: number;
  results: Array<{ key: string; updated: boolean; error?: string }>;
}

export interface BulkKeySpendResetResponse {
  reset: number;
  failed: number;
  results: Array<{ key: string; reset: boolean; error?: string }>;
}

export interface KeyInfo {
  advanced_settings?: Record<string, unknown>;
  model_max_budget?: Record<string, ModelBudget> | null;
  user_budget?: number | null;
  organization_managed?: boolean;
  user_budget_available?: boolean;
  policy_error?: string | null;
  policy_notice?: string | null;
  user_spend?: number | null;
  organization_path?: string[];
  blocked?: boolean;
  secret_available?: boolean;
  token?: string;
  key_alias?: string;
  spend: number;
  max_budget?: number | null;
  expires?: string | null;
  models: string[];
  tpm_limit?: number | null;
  rpm_limit?: number | null;
  budget_duration?: string | null;
  /** LiteLLM's next budget reset, passed through from key info. */
  budget_reset_at?: string | null;
  /** LiteLLM's masked secret preview, e.g. `sk-...7f3a`. */
  key_name?: string | null;
  created_at?: string | null;
  user_id?: string;
  user_email?: string;
  api_key?: string;
  key?: string;
  team_id?: string | null;
}

export interface AdminKeyPage {
  keys: KeyInfo[];
  page: number;
  size: number;
  total: number;
  total_pages: number;
}

export interface AdminKeyIdentifiers {
  keys: string[];
  total: number;
}

export interface AdminKeyFilters {
  search?: string;
  team_id?: string;
  blocked?: boolean;
}

export interface DependencyStatus {
  ok: boolean;
  detail: string;
}

export interface SystemStatus {
  ready: boolean;
  dependencies: {
    litellm: DependencyStatus;
    database: DependencyStatus;
  };
  storage_mode: string;
  security_warnings?: string[];
}

export interface AuditEvent {
  id: number;
  occurred_at: string;
  actor_id: string;
  actor_email: string;
  action: string;
  target: string;
  outcome: "success" | "failure";
  details: Record<string, unknown>;
}

export interface KeyCreateResponse {
  key: string;
  user_id: string;
  expires?: string | null;
}

export interface OperationLimit {
  limit: number;
  remaining: number;
  retry_after: number;
}

export interface TeamInfo {
  advanced_settings?: Record<string, unknown>;
  organization_managed?: boolean;
  /** Organization group of a config-managed team and its per-user limit. */
  organization_node_id?: string | null;
  organization_per_user?: number | null;
  organization_per_user_override?: number | null;
  team_id: string;
  team_alias?: string | null;
  organization_id?: string | null;
  spend?: number | null;
  max_budget?: number | null;
  budget_duration?: string | null;
  budget_limits?: { budget_duration?: string; max_budget?: number | null }[];
  /** Windows where an admin set a custom cap; null is unlimited. */
  window_budgets?: Record<string, number | null>;
  /** Windows whose cap the configuration sets for this team (read-only). */
  window_config?: Record<string, number | null>;
  tpm_limit?: number | null;
  rpm_limit?: number | null;
  models: string[];
  blocked: boolean;
  members_count?: number;
  keys_count?: number;
  members_with_roles: TeamMember[];
  mapped_groups: string[];
  default_key_team: boolean;
}

export interface TeamMember {
  user_id?: string | null;
  user_email?: string | null;
  role: "user" | "admin";
}

export interface TeamPage {
  teams: TeamInfo[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TeamCreatePayload {
  advanced_settings?: Record<string, unknown>;
  team_alias: string;
  team_id?: string;
  models: string[];
  max_budget?: number;
  budget_duration?: string;
  window_budgets?: WindowBudgets;
  tpm_limit?: number;
  rpm_limit?: number;
  blocked: boolean;
}

export interface TeamUpdatePayload {
  advanced_settings?: Record<string, unknown>;
  team_alias: string;
  models: string[];
  max_budget?: number | null;
  budget_duration?: string | null;
  window_budgets?: WindowBudgets;
  tpm_limit: number | null;
  rpm_limit: number | null;
  blocked: boolean;
}

/** Per scheduled budget window name: an amount, null for unlimited, or
 * "config" to follow the configuration (team_budgets, else default_budget). */
export type WindowBudgets = Record<string, number | null | "config">;

/** One window of the installation-wide schedule (TEAM_BUDGET_WINDOWS). */
export interface BudgetWindow {
  name: string;
  days: string[];
  start: string;
  end: string;
  /** LiteLLM's budget_duration label for this window. */
  label: string;
  /** Default cap for teams that do not override it (admin view only). */
  default_budget?: number | null;
}

export interface BudgetWindowSchedule {
  /** As configured, e.g. "Europe/Berlin" or "UTC+2". */
  timezone: string;
  /** IANA zone used for the clock, e.g. "Etc/GMT-2" for "UTC+2". */
  zone: string;
  windows: BudgetWindow[];
}

/** Administrator view: the schedule with default caps and the key reset period. */
export interface AdminBudgetWindows extends BudgetWindowSchedule {
  key_budget_duration: string | null;
}

export interface TeamBudgetWindowUsage {
  team_id: string;
  timezone: string;
  zone: string;
  windows: (BudgetWindow & {
    max_budget: number | null;
    /** "custom" for a cap set in the team dialog, else "config". */
    source: "config" | "custom";
    /** The configuration sets this window's cap for this team. */
    locked: boolean;
    current_spend: number | null;
    active: boolean | null;
    next_start: string | null;
  })[];
}

export interface TeamMemberMovePayload {
  user_id: string;
  destination_team_id: string;
  confirm_policy_change: true;
}

export interface TeamMemberMoveResult {
  moved: boolean;
  user_id: string;
  source_team_id: string;
  destination_team_id: string;
  keys_moved: number;
  destination_membership_existed: boolean;
}

export interface PeoplePage {
  users: {
    user_id: string;
    email: string | null;
    upstream_role: string | null;
  }[];
  page: number;
  size: number;
  total: number;
  total_pages: number;
}
