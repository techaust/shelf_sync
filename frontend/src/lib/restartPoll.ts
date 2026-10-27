// After an accepted Install or Roll back (202), ShelfSync closes and the switcher starts the other version (SYS-06,
// SYS-07). The page asks GET /api/health (no session needed) every few seconds and reloads when:
// - the version it switched to answers; or
// - ShelfSync answers again after it was seen gone, with any version (the switch kept the old one, or changed
//   nothing): after the reload the page shows the last switch's result from GET /api/updates.
// An answer from the old copy before it closed is not a restart, so it is never reloaded on. After `lateAfterMs` the
// page says so once (onLate) and keeps asking. Timers come from `clock`, so the tests use a fake one.

export interface HealthAnswer {
  app: string;
  version: string;
}

export interface Clock {
  setTimeout(callback: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
  now(): number;
}

export interface RestartPollOptions {
  target: string;
  /** Resolves with ShelfSync's answer; rejects (or answers something else) while it is gone. */
  health: () => Promise<HealthAnswer>;
  onBack: () => void;
  onLate?: () => void;
  clock?: Clock;
  everyMs?: number;
  lateAfterMs?: number;
}

export const POLL_EVERY_MS = 2000;
export const LATE_AFTER_MS = 3 * 60 * 1000;

const realClock: Clock = {
  setTimeout: (callback, ms) => globalThis.setTimeout(callback, ms),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
  now: () => Date.now(),
};

/** Starts asking; returns a function that stops it. */
export function pollForRestart(options: RestartPollOptions): () => void {
  const clock = options.clock ?? realClock;
  const every = options.everyMs ?? POLL_EVERY_MS;
  const lateAfter = options.lateAfterMs ?? LATE_AFTER_MS;
  const started = clock.now();
  let stopped = false;
  let seenGone = false;
  let saidLate = false;
  let handle: unknown = null;

  const schedule = () => {
    if (!stopped) handle = clock.setTimeout(tick, every);
  };

  async function tick(): Promise<void> {
    if (stopped) return;
    let answer: HealthAnswer | null = null;
    try {
      const body = await options.health();
      answer = body && body.app === "shelfsync" && typeof body.version === "string" ? body : null;
    } catch {
      answer = null;
    }
    if (stopped) return;
    if (answer === null) seenGone = true;
    else if (answer.version === options.target || seenGone) {
      stopped = true;
      options.onBack();
      return;
    }
    if (!saidLate && clock.now() - started >= lateAfter) {
      saidLate = true;
      options.onLate?.();
    }
    schedule();
  }

  schedule();
  return () => {
    stopped = true;
    if (handle !== null) clock.clearTimeout(handle);
  };
}
