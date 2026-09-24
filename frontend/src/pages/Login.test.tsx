import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Login from "./Login";

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({ login: vi.fn(), user: null }),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

function renderLogin() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("login configuration", () => {
  it("shows an error and recovers instead of silently hiding SSO", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ sso_enabled: true, local_enabled: false }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );

    renderLogin();

    expect(
      await screen.findByText(
        /sign-in configuration is temporarily unavailable/i,
      ),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() =>
      expect(
        screen.getByRole("link", { name: /sign in with sso/i }),
      ).toBeVisible(),
    );
  });
});
