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
  it("shows the configured logo and renders custom login text as plain text", async () => {
    const loginText = 'Welcome to Example\n<img src=x onerror="alert(1)">';
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          sso_enabled: true,
          local_enabled: false,
          login_text: loginText,
          logo_url: "/example-logo.svg",
        }),
      ),
    );

    const { container } = renderLogin();

    const logo = await screen.findByRole("img", { name: /organization logo/i });
    expect(logo).toHaveAttribute("src", "/example-logo.svg");
    expect(screen.getByText(/Welcome to Example/).textContent).toBe(loginText);
    expect(container.querySelectorAll("img")).toHaveLength(1);
    expect(
      screen.queryByText("Sign in to your LiteLLM access portal"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /sign in with sso/i }),
    ).toBeVisible();
  });

  it.each(["", "   \n "])(
    "keeps the default branding when login text is blank (%j)",
    async (loginText) => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(
          JSON.stringify({
            sso_enabled: false,
            local_enabled: true,
            login_text: loginText,
            logo_url: "",
          }),
        ),
      );

      renderLogin();

      expect(
        await screen.findByRole("textbox", { name: "Username" }),
      ).toBeVisible();
      expect(
        screen.getByText("Sign in to your LiteLLM access portal"),
      ).toBeVisible();
      expect(screen.queryByRole("img")).not.toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "LiteGate" })).toBeVisible();
    },
  );

  it("shows an error and recovers instead of silently hiding SSO", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            sso_enabled: true,
            local_enabled: false,
            login_text: "",
            logo_url: "",
          }),
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
