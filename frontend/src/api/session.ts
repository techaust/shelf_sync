// Sign-in, the page's side (SYS-03; contract in docs/runs/m1a.2-security.md item 11 and section 3).
// The launcher opens http://127.0.0.1:<port>/#t=<ticket>. The page:
//   1. reads #t= and removes it from the address bar with history.replaceState, before it makes any request
//      (a fragment is never sent to a server, and the page's Referrer-Policy is no-referrer, so the ticket also
//      never leaves the browser in a request line or a Referer header);
//   2. POSTs it once to /api/session as {"ticket": …} (the client adds X-ShelfSync: 1; the browser adds Origin);
//   3. on 204 the session cookie is set (HttpOnly; the page never sees it). On 401 it shows the signed-out state.
// Without a ticket (a refresh, a second tab) it asks a protected path whether the cookie is still good.
// The ticket is held in one local variable for one request: never logged, stored, put in state or in error text.

import { type ApiClient, ApiError, ApiUnreachableError } from "./client";
import type { components } from "./schema";

/** The sign-in body, typed from the backend's OpenAPI schema (src/api/schema.d.ts). */
type SignInRequest = components["schemas"]["SignInRequest"];

export const SIGN_IN_PATH = "/api/session";

// There is no "am I signed in?" route yet (open question for the lead, docs/runs/m1a.3-app-shell.md section 4).
// Until there is one, the page asks a session-protected path with GET: the guard answers 401 "signed_out" without
// a valid cookie, and with one the request reaches the router, which answers 405 (the route takes POST only).
// GET never changes anything there. Replace with the real route when the builder adds it.
export const SESSION_PROBE_PATH = "/api/session/reset-token";

/** What `secrets.token_urlsafe(32)` makes (43 characters), with room to spare; anything else isn't a ticket. */
const TICKET_SHAPE = /^[A-Za-z0-9_-]{16,256}$/;
const TICKET_PREFIX = "#t=";

export interface LocationLike {
  readonly hash: string;
  readonly pathname: string;
  readonly search: string;
}

export interface HistoryLike {
  readonly state: unknown;
  replaceState(data: unknown, unused: string, url?: string | URL | null): void;
}

/**
 * Takes the ticket out of the address: returns it (or null) and leaves the address as `/#/`, so the ticket isn't
 * in the address bar, the history entry or a bookmark. A hash that starts with #t= is always removed, even when
 * what follows isn't ticket-shaped.
 */
export function hasTicketFragment(location: LocationLike): boolean {
  return location.hash.startsWith(TICKET_PREFIX);
}

export function takeTicket(location: LocationLike, history: HistoryLike): string | null {
  if (!hasTicketFragment(location)) return null;
  const candidate = location.hash.slice(TICKET_PREFIX.length);
  history.replaceState(history.state, "", `${location.pathname}${location.search}#/`);
  return TICKET_SHAPE.test(candidate) ? candidate : null;
}

export type SessionState =
  | { kind: "checking" }
  | { kind: "signed_in" }
  | { kind: "signed_out" }
  | { kind: "unreachable" }
  | { kind: "refused"; status: number };

/** Exchanges the ticket for the session cookie. One attempt; no retry loop. */
export async function signIn(api: ApiClient, ticket: string): Promise<SessionState> {
  try {
    const body: SignInRequest = { ticket };
    await api.send("POST", SIGN_IN_PATH, body);
    return { kind: "signed_in" };
  } catch (error) {
    return fromError(error);
  }
}

/** Is the session cookie (if any) still accepted? */
export async function probeSession(api: ApiClient): Promise<SessionState> {
  let response: Response;
  try {
    response = await api.request("GET", SESSION_PROBE_PATH);
  } catch (error) {
    return fromError(error);
  }
  if (response.status === 401) return { kind: "signed_out" };
  // 405: the cookie was accepted and the GET reached the route (see SESSION_PROBE_PATH).
  if (response.status === 405) return { kind: "signed_in" };
  return { kind: "refused", status: response.status };
}

/** Sign in with the ticket if there is one, otherwise check the existing session. */
export function startSession(api: ApiClient, ticket: string | null): Promise<SessionState> {
  return ticket === null ? probeSession(api) : signIn(api, ticket);
}

function fromError(error: unknown): SessionState {
  if (error instanceof ApiUnreachableError) return { kind: "unreachable" };
  if (error instanceof ApiError)
    return error.status === 401 ? { kind: "signed_out" } : { kind: "refused", status: error.status };
  return { kind: "refused", status: 0 };
}

/** A tiny store the client's 401 handler and the React tree share (useSyncExternalStore). */
export function createSessionStore(initial: SessionState = { kind: "checking" }) {
  let state = initial;
  const listeners = new Set<() => void>();
  return {
    get: (): SessionState => state,
    set(next: SessionState): void {
      state = next;
      for (const listener of listeners) listener();
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export type SessionStore = ReturnType<typeof createSessionStore>;
