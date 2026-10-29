// The tab's running and finished Test connections, by store id (SET-01, ERR-01). One store for the whole tab, so the
// card on Settings › Stores and the health popover in the app bar show the same progress, and a second click on
// either does nothing while a test runs (the server answers `busy` to a second one anyway). Kept out of React so it is
// tested with fake sends (storeTests.test.ts).

import { useSyncExternalStore } from "react";
import type { StoreTest } from "../api/stores";
import { testError } from "./storeHealth";

export interface TestEntry {
  running: boolean;
  /** The last answer this tab got (it holds `detail` and `warning`, which the saved health doesn't). */
  result: StoreTest | null;
  /** A refused or unanswered test, in 13's words. */
  error: { text: string; tone: "danger" | "info" } | null;
}

const IDLE: TestEntry = { running: false, result: null, error: null };

export interface StoreTests {
  subscribe(listener: () => void): () => void;
  get(): ReadonlyMap<number, TestEntry>;
  entry(id: number): TestEntry;
  /** Runs `send` unless a test of this store is already running; `after` runs once it has answered (or not). */
  run(id: number, send: () => Promise<StoreTest>, after?: () => unknown): Promise<void>;
  /** Forgets a store's last result (its keys or address changed, so it no longer says anything). */
  forget(id: number): void;
}

export function createStoreTests(): StoreTests {
  let entries: ReadonlyMap<number, TestEntry> = new Map();
  const listeners = new Set<() => void>();
  const set = (id: number, entry: TestEntry) => {
    const next = new Map(entries);
    next.set(id, entry);
    entries = next;
    for (const listener of [...listeners]) listener();
  };
  const entry = (id: number) => entries.get(id) ?? IDLE;
  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    get: () => entries,
    entry,
    async run(id, send, after) {
      if (entry(id).running) return;
      set(id, { running: true, result: null, error: null });
      try {
        const result = await send();
        set(id, { running: false, result, error: null });
      } catch (failure) {
        set(id, { running: false, result: null, error: testError(failure) });
      }
      await after?.();
    },
    forget(id) {
      if (!entries.has(id) || entry(id).running) return;
      const next = new Map(entries);
      next.delete(id);
      entries = next;
      for (const listener of [...listeners]) listener();
    },
  };
}

/** The tab's one store of tests. */
export const storeTests = createStoreTests();

export function useStoreTest(id: number): TestEntry {
  const entries = useSyncExternalStore(storeTests.subscribe, storeTests.get, storeTests.get);
  return entries.get(id) ?? IDLE;
}
