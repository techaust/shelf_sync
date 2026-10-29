// ERR-01: the health popover's title by the chip's kind, and where the focus goes when it closes (review round 1,
// items 1 and 2). The chip that opened it can turn into a read-out while it is open (a test inside it fixed the store):
// then the read-out takes the focus, unless a click outside already put it somewhere.
import { describe, expect, it } from "vitest";
import { chipFocusAfterClose, isProblem, popoverTitle } from "./storeHealth";
import { S } from "./storesWording";

const body = { tagName: "BODY" } as unknown as Element;
const button = { tagName: "BUTTON" } as unknown as Element;

describe("the popover's title", () => {
  it("by kind; a store a test just fixed says it is connected, never 'hasn't been tested yet'", () => {
    expect(popoverTitle("failed", "Sample store")).toBe("Sample store can't be reached.");
    expect(popoverTitle("unknown", "Sample store")).toBe("Sample store hasn't been tested yet.");
    expect(popoverTitle("connected", "Sample store")).toBe("Sample store is connected.");
    expect(popoverTitle("paused", "Sample store")).toBe(S.pausedDone("Sample store"));
  });
});

describe("the chip is a button for a failed or never-tested store only", () => {
  it.each([
    ["failed", true],
    ["unknown", true],
    ["connected", false],
    ["paused", false],
  ] as const)("%s: %s", (kind, problem) => {
    expect(isProblem(kind)).toBe(problem);
  });
});

describe("where the focus goes when the popover closes", () => {
  it("still a button: Radix gives the focus back to it", () => {
    expect(chipFocusAfterClose(true, body, body)).toBe("leave");
  });

  it("now a read-out, after Esc (the removed popover left the focus on the body): the read-out takes it", () => {
    expect(chipFocusAfterClose(false, body, body)).toBe("chip");
    expect(chipFocusAfterClose(false, null, body)).toBe("chip");
  });

  it("now a read-out, after a click outside on the page's background: the read-out takes it", () => {
    expect(chipFocusAfterClose(false, body, body)).toBe("chip");
  });

  it("a click outside on another control keeps the focus there", () => {
    expect(chipFocusAfterClose(false, button, body)).toBe("leave");
  });
});
