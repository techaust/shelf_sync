// After an accepted Install or Roll back (202), ShelfSync closes and the switcher starts the other version, then opens
// a new signed-in tab (SYS-06, SYS-07). Sessions live in memory, so this tab can't stay signed in across the restart.
// Every few seconds the page asks GET /api/health (no session needed), each question ended after `timeoutMs`; when
// ShelfSync answers, GET /api/session/status says which copy it is:
// - 401: a new copy (any version, also a quick restart that brought the old version back) → "new_tab": this tab
//   stops and says a new signed-in tab has opened;
// - 204: the copy this tab signed in to is still running. Once it no longer reports a switch under way (the switch
//   changed nothing), → "reload", and the page shows the result. While it does, the asking goes on.
// After `lateAfterMs` the page says so once (onLate, its own timer) and keeps asking. Timers come from `clock`, so the
// tests use fake ones.

import type { SessionCheck } from "../api/settings";

export interface HealthAnswer {
  app: string;
  version: string;
}

export interface Clock {
  setTimeout(callback: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export type RestartOutcome = "reload" | "new_tab";

export interface RestartPollOptions {
  target: string;
  /** ShelfSync's answer; rejects (or answers something else) while it is gone. */
  health: (signal: AbortSignal) => Promise<HealthAnswer>;
  session: (signal: AbortSignal) => Promise<SessionCheck>;
  /** True while the copy that answers still reports a switch under way (GET /api/updates `busy`). */
  stillSwitching: (signal: AbortSignal) => Promise<boolean>;
  onBack: (outcome: RestartOutcome) => void;
  onLate?: () => void;
  clock?: Clock;
  everyMs?: number;
  lateAfterMs?: number;
  timeoutMs?: number;
}

export const POLL_EVERY_MS = 2000;
export const LATE_AFTER_MS = 3 * 60 * 1000;
export const ASK_TIMEOUT_MS = 3000;

export const realClock: Clock = {
  setTimeout: (callback, ms) => globalThis.setTimeout(callback, ms),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/** Starts asking; returns a function that stops it. */
export function pollForRestart(options: RestartPollOptions): () => void {
  const clock = options.clock ?? realClock;
  const every = options.everyMs ?? POLL_EVERY_MS;
  const timeout = options.timeoutMs ?? ASK_TIMEOUT_MS;
  let stopped = false;
  let next: unknown = null;
  const late = clock.setTimeout(() => {
    if (!stopped) options.onLate?.();
  }, options.lateAfterMs ?? LATE_AFTER_MS);

  function stop(): void {
    stopped = true;
    if (next !== null) clock.clearTimeout(next);
    clock.clearTimeout(late);
  }

  /** One question with its own time limit; a question that runs out counts as no answer. */
  async function ask<T>(question: (signal: AbortSignal) => Promise<T>): Promise<T | null> {
    const controller = new AbortController();
    const timer = clock.setTimeout(() => controller.abort(), timeout);
    try {
      return await question(controller.signal);
    } catch {
      return null;
    } finally {
      clock.clearTimeout(timer);
    }
  }

  function finish(outcome: RestartOutcome): void {
    stop();
    options.onBack(outcome);
  }

  async function tick(): Promise<void> {
    if (stopped) return;
    const answer = await ask(options.health);
    if (stopped) return;
    if (answer && answer.app === "shelfsync" && typeof answer.version === "string") {
      const session = await ask(options.session);
      if (stopped) return;
      if (session === "signed_out") return finish("new_tab");
      if (session === "signed_in") {
        if (answer.version === options.target) return finish("reload");
        const switching = await ask(options.stillSwitching);
        if (stopped) return;
        if (switching === false) return finish("reload");
      }
    }
    next = clock.setTimeout(tick, every);
  }

  next = clock.setTimeout(tick, every);
  return stop;
}
