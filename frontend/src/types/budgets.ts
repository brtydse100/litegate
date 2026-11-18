export interface BudgetUser {
  user_id: string;
  email: string;
  allocation: number | null;
  override: number | null;
  mode: "automatic" | "manual" | "fixed";
  used: number | null;
  remaining: number | null;
  can_edit: boolean;
}
export interface BudgetGroup {
  id: string;
  name: string;
  path: string[];
  parent_id: string | null;
  duration: string | null;
  assigned: number;
  allocated: number | null;
  reserved: number;
  remainder: number | null;
  allocation_error?: string | null;
  used: number | null;
  remaining: number | null;
  can_edit_envelope: boolean;
  /** Effective per-user limit: the override when set, else the configured value. */
  per_user: number | null;
  per_user_config: number | null;
  per_user_override: number | null;
  can_edit_per_user: boolean;
  users: BudgetUser[];
}
export interface PerUserLimit {
  node_id: string;
  per_user: number | null;
  per_user_config: number | null;
  per_user_override: number | null;
}
export interface BudgetView {
  revision: number;
  mode: string;
  applied: boolean;
  pending: boolean;
  capability: { supported: boolean; version: string | null; reasons: string[] };
  groups: BudgetGroup[];
}
