import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import AdminTeams from "./AdminTeams";

vi.mock("../api/client", () => ({
  api: {
    policySchemas: vi.fn(),
    listTeams: vi.fn(),
    listModels: vi.fn(),
    getOperationLimit: vi.fn(),
    createTeam: vi.fn(),
    updateTeam: vi.fn(),
    deleteTeam: vi.fn(),
    moveTeamMember: vi.fn(),
    setGroupPerUser: vi.fn(),
    budgetWindows: vi.fn(),
    teamBudgetWindows: vi.fn(),
  },
}));

describe("team policy editing", () => {
  it("discovers team model budgets, member defaults and MCP permissions without resending unedited fields", async () => {
    vi.mocked(api.policySchemas).mockResolvedValue({
      available: true,
      schemas: {
        team_update: {
          properties: {
            model_max_budget: { type: "object" },
            team_member_budget: { type: "number" },
            object_permission: { type: "object" },
            new_flag: { type: "boolean" },
            max_budget: { type: "number" },
          },
        },
      },
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <AdminTeams />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByText("Advanced settings"));
    expect(await screen.findByLabelText("Edit model_max_budget")).toBeVisible();
    expect(screen.getByLabelText("Edit team_member_budget")).not.toBeChecked();
    expect(screen.queryByLabelText("Edit max_budget")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Edit object_permission"));
    fireEvent.change(screen.getByLabelText("object_permission"), {
      target: { value: '{"mcp_servers":["local"]}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(api.updateTeam).toHaveBeenCalledWith(
        "devops",
        expect.objectContaining({
          advanced_settings: { object_permission: { mcp_servers: ["local"] } },
        }),
      ),
    );
    const payload = vi.mocked(api.updateTeam).mock.calls[0][1];
    expect(payload.advanced_settings).not.toHaveProperty("model_max_budget");
    expect(payload.advanced_settings).not.toHaveProperty("team_member_budget");
  });

  it("drops advanced drafts after closing and reopening a team editor", async () => {
    vi.mocked(api.policySchemas).mockResolvedValue({
      available: true,
      schemas: {
        team_update: { properties: { new_flag: { type: "boolean" } } },
      },
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <AdminTeams />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByText("Advanced settings"));
    fireEvent.click(await screen.findByLabelText("Edit new_flag"));
    fireEvent.change(screen.getByLabelText("new_flag"), {
      target: { value: "true" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Close team editor" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByText("Advanced settings"));
    expect(await screen.findByLabelText("Edit new_flag")).not.toBeChecked();
    expect(api.policySchemas).toHaveBeenCalledTimes(1);
  });
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.updateTeam).mockResolvedValue({
      team_id: "devops",
      models: ["model-b"],
      blocked: false,
      members_with_roles: [],
      mapped_groups: [],
      default_key_team: false,
    });
    vi.mocked(api.getOperationLimit).mockResolvedValue({
      limit: 5,
      remaining: 5,
      retry_after: 0,
    });
    vi.mocked(api.listModels).mockResolvedValue({
      models: ["model-a", "model-b"],
    });
    vi.mocked(api.listTeams).mockResolvedValue({
      teams: [
        {
          team_id: "devops",
          team_alias: "DevOps",
          organization_managed: true,
          max_budget: 2000,
          spend: 0.0024,
          budget_duration: "30d",
          models: ["legacy-model"],
          blocked: false,
          rpm_limit: 100,
          members_with_roles: [],
          mapped_groups: [],
          default_key_team: false,
        },
      ],
      page: 1,
      page_size: 25,
      total: 1,
      total_pages: 1,
    });
  });

  it("keeps saved settings visible while editing and retains custom model names", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <AdminTeams />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    expect(screen.getByText("$0.00")).toBeVisible();
    expect(screen.getByText("Config managed")).toBeVisible();
    const dialog = screen.getByRole("dialog", { name: "Edit team" });
    const current = within(dialog).getByRole("region", {
      name: "Current team settings",
    });
    expect(within(current).getByText("$2000")).toBeVisible();
    expect(within(dialog).getByLabelText("Team name")).toHaveAttribute(
      "placeholder",
      "DevOps",
    );
    expect(
      within(dialog).getByLabelText("Maximum budget (USD)"),
    ).toHaveAttribute("placeholder", "2000");
    expect(within(dialog).getByLabelText("Budget reset")).toHaveAttribute(
      "placeholder",
      "30d",
    );
    expect(within(dialog).getByLabelText("RPM limit")).toHaveAttribute(
      "placeholder",
      "100",
    );
    expect(within(dialog).getByLabelText("Maximum budget (USD)")).toHaveValue(
      2000,
    );
    fireEvent.change(within(dialog).getByLabelText("Maximum budget (USD)"), {
      target: { value: "3000" },
    });
    expect(
      within(dialog).getByLabelText("Maximum budget (USD)"),
    ).toHaveAttribute("placeholder", "2000");
    expect(within(current).getByText("$2000")).toBeVisible();
    expect(within(dialog).getByLabelText("Budget reset")).toHaveValue("30d");
    expect(
      within(dialog).queryByRole("textbox", { name: /Allowed models/ }),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).getByRole("checkbox", { name: "legacy-model" }),
    ).toBeChecked();
    fireEvent.click(
      await within(dialog).findByRole("checkbox", { name: "model-b" }),
    );
    expect(
      within(dialog).getByRole("checkbox", { name: "model-b" }),
    ).toBeChecked();
    fireEvent.click(
      within(dialog).getByRole("checkbox", { name: "legacy-model" }),
    );
    expect(
      within(dialog).getByRole("checkbox", { name: "legacy-model" }),
    ).not.toBeChecked();
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() =>
      expect(api.updateTeam).toHaveBeenCalledWith(
        "devops",
        expect.objectContaining({ models: ["model-b"] }),
      ),
    );
  });

  it("requires an explicit all-models choice after deselecting the last model", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <AdminTeams />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog", { name: "Edit team" });
    fireEvent.click(
      within(dialog).getByRole("checkbox", { name: "legacy-model" }),
    );
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Save changes" }),
    );
    expect(api.updateTeam).not.toHaveBeenCalled();
    fireEvent.click(
      within(dialog).getByRole("checkbox", { name: "All allowed models" }),
    );
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() =>
      expect(api.updateTeam).toHaveBeenCalledWith(
        "devops",
        expect.objectContaining({ models: [] }),
      ),
    );
  });
});

