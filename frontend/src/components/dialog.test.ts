// ConfirmDialog's keyboard behaviour (05 section 5; WAI-ARIA dialog pattern), with a fake <dialog>: opened modally
// (the browser's own focus trap), the first focus on Cancel for a destructive action, Esc is Cancel (and waits while
// the action is sent), and the focus goes back to the button that opened it.
import { describe, expect, it, vi } from "vitest";
import { type DialogElement, dialogBehaviour, type Focusable } from "./dialog";

type Listener = (event: { preventDefault(): void }) => void;
type EventName = "cancel" | "close";

/** A fake <dialog>. close() fires "close" as the browser does (here at once; in a browser a task later). */
function fakeDialog() {
  const listeners: Record<EventName, Set<Listener>> = { cancel: new Set(), close: new Set() };
  const fire = (type: EventName) => {
    const event = { defaultPrevented: false, preventDefault: () => (event.defaultPrevented = true) };
    for (const listener of [...listeners[type]]) listener(event);
    return event;
  };
  const dialog = {
    open: false,
    showModal: vi.fn(() => {
      dialog.open = true;
    }),
    close: vi.fn(() => {
      if (!dialog.open) return;
      dialog.open = false;
      fire("close");
    }),
    addEventListener: (type: EventName, listener: Listener) => listeners[type].add(listener),
    removeEventListener: (type: EventName, listener: Listener) => listeners[type].delete(listener),
    /** What the browser does on Esc while a modal dialog is open: a cancelable "cancel" event. */
    pressEscape() {
      const event = fire("cancel");
      if (!event.defaultPrevented) dialog.close();
      return event;
    },
    /** A second Esc in Chrome: the dialog closes even though "cancel" was prevented (its close watcher). */
    browserCloses() {
      fire("cancel");
      dialog.open = false;
      fire("close");
    },
    listeners: { size: () => listeners.cancel.size + listeners.close.size },
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
    expect(dialog.listeners.size()).toBe(0);
    expect(dialog.open).toBe(false);
    expect(log).toEqual(["opener"]);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("our own close never reports a Cancel", () => {
    const dialog = fakeDialog();
    const onCancel = vi.fn();
    const behaviour = dialogBehaviour(dialog, { onCancel, isBusy: () => false });
    behaviour.open(null, null);
    behaviour.close();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("a second Esc that closes the native dialog while the action is sent: it opens again", () => {
    const dialog = fakeDialog();
    const onCancel = vi.fn();
    const log: string[] = [];
    const behaviour = dialogBehaviour(dialog, {
      onCancel,
      isBusy: () => true,
      busyFocus: () => focusable("confirm (busy)", log),
    });
    behaviour.open(null, null);
    dialog.browserCloses();
    expect(dialog.open).toBe(true);
    expect(dialog.showModal).toHaveBeenCalledTimes(2);
    expect(onCancel).not.toHaveBeenCalled();
    expect(log).toEqual(["confirm (busy)"]); // the focus goes back on the busy confirm button
  });

  it("a browser close while nothing is sent: React is told (Cancel) and the focus goes back", () => {
    const dialog = fakeDialog();
    const log: string[] = [];
    const onCancel = vi.fn();
    const behaviour = dialogBehaviour(dialog, { onCancel, isBusy: () => false });
    behaviour.open(null, focusable("opener", log));
    dialog.browserCloses();
    expect(dialog.open).toBe(false);
    expect(onCancel).toHaveBeenCalled();
    expect(log).toEqual(["opener"]);
    behaviour.close(); // React then closes it too: nothing more happens
    expect(log).toEqual(["opener"]);
  });
});
