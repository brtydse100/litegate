const BASE = "/api";

function getToken(): string | null {
  return localStorage.getItem("token");
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (res.status === 401) {
    localStorage.removeItem("token");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = Array.isArray(err.detail)
      ? err.detail.map((item: { msg?: string }) => item.msg ?? "Invalid value").join("; ")
      : err.detail;
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return res.json() as Promise<T>;
}

export const api = {
  me: () => request<import("../types").User>("/auth/me"),

  listKeys: () => request<{ keys: import("../types").KeyInfo[] }>("/keys"),

  listAllKeys: (page = 1, size = 25) =>
    request<import("../types").AdminKeyPage>(`/v1/keys?all=true&page=${page}&size=${size}`),

  createKey: () =>
    request<import("../types").KeyCreateResponse>("/keys", { method: "POST" }),

  regenerateKey: () =>
    request<import("../types").KeyCreateResponse>("/keys/regenerate", { method: "POST" }),

  deleteKey: (key: string) =>
    request<{ deleted: boolean }>(`/keys/${encodeURIComponent(key)}`, {
      method: "DELETE",
    }),

  bulkUpdateKeys: (keys: string[], settings: import("../types").KeySettingsUpdate) =>
    request<import("../types").BulkKeyUpdateResponse>("/v1/keys/bulk", {
      method: "PATCH",
      body: JSON.stringify({ keys, settings }),
    }),

  listUsers: () => request<import("../types").LocalUser[]>("/users"),

  createUser: (payload: { username: string; email: string; password: string; role: "user" | "admin" }) =>
    request<import("../types").LocalUser>("/users", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateUser: (username: string, payload: { email?: string; password?: string; role?: "user" | "admin"; active?: boolean }) =>
    request<import("../types").LocalUser>(`/users/${encodeURIComponent(username)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};
