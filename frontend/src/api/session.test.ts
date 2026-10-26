// SYS-03, the page's side of sign-in (docs/runs/m1a.2-security.md item 11): the #t= ticket leaves the address
// before any request, is POSTed once as {"ticket"} with X-ShelfSync: 1, and never shows up in logs, the console,
// storage or error text. fetch is mocked.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "./client";
import {
  createSessionStore,
  type HistoryLike,
  type LocationLike,
  probeSession,
  SESSION_PROBE_PATH,
  SIGN_IN_PATH,
  signIn,
  startSession,
  takeTicket,
} from "./session";

const TICKET = "Qx3_vB9-kLmN0pRsTuVwXyZ01234567890abcdEFGHij"; // the shape of secrets.token_urlsafe(32)

function fakeAddress(hash: string, log: string[] = []) {
  const location: LocationLike = { hash, pathname: "/", search: "" };
  const history: HistoryLike & { urls: string[] } = {
    state: null,
    urls: [],
    replaceState(_data, _unused, url) {
      log.push("replaceState");
      this.urls.push(String(url));
    },
  };
  return { location, history };
}

function fetchAnswering(status: number, body?: unknown, log: string[] = []) {
  return vi.fn<typeof fetch>(async () => {
    log.push("fetch");
    if (status === 204) return new Response(null, { status });
    return new Response(body === undefined ? "" : JSON.stringify(body), { status });
  });
}

const CONSOLE_METHODS = ["log", "info", "warn", "error", "debug", "trace"] as const;
let consoleSpies: ReturnType<typeof vi.spyOn>[] = [];
let storageWrites: string[] = [];

beforeEach(() => {
  consoleSpies = CONSOLE_METHODS.map((method) => vi.spyOn(console, method).mockImplementation(() => {}));
  storageWrites = [];
  const storage = {
    getItem: () => null,
    setItem: (key: string, value: string) => storageWrites.push(`${key}=${value}`),
    removeItem: () => {},
  };
  vi.stubGlobal("localStorage", storage);
  vi.stubGlobal("sessionStorage", storage);
});

afterEach(() => {
  // Nothing in this file may print anything, and nothing may be stored: the ticket included.
  for (const spy of consoleSpies) expect(spy).not.toHaveBeenCalled();
  expect(storageWrites).toEqual([]);
});

describe("takeTicket", () => {
  it("returns the ticket and removes it from the address, leaving the Dashboard route", () => {
    const { location, history } = fakeAddress(`#t=${TICKET}`);
    expect(takeTicket(location, history)).toBe(TICKET);
    expect(history.urls).toEqual(["/#/"]);
    expect(history.urls.join()).not.toContain(TICKET);
  });

  it.each(["", "#/", "#/review", "#main", "#token=abc"])("leaves an address without #t= alone: %j", (hash) => {
    const { location, history } = fakeAddress(hash);
    expect(takeTicket(location, history)).toBeNull();
    expect(history.urls).toEqual([]);
  });

  it.each(["", "short", "has space in it here ok", "a".repeat(257), `${TICKET}&x=1`, "%3Cscript%3E-------------"])(
    "removes a #t= that isn't ticket-shaped and returns null: %j",
    (value) => {
      const { location, history } = fakeAddress(`#t=${value}`);
      expect(takeTicket(location, history)).toBeNull();
      expect(history.urls).toEqual(["/#/"]);
    },
  );

  it("removes the ticket before the page makes any request", async () => {
    const log: string[] = [];
    const { location, history } = fakeAddress(`#t=${TICKET}`, log);
    const api = createApiClient({ fetch: fetchAnswering(204, undefined, log) });
    await startSession(api, takeTicket(location, history));
    expect(log).toEqual(["replaceState", "fetch"]);
  });
});

