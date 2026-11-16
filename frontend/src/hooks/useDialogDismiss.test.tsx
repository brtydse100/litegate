import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it, vi } from "vitest";
import { useDialogDismiss } from "./useDialogDismiss";

function Modal({ onClose }: { onClose: () => void }) {
  const [pending, setPending] = useState(false);
  const ref = useDialogDismiss(onClose, pending);
  return (
    <div role="dialog" aria-modal="true" ref={ref}>
      <button onClick={() => setPending(true)}>First</button>
      <button>Last</button>
    </div>
  );
}

it("focuses the dialog, contains Tab in both directions and restores its opener", () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>Open</button>
        {open && <Modal onClose={() => setOpen(false)} />}
      </>
    );
  }
  render(<Harness />);
  const opener = screen.getByText("Open");
  opener.focus();
  fireEvent.click(opener);
  const first = screen.getByText("First");
  const last = screen.getByText("Last");
  expect(first).toHaveFocus();
  fireEvent.keyDown(first, { key: "Tab", shiftKey: true });
  expect(last).toHaveFocus();
  fireEvent.keyDown(last, { key: "Tab" });
  expect(first).toHaveFocus();
  fireEvent.keyDown(first, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(opener).toHaveFocus();
});

it("keeps focus contained while pending without resetting focus on a rerender", () => {
  const close = vi.fn();
  render(
    <>
      <button>Outside</button>
      <Modal onClose={close} />
    </>,
  );
  fireEvent.click(screen.getByText("First"));
  const last = screen.getByText("Last");
  last.focus();
  fireEvent.keyDown(last, { key: "Escape" });
  expect(close).not.toHaveBeenCalled();
  expect(last).toHaveFocus();
  screen.getByText("Outside").focus();
  expect(screen.getByText("First")).toHaveFocus();
});
