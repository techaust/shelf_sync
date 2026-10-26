# ADR 0005: Localhost only, no login screen

- **Status:** Accepted (owner, with plan Draft 3, 2026-10-25)
- **Date:** 2026-10-25

## Context
One user on one PC. A login screen adds friction without real protection if the app can't be reached from outside.

## Decision
- Bind to **`127.0.0.1`** only.
- A **per-install token** (in Credential Manager) never appears in a URL. The launcher (and a toast click) trades it directly with the server for a **single-use ticket valid for 60 s**, opens the page with that ticket, and the page exchanges the ticket for a strict session cookie (`HttpOnly`, `SameSite=Strict`). A second launch or a new tab gets a fresh ticket, so it's signed in ([06 §2](../06-security.md)). *Amended 2026-10-25 after the re-review (accepted with the Phase 2 docs): the token itself was in the `#t=` URL, which reaches browser history.*
- Every API call except `/api/health` and the two sign-in routes (`/api/session/ticket`, `/api/session`) needs the session. The static UI files are public on 127.0.0.1 but hold no data.
- **`Host`** and **`Origin`** checks plus a custom header on state-changing calls block web pages and DNS rebinding.
- No login screen; "Reset access token" in Settings makes a new token.

## Consequences
- The app is reachable only from this PC, and its data only with the token.
- SSE and CSV downloads work, because the cookie travels with them.
- If the owner ever wants remote use, this ADR is replaced first.