describe("organization per-user limits", () => {
  it("edits a config-managed team's per-user limit instead of its shared budget", async () => {
    vi.mocked(api.policySchemas).mockResolvedValue({
      available: false,
      schemas: {},
    });
    vi.mocked(api.getOperationLimit).mockResolvedValue({
      limit: 5,
      remaining: 5,
      retry_after: 0,
    });
    vi.mocked(api.listModels).mockResolvedValue({ models: [] });
    vi.mocked(api.setGroupPerUser).mockResolvedValue({
      node_id: "node-eng",
      per_user: 150,
      per_user_config: 200,
      per_user_override: 150,
    });
    vi.mocked(api.listTeams).mockResolvedValue({
      teams: [
        {
          team_id: "eng",
          team_alias: "Engineering",
          organization_managed: true,
          organization_node_id: "node-eng",
          organization_per_user: 200,
          organization_per_user_override: null,
          max_budget: null,
          budget_duration: "30d",
          models: [],
          blocked: false,
          members_with_roles: [],
          mapped_groups: [],
          default_key_team: false,
        },
      ],
      page: 1,
      page_size: 25,
      total: 1,
      total_pages: 1,
    });
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <AdminTeams />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog", { name: "Edit team" });
    expect(
      within(dialog).queryByLabelText("Maximum budget (USD)"),
    ).not.toBeInTheDocument();
    const limit = within(dialog).getByLabelText("Per-user limit (USD)");
    expect(limit).toHaveValue(200);
    expect(limit).toBeEnabled();
    fireEvent.change(limit, { target: { value: "150" } });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() =>
      expect(api.setGroupPerUser).toHaveBeenCalledWith("node-eng", "150"),
    );
    await waitFor(() => expect(api.updateTeam).toHaveBeenCalled());
    expect(vi.mocked(api.updateTeam).mock.calls[0][1]).not.toHaveProperty(
      "max_budget",
    );
  });
});

