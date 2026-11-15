import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import AdminUsers from "./AdminUsers";

afterEach(() => vi.restoreAllMocks());

function setup() {
  vi.spyOn(api, "listUsers").mockResolvedValue([
    {
      username: "alice",
      user_id: "local:alice",
      email: "alice@example.com",
      role: "user",
      active: true,
      created_at: "",
      updated_at: "",
    },
  ]);
  vi.spyOn(api, "getOperationLimit").mockResolvedValue({
    limit: 5,
    remaining: 5,
    retry_after: 0,
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <AdminUsers />
    </QueryClientProvider>,
  );
  return client;
}

it("shows reset errors in the modal, enforces the length limit and clears errors on reopening", async () => {
  vi.spyOn(api, "updateUser").mockRejectedValue(
    new Error("Password service unavailable"),
  );
  setup();
  fireEvent.click(
    await screen.findByRole("button", { name: "Reset password" }),
  );
  const dialog = screen.getByRole("dialog");
  const input = within(dialog).getByLabelText("New password");
  expect(input).toHaveAttribute("maxlength", "256");
  fireEvent.change(input, { target: { value: "synthetic-password" } });
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Reset password" }),
  );
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "Password service unavailable",
  );
  fireEvent.click(within(dialog).getByText("Cancel"));
  fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
  expect(
    within(screen.getByRole("dialog")).queryByText(
      "Password service unavailable",
    ),
  ).not.toBeInTheDocument();
});

it("explains a mutation cooldown inside the open reset dialog", async () => {
  const client = setup();
  fireEvent.click(
    await screen.findByRole("button", { name: "Reset password" }),
  );
  act(() =>
    client.setQueryData(["key-operation-limit"], {
      limit: 5,
      remaining: 0,
      retry_after: 30,
    }),
  );
  expect(
    await within(screen.getByRole("dialog")).findByRole("alert"),
  ).toHaveTextContent("30 seconds");
  expect(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "Reset password",
    }),
  ).toBeDisabled();
});
