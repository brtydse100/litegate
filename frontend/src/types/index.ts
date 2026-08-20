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

export interface KeySettingsUpdate {
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

export interface KeyInfo {
  token?: string;
  key_alias?: string;
  spend: number;
  max_budget?: number | null;
  expires?: string | null;
  models: string[];
  tpm_limit?: number | null;
  rpm_limit?: number | null;
  budget_duration?: string | null;
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

export interface KeyCreateResponse {
  key: string;
  user_id: string;
  expires?: string | null;
}

export interface TeamInfo {
  team_id: string;
  team_alias?: string | null;
  organization_id?: string | null;
  spend?: number | null;
  max_budget?: number | null;
  budget_duration?: string | null;
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
  team_alias: string;
  team_id?: string;
  models: string[];
  max_budget?: number;
  budget_duration?: string;
  tpm_limit?: number;
  rpm_limit?: number;
  blocked: boolean;
}

export interface TeamUpdatePayload {
  team_alias: string;
  models: string[];
  max_budget: number | null;
  budget_duration: string | null;
  tpm_limit: number | null;
  rpm_limit: number | null;
  blocked: boolean;
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
