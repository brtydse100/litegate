import { fireEvent, render, screen, within } from "@testing-library/react";
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
          max_budget: 2000,
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
    const dialog = screen.getByRole("dialog", { name: "Edit team" });
    const current = within(dialog).getByRole("region", {
      name: "Current team settings",
    });
    expect(within(current).getByText("$2000")).toBeVisible();
    expect(within(dialog).getByLabelText("Maximum budget (USD)")).toHaveValue(
      2000,
    );
    fireEvent.change(within(dialog).getByLabelText("Maximum budget (USD)"), {
      target: { value: "3000" },
    });
    expect(within(current).getByText("$2000")).toBeVisible();
    expect(within(dialog).getByLabelText("Budget reset")).toHaveValue("30d");
    const options = within(dialog).getByLabelText("Add available model");
    await within(options).findByRole("option", { name: "model-b" });
    fireEvent.change(options, { target: { value: "model-b" } });
    expect(
      within(dialog).getByLabelText(
        "Allowed models (comma-separated or one per line)",
      ),
    ).toHaveValue("legacy-model, model-b");
  });
});
