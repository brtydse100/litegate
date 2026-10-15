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
    listTeams: vi.fn(),
    listModels: vi.fn(),
    getOperationLimit: vi.fn(),
    createTeam: vi.fn(),
    updateTeam: vi.fn(),
    deleteTeam: vi.fn(),
    moveTeamMember: vi.fn(),
  },
}));

describe("team policy editing", () => {
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
    expect(screen.getByText("$0.0024")).toBeVisible();
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
