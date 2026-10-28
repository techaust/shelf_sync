// SET-01, ERR-01: the tab's store of running tests. A second Test connection while one runs does nothing (the card
// and the popover share it), an answer or a refusal is kept for the screens, and the list is read again afterwards.
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { StoreTest } from "../../api/stores";
import { S } from "./storesWording";
import { createStoreTests } from "./storeTests";

const answer: StoreTest = {
  ok: true,
  state: "connected",
  reason: null,
  http_status: 200,
  latency_ms: 298,
  wc_version: "9.4.2",
  wp_version: "6.8",
  downloadable_count: 12,
  tested_at: "2026-10-29T04:00:00Z",
  detail: null,
  warning: null,
};

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  let reject: (error: unknown) => void = () => undefined;
  const promise = new Promise<T>((ok, no) => {
    resolve = ok;
    reject = no;
  });
  return { promise, resolve, reject };
}

describe("Test connection, one at a time per store", () => {
  it("shows progress, then keeps the answer and reads the list again", async () => {
    const tests = createStoreTests();
    const pending = deferred<StoreTest>();
    const after = vi.fn();
    const run = tests.run(1, () => pending.promise, after);
    expect(tests.entry(1)).toEqual({ running: true, result: null, error: null });
    pending.resolve(answer);
    await run;
    expect(tests.entry(1)).toEqual({ running: false, result: answer, error: null });
    expect(after).toHaveBeenCalledTimes(1);
  });

  it("a second click while it runs does nothing (no second request)", async () => {
    const tests = createStoreTests();
    const pending = deferred<StoreTest>();
    const send = vi.fn(() => pending.promise);
    const first = tests.run(1, send);
    await tests.run(1, send);
    expect(send).toHaveBeenCalledTimes(1);
    pending.resolve(answer);
    await first;
  });

  it("other stores test at the same time", async () => {
    const tests = createStoreTests();
    const one = deferred<StoreTest>();
    const send = vi.fn(() => one.promise);
    const a = tests.run(1, send);
    const b = tests.run(2, send);
    expect(send).toHaveBeenCalledTimes(2);
    one.resolve(answer);
    await Promise.all([a, b]);
  });

  it("a refusal is kept in 13's words (busy as information)", async () => {
    const tests = createStoreTests();
    await tests.run(1, () => Promise.reject(new ApiError("POST", "/api/stores/1/test", 409, "busy")));
    expect(tests.entry(1).error).toEqual({ text: S.errors.busy, tone: "info" });
    await tests.run(1, () => Promise.reject(new ApiError("POST", "/api/stores/1/test", 409, "keys_missing")));
    expect(tests.entry(1).error).toEqual({ text: S.errors.keys_missing, tone: "danger" });
  });

  it("subscribers hear each change; forget drops a stale result but never a running test", async () => {
    const tests = createStoreTests();
    const heard = vi.fn();
    const stop = tests.subscribe(heard);
    await tests.run(1, () => Promise.resolve(answer));
    expect(heard).toHaveBeenCalledTimes(2);
    tests.forget(1);
    expect(tests.entry(1).result).toBeNull();
    const pending = deferred<StoreTest>();
    const run = tests.run(1, () => pending.promise);
    tests.forget(1);
    expect(tests.entry(1).running).toBe(true);
    pending.resolve(answer);
    await run;
    stop();
  });
});
