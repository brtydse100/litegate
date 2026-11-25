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
  it("edits one amount per shared window and sends blanks as unlimited", async () => {
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
    vi.mocked(api.teamBudgetWindows).mockResolvedValue({
      team_id: "research",
      timezone: "UTC",
      windows: [
        {
          name: "Mon 08:00-13:00",
          days: ["mon"],
          start: "08:00",
          end: "13:00",
          label: "sched:UTC:mon:08:00-13:00",
          max_budget: 5,
          current_spend: 1.5,
          active: true,
          next_start: null,
        },
        {
          name: "Mon 18:00-22:00",
          days: ["mon"],
          start: "18:00",
          end: "22:00",
          label: "sched:UTC:mon:18:00-22:00",
          max_budget: null,
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
          budget_limits: [
            { budget_duration: "sched:UTC:mon:08:00-13:00", max_budget: 5 },
          ],
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
          budgetWindows={{
            timezone: "UTC",
            windows: [
              {
                name: "Mon 08:00-13:00",
                days: ["mon"],
                start: "08:00",
                end: "13:00",
                label: "sched:UTC:mon:08:00-13:00",
              },
              {
                name: "Mon 18:00-22:00",
                days: ["mon"],
                start: "18:00",
                end: "22:00",
                label: "sched:UTC:mon:18:00-22:00",
              },
            ],
          }}
        />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Budget windows · Mon (UTC)")).toBeVisible();
    expect(screen.getByText(/including weekends/)).toBeVisible();
    expect(await screen.findByText(/\$1\.50 of \$5\.00/)).toBeVisible();
    expect(screen.queryByText(/Morning/)).not.toBeInTheDocument();
    expect(await screen.findByText(/\$1\.50 of \$5\.00/)).toBeVisible();
    expect(screen.queryByText(/resets every/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = screen.getByRole("dialog", { name: "Edit team" });
    expect(within(dialog).queryByText("Budget reset")).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText("08:00–13:00")).toHaveValue(5);
    fireEvent.change(within(dialog).getByLabelText("18:00–22:00"), {
      target: { value: "3" },
    });
    fireEvent.change(within(dialog).getByLabelText("08:00–13:00"), {
      target: { value: "" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() => expect(api.updateTeam).toHaveBeenCalled());
    const sent = vi.mocked(api.updateTeam).mock.calls[0][1];
    expect(sent.window_budgets).toEqual({
      "Mon 08:00-13:00": null,
      "Mon 18:00-22:00": 3,
    });
    expect(sent).not.toHaveProperty("budget_duration");
  });
});
