import type { PeoplePage } from "../types";

const BASE = "/api";

export interface FieldError {
  loc: (string | number)[];
  msg: string;
  type?: string;
}

export class RequestError extends Error {
  constructor(
    public fieldErrors: FieldError[],
    message: string,
  ) {
    super(message);
  }
}

function getToken(): string | null {
  return localStorage.getItem("token");
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  redirectOnUnauthorized = true,
): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (res.status === 401 && redirectOnUnauthorized) {
    localStorage.removeItem("token");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    if (Array.isArray(err.detail)) {
      const fields: FieldError[] = err.detail
        .slice(0, 20)
        .map((item: FieldError) => ({
          loc: Array.isArray(item?.loc)
            ? item.loc
                .filter(
                  (part) =>
                    typeof part === "string" || typeof part === "number",
                )
                .slice(0, 35)
            : [],
          msg: typeof item?.msg === "string" ? item.msg : "Invalid value",
          ...(typeof item?.type === "string" ? { type: item.type } : {}),
        }));
      throw new RequestError(
        fields,
        fields
          .map(
            (field) =>
              `${field.loc.filter((part) => part !== "body").join(".")}${field.loc.length ? ": " : ""}${field.msg}`,
          )
          .join("; "),
      );
    }
    const detail = err.detail;
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return res.json() as Promise<T>;
}

function peoplePage(data: unknown, page: number, size: number): PeoplePage {
  const result = data as PeoplePage | null;
  if (
    !result ||
    result.page !== page ||
    result.size !== size ||
    !Number.isInteger(result.total) ||
    result.total < 0 ||
    result.total > 1_000_000_000 ||
    result.total_pages !== Math.ceil(result.total / size) ||
    !Array.isArray(result.users) ||
    result.users.length !==
      Math.min(size, Math.max(0, result.total - (page - 1) * size)) ||
    result.users.some(
      (person) =>
        !person ||
        typeof person.user_id !== "string" ||
        !person.user_id.trim() ||
        person.user_id.length > 512 ||
        !(
          person.email === null ||
          (typeof person.email === "string" && person.email.length <= 512)
        ) ||
        !(
          person.upstream_role === null ||
          (typeof person.upstream_role === "string" &&
            person.upstream_role.length <= 100)
        ),
    ) ||
    new Set(result.users.map((person) => person.user_id)).size !==
      result.users.length
  ) {
    throw new Error(
      "The people directory returned an invalid page. Try again later.",
    );
  }
  return result;
}

