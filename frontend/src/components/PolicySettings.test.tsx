import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CurrentPolicySettings } from "./PolicySettings";
import type { KeyInfo } from "../types";

describe("current policy metadata", () => {
  it("handles null model lists from the upstream API without hiding the rest of the policy", () => {
    // The administrator API forwards upstream metadata, including nullable lists.
    const key = {
      models: null,
      spend: 4,
      max_budget: 50,
    } as unknown as KeyInfo;
    render(<CurrentPolicySettings settings={key} />);
    expect(screen.getByText("$50")).toBeVisible();
    expect(screen.getByText("All allowed models")).toBeVisible();
    expect(screen.getAllByText("Not provided").length).toBeGreaterThan(0);
  });
});
