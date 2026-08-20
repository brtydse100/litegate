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
