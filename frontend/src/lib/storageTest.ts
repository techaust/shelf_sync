// The tab's Storage Test (SET-02, ERR-03): running, its last answer, or why it was refused. One store for the whole
// tab, kept out of React like storeTests.ts, so leaving Settings › Storage while a test runs and coming back shows the
// same progress, and a second click while it runs sends nothing (the server answers `busy` to a second one anyway).
// The words are the screen's (screens/settings/storageTestModel.ts); this file only keeps what happened.

import { useSyncExternalStore } from "react";
import type { StorageTest } from "../api/storage";

export interface StorageTestEntry {
  running: boolean;
  /** The last answer this tab got (200, passed or failed). */
  result: StorageTest | null;
  /** The saved region the test ran against: `wrong_region` names it, and a later save may change it. */
  region: string;
  /** A refused or unanswered test (ApiError, ApiUnreachableError, …), turned into words by the screen. */
  failure: unknown;
  /** The settings or keys changed while this test ran: its answer is about what was saved before (T2 review 1). */
  stale: boolean;
}

export const STORAGE_TEST_IDLE: StorageTestEntry = {
  running: false,
  result: null,
  region: "",
  failure: null,
  stale: false,
};

export interface StorageTestRun {
  subscribe(listener: () => void): () => void;
  get(): StorageTestEntry;
  /** Runs `send` unless a test is already running; `region` is the saved region it tests. */
  run(region: string, send: () => Promise<StorageTest>): Promise<void>;
  /**
   * The settings or keys changed, so the last answer no longer says anything about them. A finished answer is dropped;
   * a running test is marked stale, so its answer lands with a note instead of passing for the new settings.
   */
  forget(): void;
}

export function createStorageTestRun(): StorageTestRun {
  let entry: StorageTestEntry = STORAGE_TEST_IDLE;
  const listeners = new Set<() => void>();
  const set = (next: StorageTestEntry) => {
    entry = next;
    for (const listener of [...listeners]) listener();
  };
  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    get: () => entry,
    async run(region, send) {
      if (entry.running) return;
      set({ running: true, result: null, region, failure: null, stale: false });
      try {
        const result = await send();
        set({ running: false, result, region, failure: null, stale: entry.stale });
      } catch (failure) {
        set({ running: false, result: null, region, failure, stale: entry.stale });
      }
    },
    forget() {
      if (entry.running) {
        if (!entry.stale) set({ ...entry, stale: true });
        return;
      }
      if (entry.result === null && entry.failure === null) return;
      set(STORAGE_TEST_IDLE);
    },
  };
}

/** The tab's one Storage Test. */
export const storageTestRun = createStorageTestRun();

export function useStorageTest(run: StorageTestRun = storageTestRun): StorageTestEntry {
  return useSyncExternalStore(run.subscribe, run.get, run.get);
}
