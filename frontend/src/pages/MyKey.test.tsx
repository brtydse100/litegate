import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { CreateKeyCard } from "./MyKey";

describe("CreateKeyCard", () => {
  it.each([
    [true, "Saved keys can be shown again when you need them."],
    [false, "The secret is shown once, so copy it straight away."],
  ])("describes secret visibility when saved keys is %s", (savedKeys, text) => {
    render(
      <CreateKeyCard
        pending={false}
        paused={false}
        savedKeys={savedKeys}
        onCreate={vi.fn()}
      />,
    );
    expect(screen.getByText(text)).toBeVisible();
  });
});
