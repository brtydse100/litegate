import {
  fireEvent,
  act,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import {
  organizationOverview,
  organizationUsage,
  organizationUsers,
} from "../demo/organization";
import AdminOrganization from "./AdminOrganization";
import { metricValue } from "./OrganizationCharts";

it("distinguishes sub-cent spend from zero while retaining normal currency precision", () => {
  expect(metricValue(0.0024, "spend")).toBe("$0.0024");
  expect(metricValue(0.000001, "spend")).toBe("<$0.0001");
  expect(metricValue(0, "spend")).toBe("$0.00");
  expect(metricValue(0.01, "spend")).toBe("$0.01");
  expect(metricValue(1.1, "spend")).toBe("$1.10");
});

vi.mock("../api/client", () => ({
  api: {
    organization: vi.fn(),
    organizationUsers: vi.fn(),
    organizationUsage: vi.fn(),
  },
}));

function renderOrganization() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <AdminOrganization />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

describe("organization dashboard contracts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.organization).mockResolvedValue(organizationOverview());
    vi.mocked(api.organizationUsers).mockImplementation(async (node, page) =>
      organizationUsers(node, page ?? 1),
    );
    vi.mocked(api.organizationUsage).mockImplementation(
      async (node, start, end) => organizationUsage(node, start, end),
    );
  });

  it("filters users, charts, and effective budgets together when selecting a squad", async () => {
    renderOrganization();
    const navigation = await screen.findByRole("navigation", {
      name: "Organization groups",
    });
    expect(
      within(navigation).queryByRole("button", { name: "Platform, 1 user" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      within(navigation).getByRole("button", { name: "Expand Engineering" }),
    );
    fireEvent.click(
      within(navigation).getByRole("button", {
        name: "Expand Engineering → Infrastructure",
      }),
    );
    fireEvent.click(
      within(navigation).getByRole("button", { name: "Platform, 1 user" }),
    );
    expect(
      within(navigation).getByRole("button", { name: "Platform, 1 user" }),
    ).toHaveTextContent(/^Platform$/);
    expect(
      within(navigation).getByRole("button", { name: "Engineering, 3 users" }),
    ).toHaveTextContent("3");
    const policy = await screen.findByRole("region", {
      name: "Effective budget policy",
    });
    expect(within(policy).getByText("$100.00")).toBeVisible();
    expect(within(policy).getByText("Platform tracking target")).toBeVisible();
    await waitFor(() =>
      expect(api.organizationUsage).toHaveBeenLastCalledWith(
        "platform",
        expect.any(String),
        expect.any(String),
      ),
    );
    await waitFor(() =>
      expect(api.organizationUsers).toHaveBeenLastCalledWith("platform", 1),
    );
    expect(
      await within(
        screen.getByRole("heading", { name: /^Users/ }).closest("section")!,
      ).findByText("alex@example.com"),
    ).toBeVisible();
    await waitFor(() =>
      expect(screen.queryByText("sam@example.com")).not.toBeInTheDocument(),
    );
    expect(
      await screen.findByRole("img", { name: "Spend (USD) over time" }),
    ).toBeVisible();
    fireEvent.click(
      within(navigation).getByRole("button", { name: "Collapse Engineering" }),
    );
    expect(
      within(navigation).queryByRole("button", { name: "Platform, 1 user" }),
    ).not.toBeInTheDocument();
    expect(within(policy).getByText("$100.00")).toBeVisible();
    expect(api.organizationUsers).toHaveBeenLastCalledWith("platform", 1);
  });

  it("shows inherited allowance and switches the plotted metric", async () => {
    renderOrganization();
    const navigation = await screen.findByRole("navigation", {
      name: "Organization groups",
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Engineering" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Infrastructure" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Cloud" }),
    );
    expect(await screen.findByText("Inherited from Engineering")).toBeVisible();
    expect(
      within(navigation).getByRole("button", { name: "Cloud, 1 user" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(navigation).getByRole("button", { name: "Collapse Engineering" }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      within(navigation).getByRole("button", {
        name: "Collapse Engineering → Infrastructure",
      }),
    ).toHaveAttribute("aria-expanded", "true");
    fireEvent.change(screen.getByRole("combobox", { name: "Chart metric" }), {
      target: { value: "tokens" },
    });
    expect(
      await screen.findByRole("img", { name: "Tokens over time" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("img", { name: "Spend (USD) over time" }),
    ).not.toBeInTheDocument();
  });

  it("changes the queried date range and surfaces upstream failures", async () => {
    renderOrganization();
    const start = await screen.findByLabelText("Usage start date");
    vi.mocked(api.organizationUsage).mockRejectedValue(
      new Error("Aggregate unavailable"),
    );
    fireEvent.change(start, { target: { value: "2026-01-01" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Aggregate unavailable",
    );
    expect(
      screen.queryByRole("img", { name: "Spend (USD) over time" }),
    ).not.toBeInTheDocument();
  });

  it("drills into a group named Direct members using its ID", async () => {
    const overview = organizationOverview();
    vi.mocked(api.organization).mockResolvedValue({
      ...overview,
      groups: overview.groups.map((group) =>
        group.id === "platform"
          ? {
              ...group,
              name: "Direct members",
              path: ["Engineering", "Infrastructure", "Direct members"],
            }
          : group,
      ),
    });
    vi.mocked(api.organizationUsage).mockImplementation(
      async (node, start, end) => {
        const usage = organizationUsage(node, start, end);
        return node === "infrastructure"
          ? {
              ...usage,
              by_group: [
                {
                  id: null,
                  name: "Direct members",
                  spend: 10,
                  tokens: 100,
                  requests: 2,
                },
                {
                  id: "platform",
                  name: "Direct members",
                  spend: 5,
                  tokens: 50,
                  requests: 1,
                },
              ],
            }
          : usage;
      },
    );
    renderOrganization();
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Engineering" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Infrastructure" }),
    );
    const chart = (
      await screen.findByRole("heading", { name: "Usage by Team" })
    ).closest("section")!;
    expect(within(chart).getByText("$10.00")).toBeVisible();
    expect(within(chart).getByText("$5.00")).toBeVisible();
    expect(within(chart).getAllByText("Direct members")).toHaveLength(2);
    fireEvent.click(
      within(chart).getByRole("button", { name: "Select Direct members" }),
    );
    await waitFor(() =>
      expect(api.organizationUsers).toHaveBeenLastCalledWith("platform", 1),
    );
    expect(
      within(
        screen.getByRole("navigation", { name: "Organization groups" }),
      ).getByRole("button", { name: "Direct members, 1 user" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("shows each leaf member's selected-period metrics without a Direct members bucket", async () => {
    renderOrganization();
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Engineering" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Infrastructure" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Cloud" }),
    );
    const chart = (
      await screen.findByRole("heading", { name: "Usage by member" })
    ).closest("section")!;
    expect(await within(chart).findByText("priya@example.com")).toBeVisible();
    expect(within(chart).getByText("$29.93")).toBeVisible();
    expect(within(chart).queryByText("Direct members")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Chart metric"), {
      target: { value: "requests" },
    });
    const calls = vi.mocked(api.organizationUsage).mock.calls;
    const [node, start, end] = calls[calls.length - 1];
    const report = organizationUsage(node, start, end);
    expect(
      within(chart).getByText(
        metricValue(report.by_user[0].requests, "requests"),
      ),
    ).toBeVisible();
    expect(
      screen.getByText("Budget-period spend / per-key allowance"),
    ).toBeVisible();
  });

  it("keeps group totals visible when an older report has no member breakdown", async () => {
    vi.mocked(api.organizationUsage).mockImplementation(
      async (node, start, end) => {
        const report = organizationUsage(node, start, end);
        Reflect.deleteProperty(report, "by_user");
        return report;
      },
    );
    renderOrganization();
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Engineering" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Infrastructure" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Cloud" }),
    );
    expect(
      await screen.findByText(
        "Per-member usage is unavailable in this report. Showing group totals.",
      ),
    ).toBeVisible();
    const chart = screen
      .getByRole("heading", { name: "Usage in this group" })
      .closest("section")!;
    expect(within(chart).getByText("$29.93")).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Usage by member" }),
    ).not.toBeInTheDocument();
  });

  it("does not query usage or users when the hierarchy is disabled", async () => {
    vi.mocked(api.organization).mockResolvedValue({
      enabled: false,
      groups: [],
      levels: [],
      total_users: 0,
      issues: [],
    });
    renderOrganization();
    expect(
      await screen.findByText(/Configure organizationHierarchy/),
    ).toBeVisible();
    expect(api.organizationUsage).not.toHaveBeenCalled();
    expect(api.organizationUsers).not.toHaveBeenCalled();
  });

  it("resets a removed selection when the hierarchy refreshes", async () => {
    const { client } = renderOrganization();
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Engineering" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Infrastructure" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Select Platform" }),
    );
    await waitFor(() =>
      expect(api.organizationUsers).toHaveBeenLastCalledWith("platform", 1),
    );
    expect(
      await within(
        screen.getByRole("heading", { name: /^Users/ }).closest("section")!,
      ).findByText("alex@example.com"),
    ).toBeVisible();
    const overview = organizationOverview();
    vi.mocked(api.organization).mockResolvedValue({
      ...overview,
      groups: overview.groups.map((group) =>
        group.id === "platform"
          ? { ...group, id: "renamed", name: "Renamed" }
          : group,
      ),
    });
    vi.mocked(api.organizationUsers).mockClear();
    vi.mocked(api.organizationUsage).mockClear();
    await act(async () => {
      await client.invalidateQueries({
        queryKey: ["organization"],
        exact: true,
      });
    });
    await waitFor(() =>
      expect(api.organizationUsers).toHaveBeenLastCalledWith("", 1),
    );
    expect(api.organizationUsers).not.toHaveBeenCalledWith(
      "platform",
      expect.any(Number),
    );
    expect(api.organizationUsage).not.toHaveBeenCalledWith(
      "platform",
      expect.any(String),
      expect.any(String),
    );
    expect(
      await screen.findByRole("button", { name: "Select Marketing" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("region", { name: "Effective budget policy" }),
    ).not.toBeInTheDocument();
    expect(await screen.findByText("sam@example.com")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "All groups, 4 users" }),
    ).toHaveAttribute("aria-pressed", "true");
  });
});
