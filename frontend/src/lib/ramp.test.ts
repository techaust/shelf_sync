// UI-SHELL: the status strip's trust-ramp meter width.
import { describe, expect, it } from "vitest";
import { rampPercent } from "./ramp";

describe("rampPercent", () => {
  it.each([
    [0, 50, 0],
    [1, 50, 2],
    [25, 50, 50],
    [50, 50, 100],
    [80, 50, 100],
    [0, 0, 0],
    [5, 0, 0],
    [-3, 50, 0],
    [Number.NaN, 50, 0],
    [10, Number.POSITIVE_INFINITY, 0],
  ])("%d of %d is %d %%", (count, target, expected) => {
    expect(rampPercent(count, target)).toBe(expected);
  });
});
