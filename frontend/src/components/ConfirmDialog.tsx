import { LoaderCircle, type LucideIcon, X } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { Alert } from "./Alert";
import { type DialogBehaviour, dialogBehaviour, type Focusable } from "./dialog";

export interface QueryRoot {
  querySelector(selectors: string): Element | null;
}

/**
 * Where the focus goes when the dialog closes and the button that opened it is gone (a removed store's Remove): the
 * caller's own target when it gives one and it is there, otherwise the screen's focus target or its h1 (the default).
 */
export function confirmFallback(custom: (() => Focusable | null) | undefined, root: QueryRoot): Focusable | null {
  return custom?.() ?? (root.querySelector("[data-nav-focus], h1") as HTMLElement | null);
}

/**
 * ConfirmDialog (05 section 5): what will change, and whether it can be undone, before an action that can't be taken
 * back from the page (Install, Roll back, Reset access token). The native <dialog> opened with showModal(): the
 * browser traps the focus and makes the page inert; Esc is Cancel; the focus goes back to the opener (dialog.ts).
 * A destructive action has the danger button and starts on Cancel.
 */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  ConfirmIcon,
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  error = null,
  fallbackFocus,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  ConfirmIcon?: LucideIcon;
  cancelLabel?: string;
  danger?: boolean;
  /** The confirmed action is being sent: Esc and the buttons wait. */
  busy?: boolean;
  /** Why the action failed, shown inside the dialog (role="alert"). */
  error?: string | null;
  /** Where the focus goes if the opener is gone when the dialog closes; default: the screen's focus target or h1. */
  fallbackFocus?: () => Focusable | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const id = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const confirm = useRef<HTMLButtonElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const behaviour = useRef<DialogBehaviour | null>(null);
  const latest = useRef({ onCancel, busy, fallbackFocus });
  latest.current = { onCancel, busy, fallbackFocus };
  const shown = useRef(false); // what the dialog was last told: open or closed

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    const made = dialogBehaviour(element, {
      onCancel: () => latest.current.onCancel(),
      isBusy: () => latest.current.busy,
      fallback: () => confirmFallback(latest.current.fallbackFocus, document),
      busyFocus: () => confirm.current,
    });
    behaviour.current = made;
    return () => {
      behaviour.current = null;
      shown.current = false;
      made.dispose();
    };
  }, []);

  // Open and close only on a change of `open` (review item 17): a change of `danger` while open moves nothing.
  const startOnCancel = useRef(danger);
  startOnCancel.current = danger;
  useEffect(() => {
    const made = behaviour.current;
    if (!made || open === shown.current) return;
    shown.current = open;
    if (open) {
      const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      made.open(startOnCancel.current ? cancel.current : confirm.current, opener);
    } else made.close();
  }, [open]);

  const wait = () => {
    if (!busy) onCancel();
  };
  return (
    <dialog
      ref={dialog}
      className="confirm-dialog"
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-body`}
      aria-busy={busy}
    >
      <div className="confirm-dialog__inner">
        <div className="confirm-dialog__head">
          <h2 className="confirm-dialog__title num" id={`${id}-title`}>
            {title}
          </h2>
          <button type="button" className="btn is-ghost is-icon" aria-label="Close" onClick={wait}>
            <X className="icon" />
          </button>
        </div>
        <div className="confirm-dialog__body" id={`${id}-body`}>
          {children}
          {error ? <Alert tone="danger" title={error} /> : null}
        </div>
        <div className="confirm-dialog__foot">
          <button ref={cancel} type="button" className="btn" onClick={wait} aria-disabled={busy || undefined}>
            {cancelLabel}
          </button>
          <button
            ref={confirm}
            type="button"
            className={`btn ${danger ? "is-danger" : "is-primary"}`}
            aria-disabled={busy || undefined}
            onClick={() => {
              if (!busy) onConfirm();
            }}
          >
            {busy ? (
              <LoaderCircle className="icon is-spinning" aria-hidden="true" />
            ) : ConfirmIcon ? (
              <ConfirmIcon className="icon" aria-hidden="true" />
            ) : null}
            {confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