describe("scheduled budget windows", () => {
  const windows = [
    {
      id: "morning",
      days: ["mon"],
      start: "08:00",
      end: "13:00",
      label: "sched:Etc/GMT-2:mon:08:00-13:00",
    },
    {
      id: "afternoon",
      days: ["mon"],
      start: "13:00",
      end: "18:00",
      label: "sched:Etc/GMT-2:mon:13:00-18:00",
    },
    {
      id: "evening",
      days: ["mon"],
      start: "18:00",
      end: "22:00",
      label: "sched:Etc/GMT-2:mon:18:00-22:00",
    },
  ];

  function renderTeams(morningOpen: boolean) {
    vi.clearAllMocks();
    vi.mocked(api.policySchemas).mockResolvedValue({
      available: false,
      schemas: {},
    });
    vi.mocked(api.getOperationLimit).mockResolvedValue({
      limit: 5,
      remaining: 5,
      retry_after: 0,
    });
    vi.mocked(api.listModels).mockResolvedValue({ models: [] });
    vi.mocked(api.budgetWindows).mockResolvedValue({
      timezone: "UTC+2",
      zone: "Etc/GMT-2",
      windows: [
        { ...windows[0], budget: 40 },
        { ...windows[1], budget: 40 },
        { ...windows[2], budget: null },
      ],
    });
    vi.mocked(api.teamBudgetWindows).mockResolvedValue({
      team_id: "research",
      timezone: "UTC+2",
      zone: "Etc/GMT-2",
      windows: [
        {
          ...windows[0],
          max_budget: 5,
          source: "custom",
          locked: false,
          current_spend: morningOpen ? 1.5 : 0,
          active: morningOpen,
          next_start: null,
        },
        {
          ...windows[1],
          max_budget: 12,
          source: "config",
          locked: true,
          current_spend: null,
          active: false,
          next_start: null,
        },
        {
          ...windows[2],
          max_budget: null,
          source: "config",
          locked: false,
          current_spend: null,
          active: false,
          next_start: null,
        },
      ],
    });
    vi.mocked(api.updateTeam).mockResolvedValue({
      team_id: "research",
      models: [],
      blocked: false,
      members_with_roles: [],
      mapped_groups: [],
      default_key_team: false,
    });
    vi.mocked(api.listTeams).mockResolvedValue({
      teams: [
        {
          team_id: "research",
          team_alias: "Research",
          budget_duration: "30d",
          window_budgets: { morning: 5 },
          window_config: { afternoon: 12 },
          models: [],
          blocked: false,
          members_with_roles: [],
          mapped_groups: [],
          default_key_team: false,
        },
      ],
      page: 1,
      page_size: 25,
      total: 1,
      total_pages: 1,
    });
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <AdminTeams
          budgetWindows={{ timezone: "UTC+2", zone: "Etc/GMT-2", windows }}
        />
      </QueryClientProvider>,
    );
  }

  it("shows only the open window on the row and edits config or custom caps", async () => {
    renderTeams(true);
    expect(
      await screen.findByRole("heading", { name: "Budget windows" }),
    ).toBeVisible();
    expect(screen.getByText("Mon · UTC+2")).toBeVisible();
    expect(await screen.findByText("$1.50 spent")).toBeVisible();
    expect(screen.getByText("· $5.00 · custom")).toBeVisible();
    // Only the open window is on the row; no reset warnings remain.
    expect(screen.queryByText(/\$12\.00/)).not.toBeInTheDocument();
    expect(screen.queryByText(/resets/)).not.toBeInTheDocument();
    expect(screen.queryByText(/KEY_BUDGET_DURATION/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog", { name: "Edit team" });
    expect(within(dialog).queryByText("Budget reset")).not.toBeInTheDocument();
    expect(await within(dialog).findAllByText("config $40.00")).toHaveLength(1);
    // The configuration overrides 13:00–18:00 for this team, so it is read-only.
    expect(
      within(dialog).getByText("Set in config for this team"),
    ).toBeVisible();
    expect(within(dialog).getByText("13:00–18:00")).toHaveAttribute(
      "title",
      "afternoon",
    );
    expect(
      within(dialog).queryByRole("group", { name: "Cap for 13:00–18:00" }),
    ).not.toBeInTheDocument();
    const morning = within(dialog).getByRole("group", {
      name: "Cap for 08:00–13:00",
    });
    const evening = within(dialog).getByRole("group", {
      name: "Cap for 18:00–22:00",
    });
    expect(
      within(morning).getByRole("button", { name: "Custom" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(dialog).getByLabelText("Custom cap for 08:00–13:00 (USD)"),
    ).toHaveValue(5);
    fireEvent.click(within(morning).getByRole("button", { name: "Config" }));
    fireEvent.click(within(evening).getByRole("button", { name: "Custom" }));
    fireEvent.change(
      within(dialog).getByLabelText("Custom cap for 18:00–22:00 (USD)"),
      { target: { value: "3" } },
    );
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() => expect(api.updateTeam).toHaveBeenCalled());
    const sent = vi.mocked(api.updateTeam).mock.calls[0][1];
    expect(sent.window_budgets).toEqual({ morning: "config", evening: 3 });
    expect(sent).not.toHaveProperty("budget_duration");
  });

  it("says when no window is open and which cap comes next", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    // Wednesday 12:00 at UTC+2: no window until Monday 08:00.
    vi.setSystemTime(new Date("2026-11-25T10:00:00Z"));
    try {
      renderTeams(false);
      expect(await screen.findByText(/\(\$5\.00 · custom\)/)).toBeVisible();
      expect(
        screen.getAllByText(/No window open · next Mon 08:00/),
      ).toHaveLength(2);
      expect(screen.queryByText(/spent/)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
