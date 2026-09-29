import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { KeyInfo } from "../types";
import Home, { AccessSnapshot } from "./Home";

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    user: { user_id: "owner", role: "user", email: "owner@example.com" },
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function keyWithModels(models: string[]): KeyInfo {
  return { spend: 0, models };
}

describe("model access snapshot", () => {
  it("reveals the accessible model names when clicked", () => {
    render(
      <AccessSnapshot
        keys={[
          keyWithModels(["gpt-5", "claude-sonnet-4"]),
          keyWithModels(["gpt-5", "gemini-2.5-pro"]),
        ]}
      />,
    );

    const toggle = screen.getByRole("button", { name: /model access/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("gpt-5")).not.toBeInTheDocument();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("claude-sonnet-4")).toBeVisible();
    expect(screen.getByText("gemini-2.5-pro")).toBeVisible();
    expect(screen.getByText("gpt-5")).toBeVisible();
  });

  it("explains unrestricted access without inventing model names", () => {
    render(<AccessSnapshot keys={[keyWithModels([])]} />);

    fireEvent.click(screen.getByRole("button", { name: /model access/i }));

    expect(
      screen.getByText(/access all models available through this LiteLLM/i),
    ).toBeVisible();
  });
});

describe("personal key storage", () => {
  function renderHome(enabled: boolean, available: boolean) {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ save_api_keys_in_db: enabled }),
      }),
    );
    vi.spyOn(api, "listKeys").mockResolvedValue({
      keys: [
        {
          token: "hashed-key",
          spend: 3,
          models: [],
          secret_available: available,
        },
      ],
    });
    vi.spyOn(api, "getOperationLimit").mockResolvedValue({
      limit: 5,
      remaining: 0,
      retry_after: 60,
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/my-key"]}>
          <Home />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("replaces regeneration with reveal for stored keys even during a mutation cooldown", async () => {
    const reveal = vi
      .spyOn(api, "revealKey")
      .mockResolvedValue({ key: "sk-synthetic-personal" });
    renderHome(true, true);
    const button = await screen.findByRole("button", { name: "Show API key" });
    expect(button).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: /regenerat/i }),
    ).not.toBeInTheDocument();
    fireEvent.click(button);
    expect(await screen.findByText("sk-synthetic-personal")).toBeVisible();
    expect(reveal).toHaveBeenCalledWith("hashed-key");
  });

  it.each([
    [false, false],
    [true, false],
  ])(
    "keeps regeneration for disabled storage or an older key (%s, %s)",
    async (enabled, available) => {
      renderHome(enabled, available);
      expect(
        await screen.findByRole("button", { name: /regeneration paused/i }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Show API key" }),
      ).not.toBeInTheDocument();
    },
  );
});
