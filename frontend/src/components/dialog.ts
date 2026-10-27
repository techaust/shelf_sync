// The ConfirmDialog's behaviour on the native <dialog> element, kept apart from React so it is tested with fakes
// (dialog.test.ts; the unit tests run without a DOM):
// - showModal(): the browser makes the rest of the page inert, so Tab and Shift+Tab stay inside the dialog (the
//   focus trap is the browser's own), and the dialog is in the top layer;
// - the first focus: Cancel when the action is destructive, otherwise the confirm button (as the approved mockup);
// - Esc fires "cancel": it is turned into the owner's Cancel (the React state closes the dialog), and ignored while
//   the confirmed action is being sent, so a half-sent action is never dismissed;
// - on close the focus goes back to the button that opened the dialog, or to a fallback when that is gone.

export interface Focusable {
  focus(options?: FocusOptions): void;
  readonly isConnected?: boolean;
}

export interface DialogElement {
  readonly open: boolean;
  showModal(): void;
  close(): void;
  addEventListener(type: "cancel", listener: (event: { preventDefault(): void }) => void): void;
  removeEventListener(type: "cancel", listener: (event: { preventDefault(): void }) => void): void;
}

export interface DialogBehaviour {
  /** Opens the dialog modally and focuses `first`; remembers `opener` for the way back. */
  open(first: Focusable | null, opener: Focusable | null): void;
  /** Closes the dialog (if open) and returns the focus. */
  close(): void;
  /** Stops listening (the component unmounts). Closes and returns the focus if still open. */
  dispose(): void;
}

export function dialogBehaviour(
  dialog: DialogElement,
  options: { onCancel: () => void; isBusy: () => boolean; fallback?: () => Focusable | null },
): DialogBehaviour {
  let opener: Focusable | null = null;
  const onCancelEvent = (event: { preventDefault(): void }) => {
    event.preventDefault(); // the React state decides when it closes
    if (!options.isBusy()) options.onCancel();
  };
  dialog.addEventListener("cancel", onCancelEvent);

  function giveBack(): void {
    const target = opener && opener.isConnected !== false ? opener : (options.fallback?.() ?? null);
    opener = null;
    target?.focus();
  }

  return {
    open(first, from) {
      opener = from;
      if (!dialog.open) dialog.showModal();
      first?.focus();
    },
    close() {
      if (!dialog.open) return;
      dialog.close();
      giveBack();
    },
    dispose() {
      dialog.removeEventListener("cancel", onCancelEvent);
      if (dialog.open) {
        dialog.close();
        giveBack();
      }
    },
  };
}
