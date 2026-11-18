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
import Home from "./Home";
import { BudgetCard, DetailsCard, StatusCard, keyAccessStatus } from "./MyKey";

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

describe("key status and details", () => {
  it.each([
    [{ blocked: true }, "Blocked"],
    [{ expires: "2000-01-01T00:00:00Z" }, "Expired"],
    [{ max_budget: 1, spend: 1 }, "Budget reached"],
  ])("shows known access restrictions (%j)", (state, label) => {
    const key: KeyInfo = { models: [], spend: 0, ...state };
    render(<StatusCard keyInfo={key} status={keyAccessStatus(key)} />);
    expect(screen.getByText(label)).toBeVisible();
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
  });

  it("reveals the accessible model names when clicked", () => {
    render(
      <DetailsCard
        keys={[
          keyWithModels(["gpt-5", "claude-sonnet-4"]),
          keyWithModels(["gpt-5", "gemini-2.5-pro", "o3"]),
        ]}
      />,
    );
    const toggle = screen.getByRole("button", { name: "4 models" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("gpt-5")).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const list = screen.getByRole("list", { name: "Accessible models" });
    expect(within(list).getByText("claude-sonnet-4")).toBeVisible();
    expect(within(list).getByText("gemini-2.5-pro")).toBeVisible();
    expect(within(list).getByText("gpt-5")).toBeVisible();
  });

  it("interprets timezone-less expiration as UTC outside UTC browsers", () => {
    vi.stubEnv("TZ", "America/New_York");
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-16T12:30:00Z"));
    try {
      expect(
        keyAccessStatus({
          models: [],
          spend: 0,
          expires: "2026-11-16T12:00:00",
        }),
      ).toBe("Expired");
    } finally {
      vi.useRealTimers();
      vi.unstubAllEnvs();
    }
  });

  it("explains unrestricted access without inventing model names", () => {
    render(<DetailsCard keys={[keyWithModels(["all-proxy-models"])]} />);
    expect(screen.getByText("All models")).toBeVisible();
    expect(screen.queryByText("all-proxy-models")).not.toBeInTheDocument();
  });

  it("shows the remaining budget, refill date and pace from key metadata", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-19T00:00:00Z"));
    try {
      render(
        <BudgetCard
          keyInfo={{
            models: [],
            spend: 18.42,
            max_budget: 100,
            budget_duration: "30d",
            budget_reset_at: "2026-12-01T00:00:00Z",
          }}
        />,
      );
      expect(
        screen.getByRole("img", { name: "82% of budget remaining" }),
      ).toBeVisible();
      expect(screen.getByText("$81.58")).toBeVisible();
      expect(screen.getByText(/Refills to \$100\.00 in 12 days/)).toBeVisible();
      expect(screen.getByText("On track")).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
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
    configState?: "pending" | "error",
    keyPending = false,
    myKeyText?: string,
  ) {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          save_api_keys_in_db: enabled,
          my_key_text: myKeyText,
        }),
      }),
    );
    if (configState === "pending")
      vi.mocked(fetch).mockReturnValue(new Promise(() => {}));
    if (configState === "error")
      vi.mocked(fetch).mockRejectedValue(new Error("Config unavailable"));
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
    if (keyPending) list.mockReturnValue(new Promise(() => {}));
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

  it("offers a working retry after a key lookup error", async () => {
    const { list } = renderHome(
      false,
      false,
      {},
      new Error("Key service unavailable"),
    );
    await screen.findByText("Key service unavailable");
    list.mockResolvedValue({ keys: [] });
    fireEvent.click(
      screen.getByRole("button", { name: "Retry key information" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByText("Key service unavailable"),
      ).not.toBeInTheDocument(),
    );
  });

  it("offers a working retry after portal configuration fails", async () => {
    renderHome(false, false, {}, undefined, false, false, "error");
    await screen.findByText(/Portal configuration is unavailable/);
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ save_api_keys_in_db: false }),
    } as Response);
    fireEvent.click(
      screen.getByRole("button", { name: "Retry portal configuration" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByText(/Portal configuration is unavailable/),
      ).not.toBeInTheDocument(),
    );
  });

  it("names the mobile sign-out control even when its text is hidden", async () => {
    renderHome(false, false);
    await screen.findByText("YOUR API KEY");
    fireEvent.click(screen.getByRole("button", { name: "Account menu" }));
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeVisible();
  });

  it("keeps plain multiline guidance beneath the action before and after key creation", async () => {
    const message = 'Keep this key safe.\n<img src=x onerror="alert(1)">';
    vi.spyOn(api, "createKey").mockResolvedValue({
      key: "sk-synthetic-guidance",
      user_id: "owner",
    });
    renderHome(
      false,
      false,
      {},
      undefined,
      false,
      true,
      undefined,
      false,
      message,
    );
    const action = await screen.findByRole("button", {
      name: "Create my API key",
    });
    const guidance = screen.getByText(/Keep this key safe/);
    expect(guidance.textContent).toBe(message);
    expect(guidance).toHaveClass("whitespace-pre-wrap", "break-words");
    expect(guidance.querySelector("img")).toBeNull();
    expect(
      action.compareDocumentPosition(guidance) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    fireEvent.click(action);
    await screen.findByText("sk-synthetic-guidance");
    const hide = screen.getByRole("button", { name: "Hide API key" });
    expect(
      screen.queryByRole("button", { name: /regenerat/i }),
    ).not.toBeInTheDocument();
    expect(guidance).toBeVisible();
    expect(
      hide.compareDocumentPosition(guidance) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    fireEvent.click(hide);
    expect(screen.queryByText("sk-synthetic-guidance")).not.toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Regenerate key" }),
    ).toBeVisible();
  });

  it("uses one action to hide a regenerated secret and then restores regeneration", async () => {
    vi.spyOn(api, "regenerateKey").mockResolvedValue({
      key: "sk-synthetic-regenerated",
      user_id: "owner",
    });
    const { list, client } = renderHome(false, false);
    await screen.findByRole("button", { name: "Regeneration paused" });
    vi.mocked(api.getOperationLimit).mockResolvedValue({
      limit: 5,
      remaining: 5,
      retry_after: 0,
    });
    act(() => {
      client.setQueryData(["key-operation-limit"], {
        limit: 5,
        remaining: 5,
        retry_after: 0,
      });
    });
    list.mockResolvedValue({
      keys: [{ token: "rotated-hash", spend: 3, models: [] }],
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "Regenerate key" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Replace key" }));
    await screen.findByText("sk-synthetic-regenerated");
    const hide = screen.getByRole("button", { name: "Hide API key" });
    expect(
      screen.getAllByRole("button", { name: "Hide API key" }),
    ).toHaveLength(1);
    expect(
      screen.queryByRole("button", { name: /regenerat/i }),
    ).not.toBeInTheDocument();
    fireEvent.click(hide);
    expect(
      screen.queryByText("sk-synthetic-regenerated"),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Regenerate key" }),
    ).toBeVisible();
  });

  it("retains guidance when stored-key mode hides regeneration", async () => {
    vi.spyOn(api, "revealKey").mockResolvedValue({ key: "sk-synthetic-saved" });
    renderHome(
      true,
      true,
      {},
      undefined,
      false,
      false,
      undefined,
      false,
      "Ask your administrator for help.",
    );
    const guidance = await screen.findByText(
      "Ask your administrator for help.",
    );
    await screen.findByText("sk-synthetic-saved");
    expect(guidance).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /regenerat/i }),
    ).not.toBeInTheDocument();
  });

  it.each([undefined, "", "  \n "])(
    "hides empty My key guidance (%j)",
    async (message) => {
      renderHome(
        false,
        false,
        {},
        undefined,
        false,
        false,
        undefined,
        false,
        message,
      );
      await screen.findByText("YOUR API KEY");
      expect(
        screen.queryByLabelText("My key guidance"),
      ).not.toBeInTheDocument();
    },
  );

  it("offers no replacement after key lookup fails with a cached key", async () => {
    const { list, client } = renderHome(false, false);
    await screen.findByText("YOUR API KEY");
    list.mockRejectedValue(new Error("Lookup unavailable"));
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["keys"] });
    });
    await screen.findByText(/Key information is unavailable/);
    expect(
      screen.queryByRole("button", { name: /regenerat|create my API key/i }),
    ).not.toBeInTheDocument();
  });

  it("offers no replacement while key lookup is pending", async () => {
    renderHome(true, false, {}, undefined, false, false, undefined, true);
    await screen.findByText(/Loading key information/);
    expect(
      screen.queryByRole("button", { name: /regenerat|create my API key/i }),
    ).not.toBeInTheDocument();
  });

  it.each(["pending", "error"] as const)(
    "does not advise regeneration while configuration is %s",
    async (state) => {
      renderHome(true, false, {}, undefined, false, false, state);
      await screen.findByText(
        state === "pending"
          ? /Loading portal configuration/
          : /Portal configuration is unavailable/,
      );
      expect(
        screen.queryByRole("button", { name: /regenerat/i }),
      ).not.toBeInTheDocument();
      expect(screen.queryByText(/only shown once/i)).not.toBeInTheDocument();
    },
  );

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

  it("shows the stored key in the key card with its toggle during a cooldown", async () => {
    const reveal = vi
      .spyOn(api, "revealKey")
      .mockResolvedValue({ key: "sk-synthetic-personal" });
    renderHome(true, true);
    expect(
      screen.queryByRole("button", { name: /regenerat/i }),
    ).not.toBeInTheDocument();
    expect(await screen.findByText("sk-synthetic-personal")).toBeVisible();
    expect(reveal).toHaveBeenCalledWith("hashed-key");
    const card = screen.getByRole("region", { name: "Key" });
    expect(within(card).getByText("sk-synthetic-personal")).toBeVisible();
    expect(
      within(card).getByRole("button", { name: "Hide API key" }),
    ).toBeVisible();
    expect(screen.queryByTitle("Copy key identifier")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hide API key" }));
    expect(screen.queryByText("sk-synthetic-personal")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show API key" }));
    expect(await screen.findByText("sk-synthetic-personal")).toBeVisible();
  });

  it("uses the same highlighted field after creating and revealing a key", async () => {
    vi.spyOn(api, "createKey").mockResolvedValue({
      key: "sk-synthetic-created",
      user_id: "owner",
    });
    vi.spyOn(api, "revealKey").mockResolvedValue({
      key: "sk-synthetic-created",
    });
    renderHome(true, true, {}, undefined, false, true);
    fireEvent.click(
      await screen.findByRole("button", { name: "Create my API key" }),
    );
    await screen.findByText("YOUR API KEY");
    await waitFor(() =>
      expect(screen.getByText("sk-synthetic-created")).toBeVisible(),
    );
    const createdPanel = screen.getByText(
      "sk-synthetic-created",
    ).parentElement!;
    expect(createdPanel).toHaveClass("bg-mint-tint");
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
    const revealed = screen.getByText("sk-synthetic-created");
    expect(revealed.parentElement).toHaveAttribute(
      "class",
      createdPanel.className,
    );
    expect(
      within(screen.getByRole("region", { name: "Key" })).getByText(
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
    expect(await screen.findByText("of $200.00")).toBeVisible();
    expect(screen.getByText("$140.00")).toBeVisible();
    expect(screen.getByText("$60.00")).toBeVisible();
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

  it("tells a moved user where they went in one dismissible info box", async () => {
    renderHome(false, false, {
      organization_managed: true,
      user_budget_available: true,
      user_budget: 50,
      user_spend: 5,
      policy_notice:
        "You were moved to Engineering / Platform. Your key moves there within about a minute.",
    });
    const notice = await screen.findByText(/You were moved to Engineering/);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/Key status:/)).not.toBeInTheDocument();
    fireEvent.click(
      within(notice.closest("[role=status]") as HTMLElement).getByRole(
        "button",
        { name: "Dismiss message" },
      ),
    );
    expect(
      screen.queryByText(/You were moved to Engineering/),
    ).not.toBeInTheDocument();
  });

  it("shows one warning, not two, when a key needs attention", async () => {
    renderHome(false, false, {
      organization_managed: true,
      user_budget_available: false,
      policy_error:
        "Your organization mapping was removed; contact an administrator",
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "mapping was removed",
    );
    expect(screen.queryByText(/Key status:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Policy unavailable/)).not.toBeInTheDocument();
  });

  it("offers replacement for an organization-managed key", async () => {
    renderHome(false, false, {
      organization_managed: true,
      user_budget_available: true,
    });
    expect(
      await screen.findByRole("button", {
        name: /Regenerate key|Regeneration paused/,
      }),
    ).toBeVisible();
    expect(screen.queryByText(/can't be replaced/)).not.toBeInTheDocument();
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
          name: /Create my API key|Key actions paused/,
        }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/Retry before creating or replacing a key/),
      ).toBeVisible();
    },
  );
});