export const api = {
  organizationBudgets: () =>
    request<import("../types/budgets").BudgetView>("/v1/organization/budgets"),
  setGroupBudget: (group: string, revision: number, amount: string) =>
    request<import("../types/budgets").BudgetView>(
      `/v1/organization/budgets/groups/${encodeURIComponent(group)}`,
      { method: "PATCH", body: JSON.stringify({ revision, amount }) },
    ),
  setUserBudget: (
    group: string,
    user: string,
    revision: number,
    amount: string | null,
  ) =>
    request<import("../types/budgets").BudgetView>(
      `/v1/organization/budgets/groups/${encodeURIComponent(group)}/users/${encodeURIComponent(user)}`,
      { method: "PATCH", body: JSON.stringify({ revision, amount }) },
    ),
  setGroupPerUser: (group: string, amount: string | null) =>
    request<import("../types/budgets").PerUserLimit>(
      `/v1/organization/groups/${encodeURIComponent(group)}/per-user`,
      { method: "PATCH", body: JSON.stringify({ amount }) },
    ),
  organizationAccess: () =>
    request<{ organization: boolean; global_admin: boolean; roots: string[] }>(
      "/v1/organization/access",
    ),
  personalAnalytics: () =>
    request<import("../types/analytics").PersonalAnalyticsData>("/analytics"),
  policySchemas: () =>
    request<import("../types").PolicySchemaResponse>("/v1/policy-schemas"),
  organizationChildren: (parent?: string) => {
    const params = new URLSearchParams();
    if (parent) params.set("parent", parent);
    return request<import("../types/organization").OrganizationChildren>(
      `/v1/organization/children${params.size ? `?${params}` : ""}`,
    );
  },
  organizationGroup: (nodeId: string) =>
    request<import("../types/organization").OrganizationGroupDetail>(
      `/v1/organization/groups/${encodeURIComponent(nodeId)}`,
    ),
  organization: () =>
    request<import("../types/organization").OrganizationOverview>(
      "/v1/organization",
    ),
  /** One group, several groups (combined), or "" / [] for every group. */
  organizationUsers: (node: string | string[], page = 1) => {
    const params = new URLSearchParams({ page: String(page), page_size: "25" });
    for (const id of [node].flat()) if (id) params.append("node", id);
    return request<import("../types/organization").OrganizationUserPage>(
      `/v1/organization/users?${params}`,
    );
  },
  organizationUsage: (node: string | string[], start: string, end: string) => {
    const params = new URLSearchParams({ start_date: start, end_date: end });
    for (const id of [node].flat()) if (id) params.append("node", id);
    return request<import("../types/organization").OrganizationUsage>(
      `/v1/organization/usage?${params}`,
    );
  },
  me: () => request<import("../types").User>("/auth/me", {}, false),

  logout: () =>
    request<{ signed_out: boolean }>("/auth/logout", { method: "POST" }, false),

  listKeys: () => request<{ keys: import("../types").KeyInfo[] }>("/keys"),

  getOperationLimit: () =>
    request<import("../types").OperationLimit>("/keys/operation-limit"),

  listAllKeys: (
    page = 1,
    size = 25,
    filters: import("../types").AdminKeyFilters = {},
  ) => {
    const params = new URLSearchParams({
      all: "true",
      page: String(page),
      size: String(size),
    });
    if (filters.search) params.set("search", filters.search);
    if (filters.team_id) params.set("team_id", filters.team_id);
    if (filters.blocked !== undefined)
      params.set("blocked", String(filters.blocked));
    return request<import("../types").AdminKeyPage>(`/v1/keys?${params}`);
  },

  listAllKeyIdentifiers: (filters: import("../types").AdminKeyFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.search) params.set("search", filters.search);
    if (filters.team_id) params.set("team_id", filters.team_id);
    if (filters.blocked !== undefined)
      params.set("blocked", String(filters.blocked));
    const query = params.toString();
    return request<import("../types").AdminKeyIdentifiers>(
      `/v1/keys/identifiers${query ? `?${query}` : ""}`,
    );
  },

  getSystemStatus: () => request<import("../types").SystemStatus>("/v1/status"),

  listAuditEvents: (limit = 100) =>
    request<{ events: import("../types").AuditEvent[] }>(
      `/v1/audit-events?limit=${limit}`,
    ),

  createKey: () =>
    request<import("../types").KeyCreateResponse>("/keys", { method: "POST" }),

  regenerateKey: () =>
    request<import("../types").KeyCreateResponse>("/keys/regenerate", {
      method: "POST",
    }),

  revealKey: (key: string) =>
    request<{ key: string }>("/keys/reveal", {
      method: "POST",
      body: JSON.stringify({ key }),
    }),

  deleteKey: (key: string) =>
    request<{ deleted: boolean }>("/keys", {
      method: "DELETE",
      body: JSON.stringify({ key }),
    }),

  bulkUpdateKeys: (
    keys: string[],
    settings: import("../types").KeySettingsUpdate,
    useKeyBudgetOnly = false,
  ) =>
    request<import("../types").BulkKeyUpdateResponse>("/v1/keys/bulk", {
      method: "PATCH",
      body: JSON.stringify({
        keys,
        ...(Object.keys(settings).length ? { settings } : {}),
        ...(useKeyBudgetOnly ? { use_key_budget_only: true } : {}),
      }),
    }),

  resetKeySpend: (keys: string[]) =>
    request<import("../types").BulkKeySpendResetResponse>(
      "/v1/keys/reset-spend",
      {
        method: "POST",
        body: JSON.stringify({ keys }),
      },
    ),

  listModels: () => request<{ models: string[] }>("/v1/models"),

  listUsers: () => request<import("../types").LocalUser[]>("/v1/users"),

  listPeople: async (page = 1, size = 25, search = "") => {
    const params = new URLSearchParams({
      page: String(page),
      size: String(size),
      search,
    });
    return peoplePage(
      await request<unknown>(`/v1/people?${params}`),
      page,
      size,
    );
  },

  createUser: (payload: {
    username: string;
    email: string;
    password: string;
    role: "user" | "admin";
  }) =>
    request<import("../types").LocalUser>("/v1/users", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateUser: (
    username: string,
    payload: {
      email?: string;
      password?: string;
      role?: "user" | "admin";
      active?: boolean;
    },
  ) =>
    request<import("../types").LocalUser>(
      `/v1/users/${encodeURIComponent(username)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    ),

  listTeams: (page = 1, size = 25, search = "") =>
    request<import("../types").TeamPage>(
      `/v1/teams?page=${page}&size=${size}&search=${encodeURIComponent(search)}`,
    ),

  createTeam: (payload: import("../types").TeamCreatePayload) =>
    request<import("../types").TeamInfo>("/v1/teams", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateTeam: (teamId: string, payload: import("../types").TeamUpdatePayload) =>
    request<import("../types").TeamInfo>(
      `/v1/teams/${encodeURIComponent(teamId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    ),

  teamBudgetWindows: (teamId: string) =>
    request<import("../types").TeamBudgetWindowUsage>(
      `/v1/teams/${encodeURIComponent(teamId)}/budget-windows`,
    ),

  deleteTeam: (teamId: string) =>
    request<{ deleted: boolean; team_id: string }>(
      `/v1/teams/${encodeURIComponent(teamId)}`,
      {
        method: "DELETE",
      },
    ),

  moveTeamMember: (
    sourceTeamId: string,
    payload: import("../types").TeamMemberMovePayload,
  ) =>
    request<import("../types").TeamMemberMoveResult>(
      `/v1/teams/${encodeURIComponent(sourceTeamId)}/members/move`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
};
