import { describe, expect, it } from "vitest";
import { parseModelBudgets } from "./ModelBudgetEditor";

describe("model budget validation", () => {
  it.each([
    { model: "", amount: "25", period: "2h" },
    { model: "opus", amount: "", period: "2h" },
    { model: "opus", amount: "-1", period: "2h" },
    { model: "opus", amount: "Infinity", period: "2h" },
    { model: "opus", amount: "NaN", period: "2h" },
    { model: "opus", amount: "25", period: "0h" },
    { model: "opus", amount: "25", period: "2hours" },
  ])("rejects invalid budget row $model/$amount/$period", (row) => {
    expect(() => parseModelBudgets([row])).toThrow();
  });

  it("rejects duplicate trimmed model names", () => {
    expect(() =>
      parseModelBudgets([
        { model: "opus", amount: "25", period: "2h" },
        { model: " opus ", amount: "10", period: "1d" },
      ]),
    ).toThrow("Each model can have only one budget.");
  });

  it("retains zero limits and independent periods for multiple models", () => {
    expect(
      parseModelBudgets([
        { model: " opus ", amount: "25.5", period: "2h" },
        { model: "other", amount: "0", period: "30d" },
      ]),
    ).toEqual({
      opus: { budget_limit: 25.5, time_period: "2h" },
      other: { budget_limit: 0, time_period: "30d" },
    });
  });
});
