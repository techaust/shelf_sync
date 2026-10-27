// The ConfirmDialog's behaviour on the native <dialog> element, kept apart from React so it is tested with fakes
// (dialog.test.ts; the unit tests run without a DOM):
// - showModal(): the browser makes the rest of the page inert, so Tab and Shift+Tab stay inside the dialog (the
//   focus trap is the browser's own), and the dialog is in the top layer;
// - the first focus: Cancel when the action is destructive, otherwise the confirm button (as the approved mockup);
// - Esc fires "cancel": it is turned into the owner's Cancel (the React state closes the dialog), and ignored while
//   the confirmed action is being sent, so a half-sent action is never dismissed;
// - a second Esc closes a native dialog even when "cancel" was prevented (Chrome's close watcher). So "close" is
//   watched too: while React still wants it open and the action is being sent, it opens again; otherwise React is
//   told (onCancel), so its state matches what is on screen;
// - on close the focus goes back to the button that opened the dialog, or to a fallback when that is gone.

export interface Focusable {
  focus(options?: FocusOptions): void;
  readonly isConnected?: boolean;
}

type DialogEvent = { preventDefault(): void };

export interface DialogElement {
  readonly open: boolean;
  showModal(): void;
  close(): void;
  addEventListener(type: "cancel" | "close", listener: (event: DialogEvent) => void): void;
  removeEventListener(type: "cancel" | "close", listener: (event: DialogEvent) => void): void;
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
  options: {
    onCancel: () => void;
    isBusy: () => boolean;
    fallback?: () => Focusable | null;
    /** Where the focus goes when the dialog opens again mid-send (the confirm button, busy). */
    busyFocus?: () => Focusable | null;
  },
): DialogBehaviour {
  let opener: Focusable | null = null;
  let wanted = false; // what React wants: open between open() and close()
  const onCancelEvent = (event: DialogEvent) => {
    event.preventDefault(); // the React state decides when it closes
    if (!options.isBusy()) options.onCancel();
  };
  const onCloseEvent = () => {
    // our own close(), or a late "close" from it after the dialog was opened again: nothing to do
    if (!wanted || dialog.open) return;
    if (options.isBusy()) {
      dialog.showModal(); // closed by the browser while the action is sent: it stays
      options.busyFocus?.()?.focus(); // back on the busy confirm button (re-review low 7)
      return;
    }
    wanted = false;
    giveBack();
    options.onCancel();
  };
  dialog.addEventListener("cancel", onCancelEvent);
  dialog.addEventListener("close", onCloseEvent);

  function giveBack(): void {
    const target = opener && opener.isConnected !== false ? opener : (options.fallback?.() ?? null);
    opener = null;
    target?.focus();
  }

  function shut(): void {
    wanted = false;
    if (!dialog.open) return;
    dialog.close();
    giveBack();
  }

  return {
    open(first, from) {
      opener = from;
      wanted = true;
      if (!dialog.open) dialog.showModal();
      first?.focus();
    },
    close: shut,
    dispose() {
      dialog.removeEventListener("cancel", onCancelEvent);
      dialog.removeEventListener("close", onCloseEvent);
      shut();
    },
  };
}
