import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { PersonalAnalyticsData } from "../types/analytics";
import PersonalAnalytics from "./PersonalAnalytics";

vi.mock("../api/client", () => ({ api: { personalAnalytics: vi.fn() } }));

function snapshot(): PersonalAnalyticsData {
  const metrics = {
    requests: 3,
    tokens: 30,
    input_tokens: 20,
    output_tokens: null,
    cost: 0.03,
  };
  return {
    totals: metrics,
    daily: [{ ...metrics, date: "2026-11-15" }],
    models: [{ ...metrics, model: "model-a" }],
    budgets: [],
    available: true,
    stale: true,
    last_refreshed_at: "2026-11-16T12:00:00Z",
    coverage_start: "2026-08-19",
    coverage_end: "2026-11-16",
  };
}

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <PersonalAnalytics />
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.personalAnalytics).mockResolvedValue(snapshot());
});

describe("personal analytics", () => {
  it("shows personal metrics, freshness, model breakdown and unavailable tokens", async () => {
    setup();
    expect(await screen.findByText("Input tokens")).toBeInTheDocument();
    expect(screen.getByText("model-a")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(/previous successful refresh/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /daily usage cost/i }),
    ).toBeInTheDocument();
  });

  it("keeps the last successful snapshot visible after a failed background request", async () => {
    vi.mocked(api.personalAnalytics).mockResolvedValue({
      ...snapshot(),
      stale: false,
    });
    const client = setup();
    expect(await screen.findByText("model-a")).toBeInTheDocument();
    expect(
      screen.queryByText(/previous successful refresh/i),
    ).not.toBeInTheDocument();
    vi.mocked(api.personalAnalytics).mockRejectedValue(
      new Error("Network unavailable"),
    );
    await act(async () => {
      await client.refetchQueries({ queryKey: ["personal-analytics"] });
    });
    expect(
      await screen.findByText(/previous successful refresh/i),
    ).toBeInTheDocument();
    expect(screen.getByText("model-a")).toBeInTheDocument();
    expect(
      screen.getByText("$0.030000", { selector: "dd" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([false, true])(
    "explains unavailable analytics without presenting stored zero totals (refresh_failed=%s)",
    async (refreshFailed) => {
      vi.mocked(api.personalAnalytics).mockResolvedValue({
        ...snapshot(),
        available: false,
        refresh_failed: refreshFailed,
      });
      setup();
      expect(
        await screen.findByText(
          refreshFailed
            ? /temporarily unavailable/i
            : /first usage snapshot is pending/i,
        ),
      ).toBeInTheDocument();
      expect(screen.queryByText("Requests")).not.toBeInTheDocument();
      expect(screen.queryByRole("img")).not.toBeInTheDocument();
    },
  );

  it("offers retry when the first request fails", async () => {
    vi.mocked(api.personalAnalytics).mockRejectedValueOnce(
      new Error("Network unavailable"),
    );
    setup();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load your analytics",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("model-a")).toBeInTheDocument();
    await waitFor(() => expect(api.personalAnalytics).toHaveBeenCalledTimes(2));
  });

  it("keeps independent reset windows and unavailable allowances separate", async () => {
    vi.mocked(api.personalAnalytics).mockResolvedValue({
      ...snapshot(),
      budgets: [
        { number: 1, available: true, limit: 10, remaining: 8, duration: "1d" },
        {
          number: 2,
          available: true,
          limit: 20,
          remaining: 12,
          duration: "30d",
        },
        { number: 3, available: false },
      ],
    });
    setup();
    expect(
      await screen.findByText("Key 1: $8.000000 remaining of $10.000000 (1d)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Key 2: $12.000000 remaining of $20.000000 (30d)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Current allowance unavailable"),
    ).toBeInTheDocument();
  });
});
