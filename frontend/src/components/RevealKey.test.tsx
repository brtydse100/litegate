import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import RevealKey from "./RevealKey";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("RevealKey", () => {
  it("fetches only on click, copies the secret, and hides it", async () => {
    const reveal = vi
      .spyOn(api, "revealKey")
      .mockResolvedValue({ key: "sk-synthetic-revealed" });
    const copy = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText: copy } });
    render(<RevealKey identifier="hashed-key-id" />);
    expect(reveal).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Show API key" }));
    expect(await screen.findByText("sk-synthetic-revealed")).toBeVisible();
    expect(reveal).toHaveBeenCalledWith("hashed-key-id");
    fireEvent.click(screen.getByRole("button", { name: "Copy API key" }));
    await waitFor(() =>
      expect(copy).toHaveBeenCalledWith("sk-synthetic-revealed"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Hide API key" }));
    expect(screen.queryByText("sk-synthetic-revealed")).not.toBeInTheDocument();
  });

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
