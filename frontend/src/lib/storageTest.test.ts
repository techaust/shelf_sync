// SET-02: the tab's one Storage Test, with fake sends. One run at a time (a second click while it runs sends nothing),
// the region it ran against kept with its answer, a refusal kept as it was thrown, and forget() never mid-run.
import { describe, expect, it, vi } from "vitest";
import type { StorageTest } from "../api/storage";
import { createStorageTestRun, STORAGE_TEST_IDLE } from "./storageTest";

const PASSED: StorageTest = {
  ok: true,
  tested_at: "2026-11-02T10:00:00Z",
  latency_ms: 412,
  steps: [],
  left_behind: null,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

describe("the tab's Storage Test", () => {
  it("starts idle, runs, keeps the answer and the region, and tells its listeners", async () => {
    const run = createStorageTestRun();
    const listener = vi.fn();
    run.subscribe(listener);
    expect(run.get()).toBe(STORAGE_TEST_IDLE);
    const sent = deferred<StorageTest>();
    const done = run.run("ap-south-1", () => sent.promise);
    expect(run.get()).toEqual({ running: true, result: null, region: "ap-south-1", failure: null });
    sent.resolve(PASSED);
    await done;
    expect(run.get()).toEqual({ running: false, result: PASSED, region: "ap-south-1", failure: null });
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("a second run while one runs sends nothing", async () => {
    const run = createStorageTestRun();
    const sent = deferred<StorageTest>();
    const first = vi.fn(() => sent.promise);
    const second = vi.fn(() => Promise.resolve(PASSED));
    const done = run.run("ap-south-1", first);
    await run.run("ap-south-1", second);
    expect(second).not.toHaveBeenCalled();
    sent.resolve(PASSED);
    await done;
    expect(first).toHaveBeenCalledTimes(1);
  });

  it("a refusal is kept as it was thrown, and the next run clears it", async () => {
    const run = createStorageTestRun();
    const refusal = new Error("409");
    await run.run("ap-south-1", () => Promise.reject(refusal));
    expect(run.get()).toEqual({ running: false, result: null, region: "ap-south-1", failure: refusal });
    await run.run("eu-west-1", () => Promise.resolve(PASSED));
    expect(run.get()).toEqual({ running: false, result: PASSED, region: "eu-west-1", failure: null });
  });

  it("forget() drops a finished answer, never a running test, and is quiet when there is nothing to drop", async () => {
    const run = createStorageTestRun();
    const listener = vi.fn();
    run.subscribe(listener);
    run.forget();
    expect(listener).not.toHaveBeenCalled();
    const sent = deferred<StorageTest>();
    const done = run.run("ap-south-1", () => sent.promise);
    run.forget();
    expect(run.get().running).toBe(true);
    sent.resolve(PASSED);
    await done;
    run.forget();
    expect(run.get()).toBe(STORAGE_TEST_IDLE);
  });

  it("unsubscribe stops the calls", async () => {
    const run = createStorageTestRun();
    const listener = vi.fn();
    const stop = run.subscribe(listener);
    stop();
    await run.run("ap-south-1", () => Promise.resolve(PASSED));
    expect(listener).not.toHaveBeenCalled();
  });
});