describe("signIn", () => {
  it('POSTs {"ticket"} to /api/session once, with X-ShelfSync: 1, and is signed in on 204', async () => {
    const fetchMock = fetchAnswering(204);
    const state = await signIn(createApiClient({ fetch: fetchMock }), TICKET);
    expect(state).toEqual({ kind: "signed_in" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [path, init] = fetchMock.mock.calls[0] ?? [];
    expect(path).toBe(SIGN_IN_PATH);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ ticket: TICKET });
    expect((init?.headers ?? {}) as Record<string, string>).toHaveProperty("X-ShelfSync", "1");
    expect(String(path)).not.toContain(TICKET); // in the body, never the URL
  });

  it.each(["bad_ticket", "signed_out"])("401 %s gives the signed-out state, with no retry", async (code) => {
    const fetchMock = fetchAnswering(401, { error: code });
    expect(await signIn(createApiClient({ fetch: fetchMock }), TICKET)).toEqual({ kind: "signed_out" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("no answer gives the unreachable state", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => {
      throw new TypeError("Failed to fetch");
    });
    expect(await signIn(createApiClient({ fetch: fetchMock }), TICKET)).toEqual({ kind: "unreachable" });
  });

  it.each([403, 422, 500])("HTTP %i is a refusal with its status", async (status) => {
    expect(await signIn(createApiClient({ fetch: fetchAnswering(status, { error: "forbidden" }) }), TICKET)).toEqual({
      kind: "refused",
      status,
    });
  });

  it("the resulting state never holds the ticket", async () => {
    for (const status of [204, 401, 403, 500]) {
      const state = await signIn(createApiClient({ fetch: fetchAnswering(status, { error: "internal" }) }), TICKET);
      expect(JSON.stringify(state)).not.toContain(TICKET);
    }
  });
});

describe("probeSession (no ticket: a refresh or a second tab)", () => {
  it("a GET to the protected probe path: 405 means the cookie was accepted", async () => {
    const fetchMock = fetchAnswering(405, { detail: "Method Not Allowed" });
    expect(await probeSession(createApiClient({ fetch: fetchMock }))).toEqual({ kind: "signed_in" });
    const [path, init] = fetchMock.mock.calls[0] ?? [];
    expect(path).toBe(SESSION_PROBE_PATH);
    expect(init?.method).toBe("GET"); // never the POST that would reset the token
  });

  it("401 means signed out", async () => {
    expect(await probeSession(createApiClient({ fetch: fetchAnswering(401, { error: "signed_out" }) }))).toEqual({
      kind: "signed_out",
    });
  });

  it("anything else is a refusal, and no answer is unreachable", async () => {
    expect(await probeSession(createApiClient({ fetch: fetchAnswering(403, { error: "forbidden" }) }))).toEqual({
      kind: "refused",
      status: 403,
    });
    const down = vi.fn<typeof fetch>(async () => {
      throw new TypeError("Failed to fetch");
    });
    expect(await probeSession(createApiClient({ fetch: down }))).toEqual({ kind: "unreachable" });
  });

  it("startSession probes when there is no ticket, and signs in when there is one", async () => {
    const probe = fetchAnswering(405);
    await startSession(createApiClient({ fetch: probe }), null);
    expect(probe.mock.calls[0]?.[0]).toBe(SESSION_PROBE_PATH);
    const sign = fetchAnswering(204);
    await startSession(createApiClient({ fetch: sign }), TICKET);
    expect(sign.mock.calls[0]?.[0]).toBe(SIGN_IN_PATH);
  });
});

describe("the session store", () => {
  it("a later 401 signed_out from any call switches the tab to signed out", async () => {
    const session = createSessionStore({ kind: "signed_in" });
    const seen: string[] = [];
    session.subscribe(() => seen.push(session.get().kind));
    const api = createApiClient({
      fetch: fetchAnswering(401, { error: "signed_out" }),
      onSignedOut: () => session.set({ kind: "signed_out" }),
    });
    await api.get("/api/catalog").catch(() => undefined);
    expect(session.get()).toEqual({ kind: "signed_out" });
    expect(seen).toEqual(["signed_out"]);
  });
});
