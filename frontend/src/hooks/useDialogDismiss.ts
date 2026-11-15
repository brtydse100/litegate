import { useEffect, useRef } from "react";

const dialogs: HTMLElement[] = [];
let previousOverflow = "";

function focusable(dialog: HTMLElement) {
  return [
    ...dialog.querySelectorAll<HTMLElement>(
      "a[href], button, input, select, textarea, [tabindex], [contenteditable=true]",
    ),
  ].filter((element) => {
    if (element.tabIndex < 0 || element.matches(":disabled")) return false;
    for (
      let parent: HTMLElement | null = element;
      parent;
      parent = parent.parentElement
    ) {
      const style = getComputedStyle(parent);
      if (
        parent.hidden ||
        parent.hasAttribute("inert") ||
        style.display === "none" ||
        style.visibility === "hidden"
      )
        return false;
      if (parent === dialog) break;
    }
    return true;
  });
}

export function useDialogDismiss<T extends HTMLElement = HTMLDivElement>(
  onClose: () => void,
  disabled = false,
  enabled = true,
) {
  const ref = useRef<T>(null);
  const options = useRef({ onClose, disabled });
  useEffect(() => {
    options.current = { onClose, disabled };
  }, [onClose, disabled]);
  useEffect(() => {
    const dialog = ref.current;
    if (!enabled || !dialog) return;
    const opener =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const tabIndex = dialog.getAttribute("tabindex");
    if (tabIndex === null) dialog.tabIndex = -1;
    if (!dialogs.length) previousOverflow = document.body.style.overflow;
    dialogs.push(dialog);
    document.body.style.overflow = "hidden";

    function focusFirst() {
      const elements = focusable(dialog!);
      (
        elements.find((element) =>
          element.hasAttribute("data-dialog-autofocus"),
        ) ??
        elements[0] ??
        dialog!
      ).focus();
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (dialogs[dialogs.length - 1] !== dialog) return;
      if (event.key === "Escape" && !options.current.disabled) {
        event.preventDefault();
        options.current.onClose();
      }
      if (event.key !== "Tab") return;
      const elements = focusable(dialog!);
      const first = elements[0],
        last = elements[elements.length - 1];
      if (!first) {
        event.preventDefault();
        dialog!.focus();
        return;
      }
      if (
        !dialog!.contains(document.activeElement) ||
        document.activeElement === dialog ||
        (event.shiftKey
          ? document.activeElement === first
          : document.activeElement === last)
      ) {
        event.preventDefault();
        (event.shiftKey ? last! : first).focus();
      }
    }
    function containFocus(event: FocusEvent) {
      if (
        dialogs[dialogs.length - 1] === dialog &&
        !dialog!.contains(event.target as Node)
      )
        focusFirst();
    }
    if (!dialog.contains(document.activeElement)) focusFirst();
    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("focusin", containFocus);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("focusin", containFocus);
      dialogs.splice(dialogs.indexOf(dialog), 1);
      if (!dialogs.length) document.body.style.overflow = previousOverflow;
      if (tabIndex === null) dialog.removeAttribute("tabindex");
      if (
        opener?.isConnected &&
        (!dialogs.length || dialogs[dialogs.length - 1].contains(opener))
      )
        opener.focus();
    };
  }, [enabled]);
  return ref;
}
