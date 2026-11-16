import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { AuthProvider, useAuth } from "./useAuth";

afterEach(() => vi.restoreAllMocks());

function Session() {
  const { user, loading, login, logout } = useAuth();
  return (
    <>
      <p>{loading ? "Loading" : (user?.user_id ?? "Signed out")}</p>
      <button onClick={() => void logout().catch(() => undefined)}>
        Logout
      </button>
      <button onClick={() => void login()}>Login</button>
    </>
  );
}

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const me = vi.spyOn(api, "me").mockResolvedValue({
    user_id: "first",
    email: "first@example.com",
    role: "admin",
    auth_source: "sso",
    team_ids: [],
  });
  vi.spyOn(api, "logout").mockResolvedValue({ signed_out: true });
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Session />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return { client, me };
}

it("clears private queries and mutation results on logout", async () => {
  const { client } = setup();
  await screen.findByText("first");
  client.setQueryData(["keys"], [{ user_id: "first" }]);
  const mutation = client.getMutationCache().build(client, {
    mutationFn: async () => "previous secret",
  });
  await act(() => mutation.execute(undefined));
  fireEvent.click(screen.getByText("Logout"));
  await screen.findByText("Signed out");
  expect(client.getQueryData(["keys"])).toBeUndefined();
  expect(client.getMutationCache().getAll()).toHaveLength(0);
});

it("clears the old account before exposing the next session, including delayed queries", async () => {
  const { client, me } = setup();
  await screen.findByText("first");
  client.setQueryData(["keys"], [{ user_id: "first" }]);
  let complete!: (value: string) => void;
  const oldRequest = client
    .fetchQuery({
      queryKey: ["admin-users"],
      queryFn: () =>
        new Promise<string>((resolve) => {
          complete = resolve;
        }),
    })
    .catch(() => undefined);
  me.mockResolvedValue({
    user_id: "second",
    email: "second@example.com",
    role: "user",
    auth_source: "local",
    team_ids: [],
  });
  fireEvent.click(screen.getByText("Login"));
  await screen.findByText("second");
  await act(async () => {
    complete("first account's data");
    await oldRequest;
  });
  expect(client.getQueryData(["keys"])).toBeUndefined();
  expect(client.getQueryData(["admin-users"])).toBeUndefined();
});

it("clears private data even when server logout fails", async () => {
  const { client } = setup();
  await screen.findByText("first");
  client.setQueryData(["keys"], "private");
  // The UI handles reporting the network error; cache cleanup remains mandatory.
  vi.spyOn(api, "logout").mockRejectedValue(new Error("network failure"));
  fireEvent.click(screen.getByText("Logout"));
  await screen.findByText("Signed out");
  await waitFor(() => expect(client.getQueryData(["keys"])).toBeUndefined());
});
