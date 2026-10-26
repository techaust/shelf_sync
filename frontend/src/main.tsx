// 1. The theme, first: data-theme is set before anything renders (no inline script; the CSP forbids one).
import "./theme/early";
import "./styles/app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createApiClient } from "./api/client";
import { createSessionStore, hasTicketFragment, startSession, takeTicket } from "./api/session";
import { App, makeQueryClient } from "./app/App";

// 2. The sign-in ticket leaves the address bar before the page makes any request (SYS-03).
const ticket = takeTicket(window.location, window.history);

// 3. One API client and one session store for the tab; a 401 "signed_out" anywhere shows the signed-out state.
const session = createSessionStore();
const api = createApiClient({ onSignedOut: () => session.set({ kind: "signed_out" }) });

// 4. Sign in with the ticket (one POST), or check the existing session. Started here, once, so the ticket never
//    reaches React's props or state.
const started = startSession(api, ticket);

// 5. A sign-in address opened in this same tab (#t= arrives without a page load): the same steps again. Added
//    before the router exists, so it runs before the router reads the hash.
window.addEventListener("hashchange", () => {
  if (!hasTicketFragment(window.location)) return;
  const next = takeTicket(window.location, window.history);
  session.set({ kind: "checking" });
  startSession(api, next).then(session.set);
});

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App api={api} session={session} started={started} queryClient={makeQueryClient()} />
    </StrictMode>,
  );
}
