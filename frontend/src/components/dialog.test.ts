// ConfirmDialog's keyboard behaviour (05 section 5; WAI-ARIA dialog pattern), with a fake <dialog>: opened modally
// (the browser's own focus trap), the first focus on Cancel for a destructive action, Esc is Cancel (and waits while
// the action is sent), and the focus goes back to the button that opened it.
import { describe, expect, it, vi } from "vitest";
import { type DialogElement, dialogBehaviour, type Focusable } from "./dialog";

type CancelListener = (event: { preventDefault(): void }) => void;

function fakeDialog() {
  const listeners = new Set<CancelListener>();
  const dialog = {
    open: false,
    showModal: vi.fn(() => {
      dialog.open = true;
    }),
    close: vi.fn(() => {
      dialog.open = false;
    }),
    addEventListener: (_type: "cancel", listener: CancelListener) => listeners.add(listener),
    removeEventListener: (_type: "cancel", listener: CancelListener) => listeners.delete(listener),
    /** What the browser does on Esc while a modal dialog is open: a cancelable "cancel" event. */
    pressEscape() {
      const event = { defaultPrevented: false, preventDefault: () => (event.defaultPrevented = true) };
      for (const listener of listeners) listener(event);
      if (!event.defaultPrevented) dialog.open = false;
      return event;
    },
    listeners,
  };
  return dialog satisfies DialogElement & Record<string, unknown>;
}

function focusable(name: string, log: string[], connected = true): Focusable {
  return { focus: () => log.push(name), isConnected: connected };
}

describe("dialogBehaviour", () => {
  it("opens modally and focuses the first control it is given", () => {
    const dialog = fakeDialog();
    const log: string[] = [];
    const behaviour = dialogBehaviour(dialog, { onCancel: vi.fn(), isBusy: () => false });
    behaviour.open(focusable("cancel", log), focusable("opener", log));
    expect(dialog.showModal).toHaveBeenCalledTimes(1);
    expect(dialog.open).toBe(true);
    expect(log).toEqual(["cancel"]);
  });

  it("Esc is the owner's Cancel: the event is held and onCancel decides", () => {
    const dialog = fakeDialog();
    const onCancel = vi.fn();
    const behaviour = dialogBehaviour(dialog, { onCancel, isBusy: () => false });
    behaviour.open(null, null);
    const event = dialog.pressEscape();
    expect(event.defaultPrevented).toBe(true);
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(dialog.open).toBe(true); // still open until the React state closes it
  });

  it("Esc does nothing while the confirmed action is being sent", () => {
    const dialog = fakeDialog();
    const onCancel = vi.fn();
    let busy = true;
    const behaviour = dialogBehaviour(dialog, { onCancel, isBusy: () => busy });
    behaviour.open(null, null);
    dialog.pressEscape();
    expect(onCancel).not.toHaveBeenCalled();
    expect(dialog.open).toBe(true);
    busy = false;
    dialog.pressEscape();
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("closing gives the focus back to the opener", () => {
    const dialog = fakeDialog();
    const log: string[] = [];
    const behaviour = dialogBehaviour(dialog, { onCancel: vi.fn(), isBusy: () => false });
    behaviour.open(focusable("confirm", log), focusable("opener", log));
    behaviour.close();
    expect(dialog.close).toHaveBeenCalledTimes(1);
    expect(log).toEqual(["confirm", "opener"]);
    behaviour.close(); // already closed: nothing more
    expect(dialog.close).toHaveBeenCalledTimes(1);
    expect(log).toEqual(["confirm", "opener"]);
  });

  it("an opener that left the page hands the focus to the fallback (the page's title)", () => {
    const dialog = fakeDialog();
    const log: string[] = [];
    const behaviour = dialogBehaviour(dialog, {
      onCancel: vi.fn(),
      isBusy: () => false,
      fallback: () => focusable("title", log),
    });
    behaviour.open(null, focusable("opener", log, false));
    behaviour.close();
    expect(log).toEqual(["title"]);
  });

  it("dispose stops listening for Esc and closes an open dialog", () => {
    const dialog = fakeDialog();
    const log: string[] = [];
    const onCancel = vi.fn();
    const behaviour = dialogBehaviour(dialog, { onCancel, isBusy: () => false });
    behaviour.open(null, focusable("opener", log));
    behaviour.dispose();
    expect(dialog.listeners.size).toBe(0);
    expect(dialog.open).toBe(false);
    expect(log).toEqual(["opener"]);
  });
});
