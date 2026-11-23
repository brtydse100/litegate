import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { BudgetView } from "../../types/budgets";
import PeopleTable from "./PeopleTable";

vi.mock("../../api/client", () => ({
  api: {
    organizationBudgets: vi.fn(),
    organizationUsers: vi.fn(),
    setUserBudget: vi.fn(),
  },
}));

function view(revision = 4): BudgetView {
  return {
    revision,
    mode: "preview",
    applied: false,
    pending: false,
    capability: {
      supported: false,
      version: "1.109.1",
      reasons: ["Native enforcement requires verification"],
    },
    groups: [
      {
        id: "root",
        name: "Engineering",
        path: ["Engineering"],
        parent_id: null,
        duration: "30d",
        assigned: 20,
        allocated: 20,
        reserved: 0,
        remainder: 0,
        used: null,
        remaining: null,
        can_edit_envelope: false,
        per_user: 100,
        per_user_config: 100,
        per_user_override: null,
        can_edit_per_user: false,
        users: [
          {
            user_id: "alice",
            email: "alice@example.invalid",
            allocation: 10,
            override: null,
            mode: "automatic",
            used: null,
            remaining: null,
            can_edit: true,
          },
          {
            user_id: "owner",
            email: "owner@example.invalid",
            allocation: 10,
            override: null,
            mode: "automatic",
            used: null,
            remaining: null,
            can_edit: false,
          },
        ],
      },
    ],
  };
}

/** Reads budgets through the shared query, as the Organization page does. */
function Harness() {
  const budgets = useQuery({
    queryKey: ["organization-budgets"],
    queryFn: api.organizationBudgets,
  });
  return (
    <PeopleTable
      standalone
      nodeIds={["root"]}
      title="People in Engineering"
      budgets={budgets.data}
    />
  );
}

function setup(data = view()) {
  vi.mocked(api.organizationBudgets).mockResolvedValue(data);
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <Harness />
    </QueryClientProvider>,
  );
}

const override = () =>
  screen.findByLabelText("Budget override for alice@example.invalid");
const save = () =>
  fireEvent.click(
    screen.getByRole("button", {
      name: "Save allowance for alice@example.invalid",
    }),
  );

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.organizationUsers).mockResolvedValue({
    users: ["alice", "owner"].map((user) => ({
      user_id: user,
      email: `${user}@example.invalid`,
      node: "root",
      path: ["Engineering"],
      per_user: 100,
      duration: "30d",
      budget_spend: 3,
      sync_error: null,
    })),
    page: 1,
    page_size: 25,
    total: 2,
    total_pages: 1,
  });
});

it("shows each member's allowance and keeps the viewer's own read-only", async () => {
  setup();
  expect(await screen.findAllByText("Automatic: $10.00")).toHaveLength(2);
  expect(
    screen.getByText(/proposals and do not cap keys yet/),
  ).toBeInTheDocument();
  expect(await override()).toBeVisible();
  expect(
    screen.queryByLabelText("Budget override for owner@example.invalid"),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText("Set by a parent team or a system administrator"),
  ).toBeVisible();
});

it("keeps zero as a manual override and sends null to restore automatic", async () => {
  const manual = view(5);
  manual.groups[0].users[0] = {
    ...manual.groups[0].users[0],
    override: 0,
    allocation: 0,
    mode: "manual",
  };
  vi.mocked(api.setUserBudget)
    .mockResolvedValueOnce(manual)
    .mockResolvedValueOnce(view(6));
  setup();
  fireEvent.change(await override(), { target: { value: "0" } });
  save();
  await waitFor(() =>
    expect(api.setUserBudget).toHaveBeenCalledWith("root", "alice", 4, "0"),
  );
  expect(await screen.findByText("Manual override: $0.00")).toBeVisible();
  expect(await override()).toHaveValue(0);
  fireEvent.change(await override(), { target: { value: "" } });
  save();
  await waitFor(() =>
    expect(api.setUserBudget).toHaveBeenLastCalledWith(
      "root",
      "alice",
      5,
      null,
    ),
  );
  expect(await override()).toHaveValue(null);
});

it("keeps a rejected draft, reports it and reloads budgets for a retry", async () => {
  vi.mocked(api.setUserBudget).mockRejectedValueOnce(
    new Error("Budget revision conflict; reload and retry"),
  );
  setup();
  fireEvent.change(await override(), { target: { value: "11" } });
  vi.mocked(api.organizationBudgets).mockResolvedValue(view(7));
  save();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Budget revision conflict",
  );
  expect(await override()).toHaveValue(11);
  await waitFor(() => expect(api.organizationBudgets).toHaveBeenCalledTimes(2));
  vi.mocked(api.setUserBudget).mockResolvedValue(view(8));
  save();
  await waitFor(() =>
    expect(api.setUserBudget).toHaveBeenLastCalledWith(
      "root",
      "alice",
      7,
      "11",
    ),
  );
});

it("keeps invalid allocations visible and states when allowances are enforced", async () => {
  const broken = view();
  broken.applied = true;
  broken.mode = "enforced";
  Object.assign(broken.groups[0], {
    allocated: null,
    remainder: null,
    allocation_error: "Child allocations exceed the assigned budget",
  });
  Object.assign(broken.groups[0].users[0], { allocation: null });
  setup(broken);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Engineering: Child allocations exceed the assigned budget",
  );
  expect(screen.getByText("Automatic: Unavailable")).toBeVisible();
  expect(screen.getByText(/Enforced: these allowances/)).toBeVisible();
});

it("shows fixed allowances without budget planning", async () => {
  vi.mocked(api.organizationBudgets).mockResolvedValue(view());
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PeopleTable nodeIds={["root"]} title="Users" />
    </QueryClientProvider>,
  );
  expect(await screen.findAllByText("$100.00")).toHaveLength(2);
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(
    screen.queryByLabelText("Budget override for alice@example.invalid"),
  ).not.toBeInTheDocument();
});
