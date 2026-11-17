import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import DismissibleMessage from "./DismissibleMessage";

it("closes on × and shows again when a different message arrives", () => {
  const view = render(
    <DismissibleMessage messageKey="first" className="box">
      First problem
    </DismissibleMessage>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Dismiss message" }));
  expect(screen.queryByText("First problem")).not.toBeInTheDocument();
  view.rerender(
    <DismissibleMessage messageKey="second" className="box">
      Second problem
    </DismissibleMessage>,
  );
  expect(screen.getByText("Second problem")).toBeVisible();
});
