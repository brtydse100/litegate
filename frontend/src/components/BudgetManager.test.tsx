import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { BudgetView } from "../types/budgets";
import BudgetManager from "./BudgetManager";

vi.mock("../api/client", () => ({
  api: {
    organizationBudgets: vi.fn(),
    setGroupBudget: vi.fn(),
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
        assigned: 10,
        allocated: 10,
        reserved: 0,
        remainder: 0,
        used: null,
        remaining: null,
        can_edit_envelope: false,
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
        ],
      },
    ],
  };
}

function setup(data = view()) {
  vi.mocked(api.organizationBudgets).mockResolvedValue(data);
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <BudgetManager />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.resetAllMocks());

it("keeps invalid allocations visible so an administrator can repair the envelope", async () => {
  const initial = view();
  Object.assign(initial.groups[0], {
    can_edit_envelope: true,
    allocated: null,
    remainder: null,
    allocation_error: "Child allocations exceed the assigned budget",
  });
  Object.assign(initial.groups[0].users[0], { allocation: null });
  vi.mocked(api.setGroupBudget).mockResolvedValue(view(5));
  setup(initial);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Child allocations exceed the assigned budget",
  );
  expect(screen.getByText("Automatic: Unavailable")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Engineering assigned budget"), {
    target: { value: "20" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Save Engineering budget" }),
  );
  await waitFor(() =>
    expect(api.setGroupBudget).toHaveBeenCalledWith("root", 4, "20"),
  );
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
  );
});

it("shows automatic allocations and prevents edits to the administered root envelope", async () => {
  setup();
  expect(await screen.findByText("Engineering")).toBeInTheDocument();
  expect(screen.getByText(/not applied to inference/i)).toBeInTheDocument();
  expect(screen.getByText(/^Automatic:/)).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Save Engineering budget" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Activate budget enforcement" }),
  ).toBeDisabled();
});

it("submits an exact decimal and the latest revision, then refreshes the saved envelope", async () => {
  const initial = view();
  initial.groups[0].can_edit_envelope = true;
  const saved = view(5);
  saved.groups[0].can_edit_envelope = true;
  saved.groups[0].assigned = 12.345678;
  vi.mocked(api.setGroupBudget).mockResolvedValue(saved);
  setup(initial);
  fireEvent.change(
    await screen.findByLabelText("Engineering assigned budget"),
    { target: { value: "12.345678" } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Save Engineering budget" }),
  );
  await waitFor(() =>
    expect(api.setGroupBudget).toHaveBeenCalledWith("root", 4, "12.345678"),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Engineering assigned budget")).toHaveValue(
      12.345678,
    ),
  );
  fireEvent.change(
    screen.getByLabelText("Budget override for alice@example.invalid"),
    { target: { value: "0" } },
  );
  vi.mocked(api.setUserBudget).mockResolvedValue(view(6));
  fireEvent.click(screen.getByRole("button", { name: "Save user budget" }));
  await waitFor(() =>
    expect(api.setUserBudget).toHaveBeenCalledWith("root", "alice", 5, "0"),
  );
});

it("keeps zero as a manual override and sends null when restoring automatic allocation", async () => {
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
  fireEvent.change(
    await screen.findByLabelText("Budget override for alice@example.invalid"),
    { target: { value: "0" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save user budget" }));
  expect(
    await screen.findByText("Manual override: $0.000000"),
  ).toBeInTheDocument();
  expect(
    screen.getByLabelText("Budget override for alice@example.invalid"),
  ).toHaveValue(0);
  fireEvent.change(
    screen.getByLabelText("Budget override for alice@example.invalid"),
    { target: { value: "" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save user budget" }));
  await waitFor(() =>
    expect(api.setUserBudget).toHaveBeenNthCalledWith(
      2,
      "root",
      "alice",
      5,
      null,
    ),
  );
  expect(await screen.findByText("Automatic: $10.000000")).toBeInTheDocument();
  expect(
    screen.getByLabelText("Budget override for alice@example.invalid"),
  ).toHaveValue(null);
});

it("retains an unsuccessful draft and reports an allocation conflict", async () => {
  vi.mocked(api.setUserBudget).mockRejectedValue(
    new Error("Budget revision conflict; reload and retry"),
  );
  setup();
  fireEvent.change(
    await screen.findByLabelText("Budget override for alice@example.invalid"),
    { target: { value: "11" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save user budget" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Budget revision conflict",
  );
  expect(
    screen.getByLabelText("Budget override for alice@example.invalid"),
  ).toHaveValue(11);
  expect(screen.getByText("Automatic: $10.000000")).toBeInTheDocument();
});

it("reloads current budgets after a conflict so the draft can be saved again", async () => {
  vi.mocked(api.setUserBudget).mockRejectedValueOnce(
    new Error("Budget revision conflict; reload and retry"),
  );
  setup();
  fireEvent.change(
    await screen.findByLabelText("Budget override for alice@example.invalid"),
    { target: { value: "11" } },
  );
  vi.mocked(api.organizationBudgets).mockResolvedValue(view(7));
  fireEvent.click(screen.getByRole("button", { name: "Save user budget" }));
  await waitFor(() => expect(api.organizationBudgets).toHaveBeenCalledTimes(2));
  vi.mocked(api.setUserBudget).mockResolvedValue(view(8));
  fireEvent.click(screen.getByRole("button", { name: "Save user budget" }));
  await waitFor(() =>
    expect(api.setUserBudget).toHaveBeenLastCalledWith(
      "root",
      "alice",
      7,
      "11",
    ),
  );
});

it("keeps unsaved drafts in other groups when one group is saved", async () => {
  const initial = view();
  initial.groups.push({
    ...initial.groups[0],
    id: "child",
    name: "Platform",
    path: ["Engineering", "Platform"],
    can_edit_envelope: true,
    users: [],
  });
  const saved = structuredClone(initial);
  saved.revision = 5;
  vi.mocked(api.setUserBudget).mockResolvedValue(saved);
  setup(initial);
  fireEvent.change(await screen.findByLabelText("Platform assigned budget"), {
    target: { value: "3" },
  });
  fireEvent.change(
    screen.getByLabelText("Budget override for alice@example.invalid"),
    { target: { value: "2" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save user budget" }));
  // The saved override reverts to server data once the new revision lands.
  await waitFor(() =>
    expect(
      screen.getByLabelText("Budget override for alice@example.invalid"),
    ).toHaveValue(null),
  );
  expect(screen.getByLabelText("Platform assigned budget")).toHaveValue(3);
});

it("shows the enforced banner and fixed per-user allowances when enforcement is on", async () => {
  const enforced = view();
  enforced.applied = true;
  enforced.mode = "enforced";
  enforced.groups[0].users[0] = {
    ...enforced.groups[0].users[0],
    mode: "fixed",
    allocation: 7,
  };
  setup(enforced);
  expect(
    await screen.findByText(/Enforced: these allowances/),
  ).toBeInTheDocument();
  expect(screen.getByText("Fixed per-user: $7.000000")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Activate budget enforcement" }),
  ).not.toBeInTheDocument();
});
