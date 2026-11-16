import { afterEach, expect, it, vi } from "vitest";
import { api } from "./client";
afterEach(() => vi.unstubAllGlobals());
it("keeps structured server locations without leaking validation inputs", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [
          {
            loc: ["body", "advanced_settings", "limits", 0],
            msg: "Must match the required type.",
            type: "schema.type",
            input: "hidden-value",
          },
        ],
      }),
    }),
  );
  const error = await api
    .createTeam({ team_alias: "draft", models: [], blocked: false })
    .catch((failure: unknown) => failure);
  expect(error).toMatchObject({
    message: "advanced_settings.limits.0: Must match the required type.",
    fieldErrors: [
      {
        loc: ["body", "advanced_settings", "limits", 0],
        msg: "Must match the required type.",
        type: "schema.type",
      },
    ],
  });
  expect(JSON.stringify(error)).not.toContain("hidden-value");
});

const peoplePage = {
  users: [
    {
      user_id: "sso-no-key",
      email: "person@example.invalid",
      upstream_role: "internal_user",
    },
  ],
  page: 1,
  size: 25,
  total: 1,
  total_pages: 1,
};

it("accepts a complete people page without changing its rows", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => peoplePage }),
  );
  await expect(api.listPeople()).resolves.toEqual(peoplePage);
});

it.each([
  {},
  null,
  { ...peoplePage, users: null },
  { ...peoplePage, users: [null] },
  { ...peoplePage, users: [{ user_id: "", email: null, upstream_role: null }] },
  {
    ...peoplePage,
    users: [{ user_id: "person", email: {}, upstream_role: null }],
  },
  { ...peoplePage, total: 0 },
  { ...peoplePage, total_pages: 2 },
  { ...peoplePage, page: 2 },
  { ...peoplePage, size: 100 },
])(
  "rejects an invalid successful directory response instead of inventing an empty page: %j",
  async (body) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => body }),
    );
    await expect(api.listPeople()).rejects.toThrow(
      "The people directory returned an invalid page. Try again later.",
    );
  },
);
