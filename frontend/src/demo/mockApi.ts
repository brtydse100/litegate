import type { AuditEvent, KeyInfo, LocalUser, TeamInfo, User } from "../types";

const demoUser: User = {
  user_id: "demo-admin",
  email: "alex@example.com",
  role: "admin",
  auth_source: "oidc",
  team_ids: ["platform-engineering"],
};

let signedIn = true;
let personalKeys: KeyInfo[] = [
  {
    token: "sk-litegate-demo-key-7f3a",
    key_alias: "alex-primary",
    spend: 18.42,
    max_budget: 100,
    expires: "2026-12-31T23:59:59Z",
    models: ["gpt-5", "claude-sonnet-4", "gemini-2.5-pro"],
    rpm_limit: 120,
    tpm_limit: 120000,
    team_id: "platform-engineering",
    user_id: "demo-admin",
    user_email: "alex@example.com",
  },
];

let installationKeys: KeyInfo[] = [
  ...personalKeys,
  {
    token: "key-product-01",
    key_alias: "product-research",
    spend: 63.78,
    max_budget: 250,
    models: ["gpt-5", "claude-sonnet-4"],
    rpm_limit: 240,
    team_id: "product",
    user_id: "maya",
    user_email: "maya@example.com",
  },
  {
    token: "key-support-01",
    key_alias: "support-assistant",
    spend: 31.09,
    max_budget: 80,
    models: ["gpt-5-mini"],
    rpm_limit: 90,
    team_id: "customer-support",
    user_id: "sam",
    user_email: "sam@example.com",
  },
  {
    token: "key-data-01",
    key_alias: "analytics-pipeline",
    spend: 146.21,
    max_budget: 500,
    models: ["gemini-2.5-pro"],
    rpm_limit: 300,
    team_id: "data-platform",
    user_id: "priya",
    user_email: "priya@example.com",
  },
];

let users: LocalUser[] = [
  {
    username: "contractor",
    user_id: "local-contractor",
    email: "contractor@example.com",
    role: "user",
    active: true,
    created_at: "2026-07-14T08:20:00Z",
    updated_at: "2026-08-18T10:05:00Z",
  },
  {
    username: "backup-admin",
    user_id: "local-backup-admin",
    email: "ops@example.com",
    role: "admin",
    active: true,
    created_at: "2026-05-02T13:30:00Z",
    updated_at: "2026-08-20T16:10:00Z",
  },
  {
    username: "former-vendor",
    user_id: "local-former-vendor",
    email: "vendor@example.com",
    role: "user",
    active: false,
    created_at: "2026-03-11T09:00:00Z",
    updated_at: "2026-06-30T17:45:00Z",
  },
];

let teams: TeamInfo[] = [
  {
    team_id: "platform-engineering",
    team_alias: "Platform Engineering",
    spend: 182.6,
    max_budget: 600,
    budget_duration: "monthly",
    tpm_limit: 300000,
    rpm_limit: 500,
    models: ["gpt-5", "claude-sonnet-4", "gemini-2.5-pro"],
    blocked: false,
    members_count: 4,
    keys_count: 6,
    members_with_roles: [
      { user_id: "demo-admin", user_email: "alex@example.com", role: "admin" },
      { user_id: "priya", user_email: "priya@example.com", role: "user" },
    ],
    mapped_groups: ["engineering-platform"],
    default_key_team: true,
  },
  {
    team_id: "product",
    team_alias: "Product",
    spend: 96.4,
    max_budget: 300,
    budget_duration: "monthly",
    tpm_limit: 180000,
    rpm_limit: 300,
    models: ["gpt-5", "claude-sonnet-4"],
    blocked: false,
    members_count: 7,
    keys_count: 5,
    members_with_roles: [
      { user_id: "maya", user_email: "maya@example.com", role: "admin" },
    ],
    mapped_groups: ["product-team"],
    default_key_team: false,
  },
  {
    team_id: "customer-support",
    team_alias: "Customer Support",
    spend: 44.15,
    max_budget: 120,
    budget_duration: "monthly",
    tpm_limit: 90000,
    rpm_limit: 150,
    models: ["gpt-5-mini"],
    blocked: false,
    members_count: 12,
    keys_count: 8,
    members_with_roles: [
      { user_id: "sam", user_email: "sam@example.com", role: "admin" },
    ],
    mapped_groups: ["support"],
    default_key_team: false,
  },
];

