import { describe, expect, it } from "vitest";
import {
  allowedModels,
  budgetSummary,
  durationDays,
  durationLabel,
  isKeyExpired,
  parseLiteLLMDate,
} from "./keyBudget";
import type { KeyInfo } from "./types";

const NOW = Date.parse("2026-03-11T00:00:00Z");

function key(fields: Partial<KeyInfo>): KeyInfo {
  return { token: "t", spend: 0, ...fields } as KeyInfo;
}

describe("durationDays", () => {
  it("parses LiteLLM units", () => {
    expect(durationDays("30d")).toBe(30);
    expect(durationDays("1w")).toBe(7);
    expect(durationDays("1mo")).toBe(30);
    expect(durationDays("12h")).toBe(0.5);
    expect(durationDays("1440m")).toBe(1);
  });

  it("rejects empty, zero and unknown values", () => {
    expect(durationDays(null)).toBeNull();
    expect(durationDays("0d")).toBeNull();
    expect(durationDays("monthly")).toBeNull();
  });
});

describe("durationLabel", () => {
  it("names singular and plural periods", () => {
    expect(durationLabel("1mo")).toBe("1 month");
    expect(durationLabel("30d")).toBe("30 days");
    expect(durationLabel("custom")).toBe("custom");
    expect(durationLabel("")).toBeNull();
  });
});

describe("parseLiteLLMDate", () => {
  it("treats timestamps without a timezone as UTC", () => {
    expect(parseLiteLLMDate("2026-03-11 10:00:00").toISOString()).toBe(
      "2026-03-11T10:00:00.000Z",
    );
  });

  it("keeps explicit offsets, with or without a colon", () => {
    expect(parseLiteLLMDate("2026-03-11T10:00:00+0200").toISOString()).toBe(
      "2026-03-11T08:00:00.000Z",
    );
    expect(parseLiteLLMDate("2026-03-11T10:00:00+02:00").toISOString()).toBe(
      "2026-03-11T08:00:00.000Z",
    );
    expect(parseLiteLLMDate("2026-03-11T10:00:00Z").toISOString()).toBe(
      "2026-03-11T10:00:00.000Z",
    );
  });
});

describe("budgetSummary", () => {
  it("reports on-track spending against the period", () => {
    const summary = budgetSummary(
      key({
        spend: 10,
        max_budget: 30,
        budget_duration: "30d",
        budget_reset_at: "2026-03-21T00:00:00Z",
      }),
      NOW,
    );
    expect(summary.left).toBe(20);
    expect(summary.daysUntilReset).toBe(10);
    expect(summary.perDay).toBeCloseTo(0.5);
    expect(summary.onTrack).toBe(true);
  });

  it("reports over-pace spending", () => {
    const summary = budgetSummary(
      key({
        spend: 25,
        max_budget: 30,
        budget_duration: "30d",
        budget_reset_at: "2026-03-21T00:00:00Z",
      }),
      NOW,
    );
    expect(summary.onTrack).toBe(false);
  });

  it("handles a zero budget without dividing by zero", () => {
    const summary = budgetSummary(key({ spend: 0, max_budget: 0 }), NOW);
    expect(summary.left).toBe(0);
    expect(summary.remaining).toBe(0);
  });

  it("leaves remaining and pace empty without a budget", () => {
    const summary = budgetSummary(key({ spend: 4, max_budget: null }), NOW);
    expect(summary.budget).toBeNull();
    expect(summary.remaining).toBeNull();
    expect(summary.onTrack).toBeNull();
  });

  it("shows no daily pace for periods shorter than a day", () => {
    const summary = budgetSummary(
      key({
        spend: 2,
        max_budget: 5,
        budget_duration: "1h",
        budget_reset_at: "2026-03-11T00:30:00Z",
      }),
      NOW,
    );
    expect(summary.perDay).toBeNull();
    expect(summary.onTrack).toBeNull();
  });

  it("uses the member's own budget for organization keys", () => {
    const summary = budgetSummary(
      key({
        spend: 9,
        max_budget: 100,
        organization_managed: true,
        user_budget: 20,
        user_spend: 5,
        user_budget_available: false,
      }),
      NOW,
    );
    expect(summary.budget).toBe(20);
    expect(summary.spent).toBe(5);
    expect(summary.available).toBe(false);
  });
});

describe("allowedModels", () => {
  it("treats an empty list or all-proxy-models as every model", () => {
    expect(allowedModels([])).toBeNull();
    expect(allowedModels(["all-proxy-models", "gpt"])).toBeNull();
    expect(allowedModels(["b", "a", "b"])).toEqual(["a", "b"]);
  });
});

describe("isKeyExpired", () => {
  it("expires at the instant, reading timezone-less dates as UTC", () => {
    expect(isKeyExpired("2026-03-11 00:00:00", NOW)).toBe(true);
    expect(isKeyExpired("2026-03-11T00:00:01Z", NOW)).toBe(false);
    expect(isKeyExpired("2026-03-10T23:59:59", NOW)).toBe(true);
  });

  it("never expires a key without a valid date", () => {
    expect(isKeyExpired(null, NOW)).toBe(false);
    expect(isKeyExpired("", NOW)).toBe(false);
    expect(isKeyExpired("not a date", NOW)).toBe(false);
  });
});
