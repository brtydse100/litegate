import { expect, test } from "@playwright/test";

test("LiteGate manages a real LiteLLM team and virtual key", async ({
  page,
}) => {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
  const teamId = `browser-${suffix}`;
  let key = "";
  let teamCreated = false;

  const api = async (path: string, init: RequestInit = {}) => {
    const response = await page.evaluate(
      async ({ path, init }) => {
        const result = await fetch(path, init);
        return { status: result.status, body: await result.json() };
      },
      { path, init },
    );
    expect(
      response.status,
      JSON.stringify(response.body),
    ).toBeGreaterThanOrEqual(200);
    expect(response.status, JSON.stringify(response.body)).toBeLessThan(300);
    return response.body;
  };

  await page.goto("/");
  const login = await page.request.post("/api/auth/local", {
    form: {
      username: "integration-admin",
      password: "litegate-integration-password",
    },
  });
  expect(login.ok(), await login.text()).toBeTruthy();

  const managementHeaders = {
    "Content-Type": "application/json",
    "X-API-Key": "litegate-integration-management-key",
  };

  try {
    const createdTeam = await api("/api/v1/teams", {
      method: "POST",
      headers: managementHeaders,
      body: JSON.stringify({
        team_id: teamId,
        team_alias: `Browser ${suffix}`,
      }),
    });
    teamCreated = true;
    expect(createdTeam.team_id).toBe(teamId);

    const teams = await api(
      `/api/v1/teams?search=${encodeURIComponent(teamId)}`,
      {
        headers: { "X-API-Key": "litegate-integration-management-key" },
      },
    );
    expect(
      teams.teams.some((team: { team_id?: string }) => team.team_id === teamId),
    ).toBeTruthy();

    const createdKey = await api("/api/v1/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    key = createdKey.key;

    const keys = await api("/api/v1/keys");
    expect(keys.keys.length).toBe(1);

    const bulk = await api("/api/v1/keys/bulk", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keys: [key],
        settings: { key_alias: `Browser updated ${suffix}` },
      }),
    });
    expect(bulk.updated).toBe(1);

    const updatedTeam = await api(
      `/api/v1/teams/${encodeURIComponent(teamId)}`,
      {
        method: "PATCH",
        headers: managementHeaders,
        body: JSON.stringify({ team_alias: `Browser updated ${suffix}` }),
      },
    );
    expect(updatedTeam.team_alias).toBe(`Browser updated ${suffix}`);
  } finally {
    if (key) {
      await api("/api/v1/keys", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
    }
    if (teamCreated) {
      await api(`/api/v1/teams/${encodeURIComponent(teamId)}`, {
        method: "DELETE",
        headers: { "X-API-Key": "litegate-integration-management-key" },
      });
    }
  }
});
