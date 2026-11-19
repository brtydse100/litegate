import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Activity, Clock3 } from "lucide-react";
import { AdminSidebar, UserMenu } from "./AppChrome";

describe("UserMenu", () => {
  it("supports the menu keyboard pattern", () => {
    render(<UserMenu email="ann@example.test" onSignOut={vi.fn()} />);
    const trigger = screen.getByRole("button", { name: "Account menu" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const items = screen.getAllByRole("menuitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveFocus();
    fireEvent.keyDown(items[0], { key: "ArrowDown" });
    expect(items[1]).toHaveFocus();
    fireEvent.keyDown(items[1], { key: "ArrowDown" });
    expect(items[0]).toHaveFocus();
    fireEvent.keyDown(items[0], { key: "End" });
    expect(screen.getByRole("menuitem", { name: /Sign out/ })).toHaveFocus();
    fireEvent.keyDown(items[1], { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});

describe("AdminSidebar", () => {
  const groups = [
    {
      label: "System",
      items: [
        { to: "/status#audit", label: "Audit log", icon: Clock3 },
        { to: "/status", label: "Status", icon: Activity },
      ],
    },
  ];

  function activeAt(entry: string) {
    render(
      <MemoryRouter initialEntries={[entry]}>
        <AdminSidebar groups={groups} onSignOut={vi.fn()} />
      </MemoryRouter>,
    );
    return screen
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page")
      .map((link) => link.textContent);
  }

  it.each([
    ["/status", ["Status"]],
    ["/status/", ["Status"]],
    ["/status#audit", ["Audit log"]],
    ["/keys", []],
  ])("marks only the matching link active at %s", (entry, expected) => {
    expect(activeAt(entry)).toEqual(expected);
  });
});
