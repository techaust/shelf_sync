// SYS-03: the tab's real start-up order (boot() is what main.tsx runs): the ticket leaves the address before any
// request, then exactly one request; the #t= listeners for an already-open tab are on the window in the capture
// phase, added during start-up (before React and the hash router exist), and strip the ticket before they sign in.
// The browser's own popstate-before-hashchange order and the router never seeing #t= are checked end to end in
// e2e/shell.spec.ts.
import { describe, expect, it, vi } from "vitest";
import type { SessionState } from "../api/session";
import { type BootWindow, boot } from "./boot";

const TICKET = "Qx3_vB9-kLmN0pRsTuVwXyZ01234567890abcdEFGHij";

type Answer = (method: string, path: string) => Response | Promise<Response>;
const always204: Answer = () => new Response(null, { status: 204 });
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function fakeWindow(hash: string, answer: Answer = always204) {
  const log: string[] = [];
  const listeners: { type: string; capture: boolean; listener: () => void }[] = [];
  const location = { hash, pathname: "/", search: "" };
  const win: BootWindow = {
    location,
    history: {
      state: null,
      replaceState(_data, _unused, url) {
        log.push(`replaceState ${String(url)}`);
        location.hash = new URL(String(url), "http://127.0.0.1").hash;
      },
    },
    addEventListener(type, listener, options) {
      log.push(`listen ${type}`);
      listeners.push({ type, capture: options.capture === true, listener });
    },
  };
  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    log.push(`fetch ${init?.method ?? "GET"} ${String(input)} hash=${location.hash}`);
    return answer(init?.method ?? "GET", String(input));
  });
  const fire = (type: string) => {
    for (const entry of listeners.filter((item) => item.type === type)) entry.listener();
  };
  return { win, log, listeners, location, fetchMock, fire };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("boot (main.tsx's start-up)", () => {
  it("with a ticket: the address is cleaned, then one POST, then the listeners; the ticket is in no log line", async () => {
    const { win, log, fetchMock } = fakeWindow(`#t=${TICKET}`);
    const { started } = boot(win, fetchMock);
    expect(await started).toEqual({ kind: "signed_in" });
    expect(log).toEqual([
      "replaceState /#/",
      "fetch POST /api/session hash=#/",
      "listen popstate",
      "listen hashchange",
    ]);
    expect(log.join("\n")).not.toContain(TICKET);
  });

  it("without a ticket: no address change, one GET to /api/session/status", async () => {
    const { win, log, fetchMock } = fakeWindow("#/review");
    expect(await boot(win, fetchMock).started).toEqual({ kind: "signed_in" });
    expect(log.filter((line) => line.startsWith("fetch") || line.startsWith("replaceState"))).toEqual([
      "fetch GET /api/session/status hash=#/review",
    ]);
  });

  it("the #t= listeners are window listeners in the capture phase (so they run before the router's)", () => {
    const { win, listeners, fetchMock } = fakeWindow("");
    boot(win, fetchMock);
    expect(listeners.map(({ type, capture }) => [type, capture])).toEqual([
      ["popstate", true],
      ["hashchange", true],
    ]);
  });

  it("a #t= arriving in an open, signed-in tab is stripped before its one POST, and signs the tab in again", async () => {
    const { win, log, location, fetchMock, fire } = fakeWindow("#/review");
    const { session, started } = boot(win, fetchMock);
    session.set(await started);
    const seen: SessionState["kind"][] = [];
    session.subscribe(() => seen.push(session.get().kind));
    log.length = 0;

    location.hash = `#t=${TICKET}`;
    fire("popstate"); // the browser fires popstate first: the ticket goes here
    expect(location.hash).toBe("#/");
    fire("hashchange"); // then hashchange, which finds nothing left to do
    await settle();

    expect(log).toEqual(["replaceState /#/", "fetch POST /api/session hash=#/"]);
    expect(seen).toEqual(["checking", "signed_in"]);
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({ ticket: TICKET }); // in the body only
    expect(fetchMock).toHaveBeenCalledTimes(2); // the start-up check and this sign-in, nothing more
  });

  it.each([
    [204, "signed_in"],
    [401, "signed_out"],
  ] as const)(
    "a used ticket in an open tab falls back to the session check (cookie answers %i: %s)",
    async (status, kind) => {
      let statusChecks = 0;
      const { win, log, location, fetchMock, fire } = fakeWindow("#/review", (method) => {
        if (method === "POST") return json(401, { error: "bad_ticket" }); // the ticket is used up
        statusChecks += 1;
        if (statusChecks === 1) return new Response(null, { status: 204 }); // start-up: signed in
        return status === 204 ? new Response(null, { status }) : json(status, { error: "signed_out" });
      });
      const { session, started } = boot(win, fetchMock);
      await started;
      await settle();
      const seen: SessionState["kind"][] = [];
      session.subscribe(() => seen.push(session.get().kind));
      log.length = 0;

      location.hash = `#t=${TICKET}`;
      fire("popstate");
      fire("hashchange");
      await settle();

      expect(log).toEqual([
        "replaceState /#/",
        "fetch POST /api/session hash=#/",
        "fetch GET /api/session/status hash=#/",
      ]);
      expect(seen).toEqual(["checking", kind]); // never "signed_out" on the way when the cookie is good
    },
  );

  it("a late start-up answer never overwrites a newer sign-in (the request counter)", async () => {
    let answerStartUp: (response: Response) => void = () => undefined;
    const { win, location, fetchMock, fire } = fakeWindow("#/review", (method) =>
      method === "GET"
        ? new Promise<Response>((resolve) => {
            answerStartUp = resolve; // the start-up check hangs until the end of the test
          })
        : new Response(null, { status: 204 }),
    );
    const { session, started } = boot(win, fetchMock);

    location.hash = `#t=${TICKET}`;
    fire("popstate");
    await settle();
    expect(session.get()).toEqual({ kind: "signed_in" }); // the newer sign-in

    answerStartUp(json(401, { error: "signed_out" })); // the older check answers last
    expect(await started).toEqual({ kind: "signed_out" });
    await settle();
    expect(session.get()).toEqual({ kind: "signed_in" }); // and is dropped
  });

  it("a screen address change (#/catalog) is left to the router", async () => {
    const { win, log, location, fetchMock, fire } = fakeWindow("#/");
    await boot(win, fetchMock).started;
    log.length = 0;
    location.hash = "#/catalog";
    fire("popstate");
    fire("hashchange");
    await settle();
    expect(log).toEqual([]);
  });
});
