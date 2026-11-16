import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import EmailAddress from "./EmailAddress";

it("shows a complete selectable wrapping address and copies it with status", async () => {
  const email = "a.very.long.email.address@a.very.long.example.com";
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
  render(<EmailAddress email={email} />);
  expect(screen.getByText(email)).toHaveClass("break-all", "select-text");
  fireEvent.click(screen.getByRole("button", { name: `Copy email ${email}` }));
  expect(await screen.findByRole("status")).toHaveTextContent("Email copied");
  expect(writeText).toHaveBeenCalledWith(email);
});

it("announces clipboard failure without losing the full address", async () => {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    configurable: true,
  });
  render(<EmailAddress email="person@example.com" />);
  fireEvent.click(
    screen.getByRole("button", { name: "Copy email person@example.com" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Could not copy email",
  );
  expect(screen.getByText("person@example.com")).toBeVisible();
});
