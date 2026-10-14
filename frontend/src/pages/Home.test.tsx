import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
  function renderHome(
    enabled: boolean,
    available: boolean,
    policy: Partial<KeyInfo> = {},
    listError?: Error,
    cachedEmpty = false,
    initiallyEmpty = false,
  ) {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ save_api_keys_in_db: enabled }),
      }),
    );
    const list = vi.spyOn(api, "listKeys").mockResolvedValue({
      keys: [
        {
          token: "hashed-key",
          spend: 3,
          models: [],
          secret_available: available,
          ...policy,
        },
      ],
    });
    if (listError) list.mockRejectedValue(listError);
    if (initiallyEmpty) list.mockResolvedValueOnce({ keys: [] });
    vi.spyOn(api, "getOperationLimit").mockResolvedValue({
      limit: 5,
      remaining: initiallyEmpty ? 5 : 0,
      retry_after: initiallyEmpty ? 0 : 60,
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    if (cachedEmpty) client.setQueryData(["keys"], { keys: [] });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/my-key"]}>
          <Home />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    return { list, client };
  }

  it("retains a one-time rotated secret if multiple cached cards remain after refresh fails", async () => {
    vi.spyOn(api, "regenerateKey").mockResolvedValue({
      key: "sk-synthetic-one-time",
      user_id: "owner",
    });
    const { list, client } = renderHome(false, false);
    await screen.findByRole("button", { name: "Regeneration paused" });
    vi.mocked(api.getOperationLimit).mockResolvedValue({
      limit: 5,
      remaining: 5,
      retry_after: 0,
    });
    list.mockRejectedValue(new Error("Metadata refresh unavailable"));
    act(() => {
      client.setQueryData(["keys"], {
        keys: [
          { token: "old-one", spend: 1, models: [] },
          { token: "old-two", spend: 2, models: [] },
        ],
      });
      client.setQueryData(["key-operation-limit"], {
        limit: 5,
        remaining: 5,
        retry_after: 0,
      });
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "Regenerate key" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Replace key" }));
    await screen.findByText("Metadata refresh unavailable");
    expect(screen.getByText("sk-synthetic-one-time")).toBeVisible();
    expect(screen.getByRole("button", { name: "Copy API key" })).toBeEnabled();
  });

  it("shows the actual stored key in the summary corner even during a mutation cooldown", async () => {
    const reveal = vi
      .spyOn(api, "revealKey")
      .mockResolvedValue({ key: "sk-synthetic-personal" });
    renderHome(true, true);
    expect(
      screen.queryByRole("button", { name: /regenerat/i }),
    ).not.toBeInTheDocument();
    expect(await screen.findByText("sk-synthetic-personal")).toBeVisible();
    expect(reveal).toHaveBeenCalledWith("hashed-key");
    const card = screen.getByText("Virtual key").closest("article")!;
    expect(within(card).getByText("sk-synthetic-personal")).toBeVisible();
    expect(screen.queryByTitle("Copy key identifier")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hide API key" }));
    expect(screen.queryByText("sk-synthetic-personal")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show API key" }));
    expect(await screen.findByText("sk-synthetic-personal")).toBeVisible();
  });

  it("keeps one secret inside the summary after creating and showing a key", async () => {
    vi.spyOn(api, "createKey").mockResolvedValue({
      key: "sk-synthetic-created",
      user_id: "owner",
    });
    vi.spyOn(api, "revealKey").mockResolvedValue({
      key: "sk-synthetic-created",
    });
    renderHome(true, true, {}, undefined, false, true);
    fireEvent.click(
      await screen.findByRole("button", { name: "Create API key" }),
    );
    await screen.findByText("Virtual key");
    await waitFor(() =>
      expect(screen.getByText("sk-synthetic-created")).toBeVisible(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Hide API key" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Show API key" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Copy API key" }),
      ).toBeEnabled(),
    );
    expect(await screen.findAllByText("sk-synthetic-created")).toHaveLength(1);
    expect(
      within(screen.getByText("Virtual key").closest("article")!).getByText(
        "sk-synthetic-created",
      ),
    ).toBeVisible();
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

  it("shows the enforced user allowance with a synchronization warning", async () => {
    renderHome(false, false, {
      organization_managed: true,
      user_budget_available: true,
      user_budget: 200,
      user_spend: 60,
      policy_error: "Budget update failed",
    });
    expect(await screen.findByText("$200")).toBeVisible();
    expect(screen.getByText("$60.0000")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Budget update failed");
  });

  it("keeps a governed key visible when its budget lookup is unavailable", async () => {
    renderHome(false, false, {
      organization_managed: true,
      user_budget_available: false,
      user_budget: null,
      user_spend: null,
      policy_error: "Budget service unavailable",
    });
    expect(
      await screen.findByRole("button", { name: "Regeneration paused" }),
    ).toBeVisible();
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.queryByText("Unlimited")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Budget service unavailable",
    );
  });

  it.each([false, true])(
    "does not offer key creation when listing keys fails (cached empty: %s)",
    async (cachedEmpty) => {
      renderHome(
        false,
        false,
        {},
        new Error("Key service unavailable"),
        cachedEmpty,
      );
      expect(await screen.findByText("Key service unavailable")).toBeVisible();
      expect(
        screen.queryByRole("button", {
          name: /Create API key|Key actions paused/,
        }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/Retry before creating or replacing a key/),
      ).toBeVisible();
    },
  );
});
