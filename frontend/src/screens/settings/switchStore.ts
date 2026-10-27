// Install and Roll back, after the dialog (SYS-06, SYS-07). The switch's phase and its restart poll live in this
// module, not in the page, so leaving Settings › Updates (or coming back to it) never stops them (review item 8); the
// page shows what the store holds. Every step is a plain function, tested with fake answers and fake timers.

import { ApiError, ApiUnreachableError } from "../../api/client";
import type { SessionCheck } from "../../api/settings";
import { type Clock, type HealthAnswer, pollForRestart, realClock } from "../../lib/restartPoll";
import type { Phase } from "./updatesModel";
import { updatesActionError, updatesActionTone } from "./wording";

/** How long an Install or Roll back request may stay unanswered before the page shows the restart panel anyway:
 *  the server hashes the whole version folder first, but never for minutes (review item 18). */
export const SEND_WAIT_MS = 3 * 60 * 1000;

export interface SwitchLine {
  tone: "info" | "danger";
  text: string;
}

export interface SwitchState {
  phase: Phase;
  error: SwitchLine | null;
}

export interface PollAnswers {
  health: (signal: AbortSignal) => Promise<HealthAnswer>;
  session: (signal: AbortSignal) => Promise<SessionCheck>;
  stillSwitching: (signal: AbortSignal) => Promise<boolean>;
}

export type SwitchOutcome = "restarting" | "confirm_required" | "refused";

export function createSwitchStore(deps: { reload: () => void; clock?: Clock }) {
  const clock = deps.clock ?? realClock;
  let state: SwitchState = { phase: { kind: "idle" }, error: null };
  let stopPoll: (() => void) | null = null;
  const listeners = new Set<() => void>();
  /** Read through a function: `state` changes inside awaits, which TypeScript's narrowing can't see. */
  const phaseNow = (): Phase => state.phase;
  const set = (next: SwitchState) => {
    state = next;
    for (const listener of listeners) listener();
  };

  function restart(version: string, answers: PollAnswers): void {
    if (state.phase.kind === "restarting") return;
    set({ phase: { kind: "restarting", version, late: false, back: false }, error: null });
    stopPoll = pollForRestart({
      target: version,
      ...answers,
      clock,
      onLate: () => {
        if (state.phase.kind === "restarting") set({ ...state, phase: { ...state.phase, late: true } });
      },
      onBack: (outcome) => {
        stopPoll = null;
        if (outcome === "reload") deps.reload();
        else if (state.phase.kind === "restarting") set({ ...state, phase: { ...state.phase, back: true } });
      },
    });
  }

  return {
    get: (): SwitchState => state,
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    clearError(): void {
      if (state.error) set({ ...state, error: null });
    },

    /**
     * Sends the confirmed Install ("preparing") or Roll back ("rolling_back"). A 202, no answer at all (ShelfSync may
     * close before it answers), or no answer for SEND_WAIT_MS: the restart panel and its poll. A refusal: back to
     * idle with its 13 line, or "confirm_required" (the database changed since the page was loaded: ask again).
     */
    async run(
      kind: "preparing" | "rolling_back",
      version: string,
      send: () => Promise<unknown>,
      answers: PollAnswers,
    ): Promise<SwitchOutcome> {
      if (state.phase.kind !== "idle") return "refused";
      set({ phase: { kind, version }, error: null });
      const waited = clock.setTimeout(() => restart(version, answers), SEND_WAIT_MS);
      try {
        await send();
        restart(version, answers);
        return "restarting";
      } catch (failure) {
        if (phaseNow().kind === "restarting") return "restarting"; // the wait ran out first: the panel stays
        if (failure instanceof ApiUnreachableError) {
          restart(version, answers);
          return "restarting";
        }
        const code = failure instanceof ApiError ? failure.code : null;
        if (code === "confirm_required") {
          set({ phase: { kind: "idle" }, error: null });
          return "confirm_required";
        }
        const status = failure instanceof ApiError ? failure.status : null;
        set({
          phase: { kind: "idle" },
          error: { tone: updatesActionTone(code), text: updatesActionError(code, status) },
        });
        return "refused";
      } finally {
        clock.clearTimeout(waited);
      }
    },

    /** Tests only: back to the start, the poll stopped. */
    reset(): void {
      stopPoll?.();
      stopPoll = null;
      set({ phase: { kind: "idle" }, error: null });
    },
  };
}

export type SwitchStore = ReturnType<typeof createSwitchStore>;

/** The tab's one switch. */
export const switchStore: SwitchStore = createSwitchStore({ reload: () => window.location.reload() });
