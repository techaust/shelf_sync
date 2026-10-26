// The tab's start-up, in the order SYS-03 needs (main.tsx calls it once, before React renders anything). Kept out
// of main.tsx so the real order is what the tests check (boot.test.ts), with a fake window.
import { type ApiClient, createApiClient } from "../api/client";
import {
  createSessionStore,
  type HistoryLike,
  hasTicketFragment,
  type LocationLike,
  type SessionState,
  type SessionStore,
  startSession,
  takeTicket,
} from "../api/session";

/** The few window members start-up uses. */
export interface BootWindow {
  readonly location: LocationLike;
  readonly history: HistoryLike;
  addEventListener(type: "popstate" | "hashchange", listener: () => void, options: AddEventListenerOptions): void;
}

export interface Booted {
  api: ApiClient;
  session: SessionStore;
  started: Promise<SessionState>;
}

export function boot(win: BootWindow, fetchImpl?: typeof fetch): Booted {
  // 1. The sign-in ticket leaves the address bar before the page makes any request.
  const ticket = takeTicket(win.location, win.history);

  // 2. One API client and one session store for the tab; a 401 "signed_out" anywhere shows the signed-out state.
  const session = createSessionStore();
  const api = createApiClient({
    ...(fetchImpl ? { fetch: fetchImpl } : {}),
    onSignedOut: () => session.set({ kind: "signed_out" }),
  });

  // 3. Sign in with the ticket (one POST), or ask whether the existing session is still good. The ticket never
  //    reaches React's props or state.
  const started = startSession(api, ticket);

  // 4. A sign-in address opened in this same tab (#t= arrives without a page load, signed in or not). The browser
  //    fires popstate, then hashchange. These listeners are on the window in the capture phase and are added before
  //    the hash router exists, so they run before the router's own popstate listener: the ticket is out of the
  //    address before the router reads it, and the router only ever sees "#/".
  const onAddressChange = () => {
    if (!hasTicketFragment(win.location)) return;
    const next = takeTicket(win.location, win.history);
    session.set({ kind: "checking" });
    startSession(api, next).then(session.set);
  };
  win.addEventListener("popstate", onAddressChange, { capture: true });
  win.addEventListener("hashchange", onAddressChange, { capture: true });

  return { api, session, started };
}
