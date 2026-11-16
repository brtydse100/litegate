import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import PeopleDirectory from "./PeopleDirectory";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("lists SSO/no-key people read-only and searches and paginates on the server", async () => {
  const list = vi
    .spyOn(api, "listPeople")
    .mockImplementation(async (page = 1, size = 25, search = "") => ({
      users: [
        {
          user_id: "sso-without-key",
          email: search || "sso@example.com",
          upstream_role: "internal_user",
        },
      ],
      page,
      size,
      total: 26,
      total_pages: 2,
    }));
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <PeopleDirectory />
    </QueryClientProvider>,
  );
  expect(await screen.findByText("sso@example.com")).toBeVisible();
  expect(screen.getByText("sso-without-key")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Reset password" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next people page" }));
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(2, 25, ""));
  fireEvent.change(screen.getByLabelText("Search people by email"), {
    target: { value: "person@example.com" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search people" }));
  expect(await screen.findByText("person@example.com")).toBeVisible();
  expect(list).toHaveBeenLastCalledWith(1, 25, "person@example.com");
});

it("reports a malformed successful page as unavailable without claiming there are no people", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <PeopleDirectory />
    </QueryClientProvider>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The people directory returned an invalid page. Try again later.",
  );
  expect(screen.queryByText("No people found.")).not.toBeInTheDocument();
  expect(screen.queryByText("0 people")).not.toBeInTheDocument();
});
