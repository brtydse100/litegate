import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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

describe("account email", () => {
  it("is copyable from the sidebar footer", () => {
    render(
      <MemoryRouter>
        <AdminSidebar
          groups={[]}
          email="ann@example.test"
          role="admin"
          onSignOut={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("button", { name: "Copy email ann@example.test" }),
    ).toBeInTheDocument();
  });
});
