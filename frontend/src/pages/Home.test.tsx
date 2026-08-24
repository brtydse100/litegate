import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { KeyInfo } from "../types";
import { AccessSnapshot } from "./Home";

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
