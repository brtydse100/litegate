import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import PersonalKeySecret from "./PersonalKeySecret";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("loads and copies the actual stored secret instead of its identifier, then hides it", async () => {
  const reveal = vi
    .spyOn(api, "revealKey")
    .mockResolvedValue({ key: "sk-synthetic-personal" });
  const copy = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText: copy } });
  render(<PersonalKeySecret identifier="hashed-identifier" canReveal />);
  expect(await screen.findByText("sk-synthetic-personal")).toBeVisible();
  expect(reveal).toHaveBeenCalledWith("hashed-identifier");
  expect(screen.queryByText("hashed-identifier")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Copy API key" }));
  await waitFor(() =>
    expect(copy).toHaveBeenCalledWith("sk-synthetic-personal"),
  );
  fireEvent.click(screen.getByRole("button", { name: "Hide API key" }));
  expect(screen.queryByText("sk-synthetic-personal")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Show API key" })).toBeEnabled();
});

it("does not offer to copy a hash when no stored secret exists", () => {
  const reveal = vi.spyOn(api, "revealKey");
  render(
    <PersonalKeySecret identifier="hashed-identifier" canReveal={false} />,
  );
  expect(screen.getByText("Original key unavailable")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Copy API key" }),
  ).not.toBeInTheDocument();
  expect(reveal).not.toHaveBeenCalled();
});

it("clears the previous secret when the key identifier changes", async () => {
  vi.spyOn(api, "revealKey").mockResolvedValue({
    key: "sk-synthetic-previous",
  });
  const view = render(<PersonalKeySecret identifier="previous" canReveal />);
  expect(await screen.findByText("sk-synthetic-previous")).toBeVisible();
  view.rerender(<PersonalKeySecret identifier="different" canReveal={false} />);
  expect(screen.queryByText("sk-synthetic-previous")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Copy API key" }),
  ).not.toBeInTheDocument();
});

it("keeps a newly created secret available without storage and clears it on hide", async () => {
  const hide = vi.fn();
  render(
    <PersonalKeySecret
      identifier="hashed-identifier"
      canReveal={false}
      initialSecret="sk-synthetic-created"
      onHide={hide}
    />,
  );
  expect(await screen.findByText("sk-synthetic-created")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Hide API key" }));
  expect(screen.queryByText("sk-synthetic-created")).not.toBeInTheDocument();
  expect(hide).toHaveBeenCalled();
});