const auditEvents: AuditEvent[] = [
  {
    id: 3,
    occurred_at: "2026-08-23T14:32:00Z",
    actor_id: "demo-admin",
    actor_email: "alex@example.com",
    action: "key.regenerate",
    target: "personal key",
    outcome: "success",
    details: { spend_carried_forward: true },
  },
  {
    id: 2,
    occurred_at: "2026-08-22T11:08:00Z",
    actor_id: "local-backup-admin",
    actor_email: "ops@example.com",
    action: "keys.bulk_update",
    target: "matching keys",
    outcome: "success",
    details: { updated: 3, failed: 0 },
  },
  {
    id: 1,
    occurred_at: "2026-08-20T09:15:00Z",
    actor_id: "demo-admin",
    actor_email: "alex@example.com",
    action: "user.update",
    target: "former-vendor",
    outcome: "success",
    details: { active: false },
  },
];

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function body(request: Request): Promise<Record<string, unknown>> {
  try {
    return (await request.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function matchesKey(key: KeyInfo, search: string, teamId: string) {
  const haystack = [key.key_alias, key.user_email, key.user_id, key.team_id]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return (
    (!search || haystack.includes(search.toLowerCase())) &&
    (!teamId || key.team_id === teamId)
  );
}

async function mockResponse(request: Request): Promise<Response> {
  await new Promise((resolve) => window.setTimeout(resolve, 120));
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method.toUpperCase();

  if (path === "/api/auth/config")
    return json({ sso_enabled: true, local_enabled: true });
  if (path === "/api/auth/local" && method === "POST") {
    signedIn = true;
    return json({ authenticated: true });
  }
  if (path === "/api/auth/me")
    return signedIn ? json(demoUser) : json({ detail: "Not signed in" }, 401);
  if (path === "/api/auth/logout" && method === "POST") {
    signedIn = false;
    return json({ signed_out: true });
  }
  if (path === "/api/portal-config")
    return json({
      support_ticket_url: "https://github.com/brtydse100/litegate/issues",
      logo_url: "",
      litellm_ui_url: "",
      api_docs_url: "https://github.com/brtydse100/litegate/blob/main/API.md",
    });
  if (path === "/api/keys/operation-limit")
    return json({ limit: 10, remaining: 10, retry_after: 0 });
  if (path === "/api/keys" && method === "GET")
    return json({ keys: personalKeys });
  if (path === "/api/keys" && method === "POST") {
    const key = "sk-litegate-demo-created-9b2c";
    const created: KeyInfo = {
      token: key,
      key_alias: "alex-primary",
      spend: 0,
      max_budget: 100,
      models: ["gpt-5", "claude-sonnet-4", "gemini-2.5-pro"],
      rpm_limit: 120,
      team_id: "platform-engineering",
      user_email: demoUser.email,
    };
    personalKeys = [created];
    installationKeys = [
      created,
      ...installationKeys.filter((item) => item.user_id !== demoUser.user_id),
    ];
    return json({ key, user_id: demoUser.user_id, expires: null });
  }
  if (path === "/api/keys/regenerate" && method === "POST") {
    const key = "sk-litegate-demo-rotated-4d8e";
    personalKeys = personalKeys.map((item) => ({ ...item, token: key }));
    return json({
      key,
      user_id: demoUser.user_id,
      expires: personalKeys[0]?.expires ?? null,
    });
  }
  if (path === "/api/v1/keys" && method === "GET") {
    const page = Number(url.searchParams.get("page") ?? 1);
    const size = Number(url.searchParams.get("size") ?? 25);
    const filtered = installationKeys.filter((key) =>
      matchesKey(
        key,
        url.searchParams.get("search") ?? "",
        url.searchParams.get("team_id") ?? "",
      ),
    );
    return json({
      keys: filtered.slice((page - 1) * size, page * size),
      page,
      size,
      total: filtered.length,
      total_pages: Math.max(1, Math.ceil(filtered.length / size)),
    });
  }
  if (path === "/api/v1/keys/identifiers") {
    const filtered = installationKeys.filter((key) =>
      matchesKey(
        key,
        url.searchParams.get("search") ?? "",
        url.searchParams.get("team_id") ?? "",
      ),
    );
    return json({
      keys: filtered.map((key) => key.token ?? key.key ?? "").filter(Boolean),
      total: filtered.length,
    });
  }
  if (path === "/api/v1/keys/bulk" && method === "PATCH") {
    const payload = await body(request);
    const targetKeys = (payload.keys as string[]) ?? [];
    const settings = (payload.settings as Record<string, unknown>) ?? {};
    installationKeys = installationKeys.map((key) =>
      targetKeys.includes(key.token ?? key.key ?? "")
        ? { ...key, ...settings }
        : key,
    );
    return json({
      updated: targetKeys.length,
      failed: 0,
      results: targetKeys.map((key) => ({ key, updated: true })),
    });
  }
  if (path === "/api/v1/users" && method === "GET") return json(users);
  if (path === "/api/v1/users" && method === "POST") {
    const payload = await body(request);
    const now = new Date().toISOString();
    const created: LocalUser = {
      username: String(payload.username),
      user_id: `local-${String(payload.username)}`,
      email: String(payload.email),
      role: payload.role === "admin" ? "admin" : "user",
      active: true,
      created_at: now,
      updated_at: now,
    };
    users = [...users, created];
    return json(created, 201);
  }
  if (path.startsWith("/api/v1/users/") && method === "PATCH") {
    const username = decodeURIComponent(path.split("/").pop() ?? "");
    const payload = await body(request);
    let updated = users.find((user) => user.username === username);
    users = users.map((user) => {
      if (user.username !== username) return user;
      updated = {
        ...user,
        ...payload,
        updated_at: new Date().toISOString(),
      } as LocalUser;
      return updated;
    });
    return updated ? json(updated) : json({ detail: "User not found" }, 404);
  }
  if (path === "/api/v1/teams" && method === "GET") {
    const page = Number(url.searchParams.get("page") ?? 1);
    const pageSize = Number(url.searchParams.get("size") ?? 25);
    const search = (url.searchParams.get("search") ?? "").toLowerCase();
    const filtered = teams.filter((team) =>
      `${team.team_id} ${team.team_alias ?? ""}`.toLowerCase().includes(search),
    );
    return json({
      teams: filtered.slice((page - 1) * pageSize, page * pageSize),
      total: filtered.length,
      page,
      page_size: pageSize,
      total_pages: Math.max(1, Math.ceil(filtered.length / pageSize)),
    });
  }
  if (path === "/api/v1/teams" && method === "POST") {
    const payload = await body(request);
    const created: TeamInfo = {
      team_id: String(payload.team_id || payload.team_alias)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-"),
      team_alias: String(payload.team_alias),
      models: Array.isArray(payload.models)
        ? payload.models.map((model) => String(model))
        : [],
      blocked: Boolean(payload.blocked),
      members_with_roles: [],
      mapped_groups: [],
      default_key_team: false,
      members_count: 0,
      keys_count: 0,
    };
    teams = [...teams, created];
    return json(created, 201);
  }
  if (
    path.startsWith("/api/v1/teams/") &&
    path.endsWith("/members/move") &&
    method === "POST"
  ) {
    const sourceTeamId = decodeURIComponent(path.split("/")[4]);
    const payload = await body(request);
    return json({
      moved: true,
      user_id: payload.user_id,
      source_team_id: sourceTeamId,
      destination_team_id: payload.destination_team_id,
      keys_moved: 1,
      destination_membership_existed: false,
    });
  }
  if (path.startsWith("/api/v1/teams/")) {
    const teamId = decodeURIComponent(path.split("/").pop() ?? "");
    if (method === "PATCH") {
      const payload = await body(request);
      let updated = teams.find((team) => team.team_id === teamId);
      teams = teams.map((team) => {
        if (team.team_id !== teamId) return team;
        updated = { ...team, ...payload } as TeamInfo;
        return updated;
      });
      return updated ? json(updated) : json({ detail: "Team not found" }, 404);
    }
    if (method === "DELETE") {
      teams = teams.filter((team) => team.team_id !== teamId);
      return json({ deleted: true, team_id: teamId });
    }
  }
  if (path === "/api/v1/status")
    return json({
      ready: true,
      dependencies: {
        litellm: { ok: true, detail: "Connected to LiteLLM demo service" },
        database: { ok: true, detail: "Local account database is available" },
      },
      storage_mode: "SQLite (demo)",
      security_warnings: [],
    });
  if (path === "/api/v1/audit-events") return json({ events: auditEvents });

  return json({ detail: `No demo response for ${method} ${path}` }, 404);
}

export function installDemoApi() {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(
      typeof input === "string"
        ? new URL(input, window.location.origin)
        : input,
      init,
    );
    const url = new URL(request.url);
    return url.origin === window.location.origin &&
      url.pathname.startsWith("/api/")
      ? mockResponse(request)
      : nativeFetch(input, init);
  };
}
