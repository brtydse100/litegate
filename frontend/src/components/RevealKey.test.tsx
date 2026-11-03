import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import RevealKey from "./RevealKey";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("RevealKey", () => {
  it.each([false, true])(
    "uses the same button to reveal and hide without fetching on hide (compact: %s)",
    async (compact) => {
      const reveal = vi
        .spyOn(api, "revealKey")
        .mockResolvedValue({ key: "sk-synthetic-revealed" });
      const copy = vi.fn().mockResolvedValue(undefined);
      vi.stubGlobal("navigator", { clipboard: { writeText: copy } });
      render(<RevealKey identifier="hashed-key-id" compact={compact} />);
      expect(reveal).not.toHaveBeenCalled();
      const toggle = screen.getByRole("button", { name: "Show API key" });
      fireEvent.click(toggle);
      expect(await screen.findByText("sk-synthetic-revealed")).toBeVisible();
      expect(toggle).toHaveTextContent("Hide API key");
      expect(screen.getByRole("button", { name: "Hide API key" })).toBe(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(
        screen.queryByRole("button", { name: "Show API key" }),
      ).not.toBeInTheDocument();
      expect(reveal).toHaveBeenCalledWith("hashed-key-id");
      fireEvent.click(screen.getByRole("button", { name: "Copy API key" }));
      await waitFor(() =>
        expect(copy).toHaveBeenCalledWith("sk-synthetic-revealed"),
      );
      fireEvent.click(toggle);
      expect(
        screen.queryByText("sk-synthetic-revealed"),
      ).not.toBeInTheDocument();
      expect(toggle).toHaveTextContent("Show API key");
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(reveal).toHaveBeenCalledTimes(1);
      fireEvent.click(toggle);
      expect(await screen.findByText("sk-synthetic-revealed")).toBeVisible();
      expect(reveal).toHaveBeenCalledTimes(2);
    },
  );

  it("shows an actionable error when the stored copy is unavailable", async () => {
    vi.spyOn(api, "revealKey").mockRejectedValue(
      new Error("No stored copy is available."),
    );
    render(<RevealKey identifier="old-key" />);
    fireEvent.click(screen.getByRole("button", { name: "Show API key" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No stored copy is available.",
    );
    expect(
      screen.queryByRole("button", { name: "Copy API key" }),
    ).not.toBeInTheDocument();
  });
});
