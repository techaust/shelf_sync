// UI-SET (SYS-06, SYS-07): after an accepted Install or Roll back the page waits for ShelfSync to come back and then
// reloads. Run on Vitest's fake timers: no real waiting, and every tick is counted.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type Clock, type HealthAnswer, LATE_AFTER_MS, POLL_EVERY_MS, pollForRestart } from "./restartPoll";

const fakeClock: Clock = {
  setTimeout: (callback, ms) => setTimeout(callback, ms),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
  now: () => Date.now(),
};

/** A health endpoint that answers from a script: a version, or "gone" (no answer). */
function scripted(steps: (string | "gone")[]) {
  let calls = 0;
  const health = vi.fn(async (): Promise<HealthAnswer> => {
    const step = steps[Math.min(calls, steps.length - 1)];
    calls += 1;
    if (step === "gone" || step === undefined) throw new Error("no answer");
    return { app: "shelfsync", version: step };
  });
  return health;
}

describe("pollForRestart", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("asks every two seconds and reloads when the new version answers", async () => {
    const health = scripted(["0.2.0", "gone", "gone", "0.3.0"]);
    const onBack = vi.fn();
    pollForRestart({ target: "0.3.0", health, onBack, clock: fakeClock });
    expect(health).not.toHaveBeenCalled(); // the first question waits one interval: the old copy is still closing
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(health).toHaveBeenCalledTimes(1);
    expect(onBack).not.toHaveBeenCalled(); // the old copy answering before it closed is not a restart
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 2);
    expect(onBack).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(health).toHaveBeenCalledTimes(4);
    expect(onBack).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 5);
    expect(health).toHaveBeenCalledTimes(4); // stopped after the reload
  });

  it("reloads when the new version answers straight away (the switch was quick)", async () => {
    const health = scripted(["0.3.0"]);
    const onBack = vi.fn();
    pollForRestart({ target: "0.3.0", health, onBack, clock: fakeClock });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("reloads when the old version is back after it was gone (kept_old, not_switched)", async () => {
    const health = scripted(["gone", "gone", "0.2.0"]);
    const onBack = vi.fn();
    pollForRestart({ target: "0.3.0", health, onBack, clock: fakeClock });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 2);
    expect(onBack).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("never reloads on the old copy while it has not gone away", async () => {
    const health = scripted(["0.2.0"]);
    const onBack = vi.fn();
    const stop = pollForRestart({ target: "0.3.0", health, onBack, clock: fakeClock });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 20);
    expect(health).toHaveBeenCalledTimes(20);
    expect(onBack).not.toHaveBeenCalled();
    stop();
  });

  it("an answer that isn't ShelfSync's counts as gone", async () => {
    let calls = 0;
    const health = vi.fn(async () => {
      calls += 1;
      return calls === 1 ? { app: "something-else", version: "9.9.9" } : { app: "shelfsync", version: "0.2.0" };
    });
    const onBack = vi.fn();
    pollForRestart({ target: "0.3.0", health, onBack, clock: fakeClock });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onBack).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onBack).toHaveBeenCalledTimes(1); // gone (a stranger), then ShelfSync again
  });

  it("says once that it is late, after three minutes, and keeps asking", async () => {
    const health = scripted(["gone"]);
    const onBack = vi.fn();
    const onLate = vi.fn();
    const stop = pollForRestart({ target: "0.3.0", health, onBack, onLate, clock: fakeClock });
    await vi.advanceTimersByTimeAsync(LATE_AFTER_MS - POLL_EVERY_MS);
    expect(onLate).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    expect(onLate).toHaveBeenCalledTimes(1);
    const asked = health.mock.calls.length;
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 10);
    expect(onLate).toHaveBeenCalledTimes(1);
    expect(health.mock.calls.length).toBe(asked + 10);
    stop();
  });

  it("stop() ends the asking, also while a question is out", async () => {
    let answer: (value: HealthAnswer) => void = () => undefined;
    const health = vi.fn(
      () =>
        new Promise<HealthAnswer>((resolve) => {
          answer = resolve;
        }),
    );
    const onBack = vi.fn();
    const stop = pollForRestart({ target: "0.3.0", health, onBack, clock: fakeClock });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);
    stop();
    answer({ app: "shelfsync", version: "0.3.0" });
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS * 3);
    expect(onBack).not.toHaveBeenCalled();
    expect(health).toHaveBeenCalledTimes(1);
  });
});
