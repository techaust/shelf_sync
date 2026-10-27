// UI-SET (SYS-06, SYS-07): Install and Roll back after the dialog, as a store outside the page (review item 8), with
// fake answers and fake timers: a 202 or no answer → the restart panel; no answer for 3 minutes → the panel anyway;
// confirm_required → ask again; a 409 → its 13 line; the poll's outcome → reload or "a new tab opened".
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, ApiUnreachableError } from "../../api/client";
import type { Clock } from "../../lib/restartPoll";
import { POLL_EVERY_MS } from "../../lib/restartPoll";
import { createSwitchStore, type PollAnswers, SEND_WAIT_MS } from "./switchStore";

const clock: Clock = {
  setTimeout: (callback, ms) => setTimeout(callback, ms),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};
const gone = () => Promise.reject(new Error("no answer"));
const silentPoll: PollAnswers = { health: gone, session: gone, stillSwitching: gone };

describe("the switch store", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("preparing while the install request runs, then the restart panel on 202", async () => {
    const store = createSwitchStore({ reload: vi.fn(), clock });
    let accept: () => void = () => undefined;
    const send = () =>
      new Promise<void>((resolve) => {
        accept = resolve;
      });
    const running = store.run("preparing", "0.3.0", send, silentPoll);
    expect(store.get().phase).toEqual({ kind: "preparing", version: "0.3.0" });
    accept();
    await expect(running).resolves.toBe("restarting");
    expect(store.get().phase).toEqual({ kind: "restarting", version: "0.3.0", late: false, back: false });
    store.reset();
  });

  it("no answer at all is taken as restarting (ShelfSync may close before it answers)", async () => {
    const store = createSwitchStore({ reload: vi.fn(), clock });
    const outcome = await store.run(
      "rolling_back",
      "0.1.4",
      () => Promise.reject(new ApiUnreachableError("POST", "/api/updates/rollback")),
      silentPoll,
    );
    expect(outcome).toBe("restarting");
    expect(store.get().phase.kind).toBe("restarting");
    store.reset();
  });

  it("an install request unanswered for 3 minutes falls through to the restart panel", async () => {
    const store = createSwitchStore({ reload: vi.fn(), clock });
    const running = store.run("preparing", "0.3.0", () => new Promise(() => undefined), silentPoll);
    await vi.advanceTimersByTimeAsync(SEND_WAIT_MS - 1);
    expect(store.get().phase.kind).toBe("preparing");
    await vi.advanceTimersByTimeAsync(1);
    expect(store.get().phase.kind).toBe("restarting");
    void running;
    store.reset();
  });

  it("confirm_required: back to idle, and the page asks again", async () => {
    const store = createSwitchStore({ reload: vi.fn(), clock });
    const outcome = await store.run(
      "rolling_back",
      "0.1.4",
      () => Promise.reject(new ApiError("POST", "/api/updates/rollback", 422, "confirm_required")),
      silentPoll,
    );
    expect(outcome).toBe("confirm_required");
    expect(store.get()).toEqual({ phase: { kind: "idle" }, error: null });
  });

  it("a 409 gives its 13 line; busy is information, the rest danger", async () => {
    const store = createSwitchStore({ reload: vi.fn(), clock });
    const refuse = (code: "files_changed" | "busy") => () =>
      Promise.reject(new ApiError("POST", "/api/updates/install", 409, code));
    await expect(store.run("preparing", "0.3.0", refuse("files_changed"), silentPoll)).resolves.toBe("refused");
    expect(store.get()).toEqual({
      phase: { kind: "idle" },
      error: { tone: "danger", text: "The files of that version changed on disk, so it was refused." },
    });
    await store.run("preparing", "0.3.0", refuse("busy"), silentPoll);
    expect(store.get().error).toEqual({ tone: "info", text: "An update is already under way." });
    store.clearError();
    expect(store.get().error).toBeNull();
  });

  it("the poll's new_tab keeps the panel, now saying a new tab opened; reload reloads", async () => {
    const reload = vi.fn();
    const store = createSwitchStore({ reload, clock });
    const newCopy: PollAnswers = {
      health: async () => ({ app: "shelfsync", version: "0.3.0" }),
      session: async () => "signed_out",
      stillSwitching: async () => false,
    };
    await store.run("preparing", "0.3.0", async () => undefined, newCopy);
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(store.get().phase).toEqual({ kind: "restarting", version: "0.3.0", late: false, back: true });
    expect(reload).not.toHaveBeenCalled();

    const same = createSwitchStore({ reload, clock });
    const oldCopy: PollAnswers = {
      ...newCopy,
      health: async () => ({ app: "shelfsync", version: "0.2.0" }),
      session: async () => "signed_in",
    };
    await same.run("preparing", "0.3.0", async () => undefined, oldCopy);
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("the phase lives in the store: a page that subscribes later sees it, and a second run waits", async () => {
    const store = createSwitchStore({ reload: vi.fn(), clock });
    await store.run("preparing", "0.3.0", async () => undefined, silentPoll);
    const listener = vi.fn();
    store.subscribe(listener); // the page mounted again
    expect(store.get().phase.kind).toBe("restarting");
    await expect(store.run("rolling_back", "0.1.4", async () => undefined, silentPoll)).resolves.toBe("refused");
    expect(store.get().phase).toMatchObject({ kind: "restarting", version: "0.3.0" });
    store.reset();
    expect(listener).toHaveBeenCalled();
  });
});
