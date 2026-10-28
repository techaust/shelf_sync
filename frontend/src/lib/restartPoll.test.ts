// UI-SET (SYS-06, SYS-07): after an accepted Install or Roll back the page waits for ShelfSync to come back. A new
// copy (the session check answers 401) means the switcher opened a new signed-in tab; the old copy still running
// (204) reloads once it no longer reports a switch. Each question has its own time limit; "late" has its own timer.
// Run on Vitest's fake timers: no real waiting.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionCheck } from "../api/settings";
import {
  ASK_TIMEOUT_MS,
  type Clock,
  type HealthAnswer,
  LATE_AFTER_MS,
  POLL_EVERY_MS,
  pollForRestart,
  type RestartPollOptions,
} from "./restartPoll";

const fakeClock: Clock = {
  setTimeout: (callback, ms) => setTimeout(callback, ms),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

type Step = string | "gone" | "hang";

/** A scripted answer per question: a value, "gone" (no answer) or "hang" (never answers until aborted). */
function scripted<T>(steps: (T | "gone" | "hang")[]) {
  let calls = 0;
  return vi.fn((signal: AbortSignal): Promise<T> => {
    const step = steps[Math.min(calls, steps.length - 1)];
    calls += 1;
    if (step === "gone" || step === undefined) return Promise.reject(new Error("no answer"));
    if (step === "hang")
      return new Promise<T>((_resolve, reject) => signal.addEventListener("abort", () => reject(new Error("aborted"))));
    return Promise.resolve(step as T);
  });
}
const healthOf = (steps: Step[]) =>
  scripted<HealthAnswer>(steps.map((s) => (s === "gone" || s === "hang" ? s : { app: "shelfsync", version: s })));

function start(over: Partial<RestartPollOptions> & Pick<RestartPollOptions, "health">) {
  const onBack = vi.fn();
  const onLate = vi.fn();
  const options: RestartPollOptions = {
    target: "0.3.0",
    session: scripted<SessionCheck>(["signed_out"]),
    stillSwitching: scripted<boolean>([true]),
    onBack,
    onLate,
    clock: fakeClock,
    ...over,
  };
  const stop = pollForRestart(options);
  return { onBack, onLate, stop, options };
}

describe("pollForRestart", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("a new copy answers (401): new_tab, and the asking stops", async () => {
    const health = healthOf(["gone", "gone", "0.3.0"]);
    const { onBack } = start({ health });
    expect(health).not.toHaveBeenCalled(); // the first question waits one interval
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 2);
    expect(onBack).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onBack).toHaveBeenCalledWith("new_tab");
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 5);
    expect(health).toHaveBeenCalledTimes(3);
  });

  it("a quick restart that brought the old version back is noticed (401 on the first answer)", async () => {
    const health = healthOf(["0.2.0"]);
    const { onBack } = start({ health });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onBack).toHaveBeenCalledWith("new_tab");
  });

  it("the old copy still running (204) waits while it reports the switch, then reloads (not_switched)", async () => {
    const health = healthOf(["0.2.0"]);
    const stillSwitching = scripted<boolean>([true, true, false]);
    const { onBack } = start({ health, session: scripted<SessionCheck>(["signed_in"]), stillSwitching });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 2);
    expect(onBack).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onBack).toHaveBeenCalledWith("reload");
    expect(stillSwitching).toHaveBeenCalledTimes(3);
  });

  it("the target version answering with this tab's sign-in (the new tab signed in; shared cookie): running", async () => {
    const health = healthOf(["gone", "0.3.0"]);
    const stillSwitching = scripted<boolean>([false]);
    const { onBack } = start({ health, session: scripted<SessionCheck>(["signed_in"]), stillSwitching });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 2);
    expect(onBack).toHaveBeenCalledWith("running");
    expect(stillSwitching).not.toHaveBeenCalled();
  });

  it("mustSeeGone: the old copy, not busy, counts only after ShelfSync was seen gone once", async () => {
    const health = healthOf(["0.2.0", "0.2.0", "gone", "0.2.0"]);
    const { onBack } = start({
      health,
      session: scripted<SessionCheck>(["signed_in"]),
      stillSwitching: scripted<boolean>([false]),
      mustSeeGone: true,
    });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 3);
    expect(onBack).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onBack).toHaveBeenCalledWith("reload");
  });

  it("an unknown session answer, or a stranger on the port, counts as no answer", async () => {
    let calls = 0;
    const health = vi.fn(async () => {
      calls += 1;
      return calls === 1 ? { app: "something-else", version: "9.9.9" } : { app: "shelfsync", version: "0.3.0" };
    });
    const session = scripted<SessionCheck>(["unknown", "signed_out"]);
    const { onBack } = start({ health, session });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS); // a stranger: the session isn't even asked
    expect(session).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS); // ShelfSync, session unknown: ask again
    expect(onBack).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onBack).toHaveBeenCalledWith("new_tab");
  });

  it("each question is ended after its time limit, and the next one still comes", async () => {
    const health = healthOf(["hang", "0.3.0"]);
    const { onBack } = start({ health });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    const signal = health.mock.calls[0]?.[0] as AbortSignal;
    expect(signal.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(ASK_TIMEOUT_MS);
    expect(signal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onBack).toHaveBeenCalledWith("new_tab");
  });

  it("says once that it is late, on its own timer (even while a question hangs), and keeps asking", async () => {
    const health = healthOf(["gone"]);
    const { onLate, onBack, stop } = start({ health });
    await vi.advanceTimersByTimeAsync(LATE_AFTER_MS - 1);
    expect(onLate).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(onLate).toHaveBeenCalledTimes(1);
    const asked = health.mock.calls.length;
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 10);
    expect(onLate).toHaveBeenCalledTimes(1);
    expect(health.mock.calls.length).toBe(asked + 10);
    expect(onBack).not.toHaveBeenCalled();
    stop();
  });

  it("stop() ends the asking and the late timer, also while a question is out", async () => {
    let answer: (value: HealthAnswer) => void = () => undefined;
    const health = vi.fn(
      () =>
        new Promise<HealthAnswer>((resolve) => {
          answer = resolve;
        }),
    );
    const { onBack, onLate, stop } = start({ health });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    stop();
    answer({ app: "shelfsync", version: "0.3.0" });
    await vi.advanceTimersByTimeAsync(LATE_AFTER_MS);
    expect(onBack).not.toHaveBeenCalled();
    expect(onLate).not.toHaveBeenCalled();
    expect(health).toHaveBeenCalledTimes(1);
  });
});
