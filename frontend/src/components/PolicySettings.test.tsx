import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { CurrentPolicySettings, NumericPolicyInput } from "./PolicySettings";
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

describe("numeric policy controls", () => {
  it("adjusts decimal budgets without submitting the form", () => {
    const submit = vi.fn((event) => event.preventDefault());
    function Editor() {
      const [value, setValue] = useState("10.25");
      return (
        <form onSubmit={submit}>
          <NumericPolicyInput
            label="Budget"
            value={value}
            onValueChange={setValue}
            step="any"
          />
        </form>
      );
    }
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "Increase Budget" }));
    expect(screen.getByRole("spinbutton", { name: "Budget" })).toHaveValue(
      11.25,
    );
    fireEvent.click(screen.getByRole("button", { name: "Decrease Budget" }));
    expect(screen.getByRole("spinbutton", { name: "Budget" })).toHaveValue(
      10.25,
    );
    expect(submit).not.toHaveBeenCalled();
  });

  it("preserves disabled managed budgets and the zero minimum", () => {
    const change = vi.fn();
    const view = render(
      <NumericPolicyInput
        label="Budget"
        value="5"
        onValueChange={change}
        disabled
      />,
    );
    expect(
      screen.getByRole("button", { name: "Increase Budget" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Decrease Budget" }),
    ).toBeDisabled();
    view.rerender(
      <NumericPolicyInput label="Budget" value="0" onValueChange={change} />,
    );
    expect(
      screen.getByRole("button", { name: "Decrease Budget" }),
    ).toBeDisabled();
    expect(change).not.toHaveBeenCalled();
  });
});
