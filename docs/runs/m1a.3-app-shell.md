Status: open
Tier: B (design effort A: designer at high, [12 §2](../12-models-and-usage.md))
Usage: (filled from node tools/model-audit.mjs)

# M1a.3: App shell

## 1. Brief
_(lead, Opus 5.5 medium, 2026-10-27)_

**Roadmap:** M1a, the screens part ([08](../08-roadmap.md) M1a row): tokens and fonts, UI-SHELL (shell), axe in CI. It builds on M1a.1 (merged) and **M1a.2** (security base, branch `feat/m1a.2-security`), and codes to M1a.2's sign-in contract.

**PRD IDs** ([03](../03-prd.md)):
- **UI-SHELL** (shell only): side nav (Dashboard, Upload, Review + count, Catalog, Cleanup + count, Activity, Settings); the store and S3 health area; "Pause everything"; the status strip (auto-apply, trust ramp, last sync, next snapshot); theme follows Windows, with a manual override. Live counts are M5.
- **NFR-1:** every font, icon and script bundled; no CDN at run time.
- **SYS-03**, the page's side of sign-in (the `#t=` exchange and the signed-out state).
- Accessibility: [05 §7](../05-design-system.md), [07 §4](../07-testing.md).

**Who:** the `designer` (Opus 5.5, **high**), in its own git worktree on the branch `feat/m1a.3-app-shell`, cut from the head of `feat/m1a.2-security` that the lead names when starting the task (M1a.2 merges first; this branch is rebased onto `main` after that). Commit there; **never push**. The lead integrates. One small backend change (the static mount) is in scope, described in item 6.

**Writes only to:**
- `frontend/` (new): the Vite + React + TypeScript app, its `package.json`, `package-lock.json`, configs and tests
- `backend/shelfsync/api/app.py` (the static mount only) and `tests/` (the mount and route-table tests)
- `.github/workflows/checks.yml`: a new `ui` job (item 9)
- §4 of this file

The lead owns `docs/` (except §4 here), `CLAUDE.md`, `CHANGELOG.md`, `brand/` and `.gitignore`: suggest changes in §4. `.gitignore` additions needed for `frontend/node_modules` and `frontend/dist`: list them in §4.

**Skills and tools** ([09 §3](../09-tooling.md)), loaded first and named in §4:
- **`frontend-design`** before any screen or component.
- **`dataviz`** only if a chart, KPI tile or meter is built (none is expected in the shell).
- **Built-in browser** (the `mcp__Claude_Browser__*` tools, `preview_start`) for every screenshot and visual check, never headless Chrome or the Playwright MCP (CLAUDE.md rule 10). Full-page 2× shots go through the in-pane capture helper ([screenshots README](../05-design-system-appendix/screenshots/README.md)).
- **Context7** before writing code that uses React 19.3, React Router 8.4, TanStack Query 5.104, Radix (tooltip, dropdown-menu, dialog), Lucide 1.55, Vite 8.3, Tailwind 4.3 (`@tailwindcss/vite`), Biome 2.5, Vitest 5.0, Playwright 1.64, @axe-core/playwright 4.13 and openapi-typescript 7.13.
- Heavy commands only through `bash tools/heavy.sh --log m1a.3-<name> <command>`.
- **No test browser is downloaded to this PC** (owner, [11](../11-decisions.md)): Playwright and axe run in CI only. Locally, check screens in the built-in browser.

**Owner decisions that bind this task** ([11](../11-decisions.md)):
- **UI packages:** only the 22 in [04 §2.1](../04-architecture.md), at exactly those versions; npm `before` set to `2026-10-13T00:00:00Z` (`.npmrc` in `frontend/`), so everything they pull in is older than the 14-day cutoff; `package-lock.json` committed with integrity hashes; `npm ci` in CI. Nothing else; if one is missing, stop and report it.
- **Design:** tokens only, never a hand-typed colour ([05](../05-design-system.md)); store colours only as small identifiers; wording from the approved mockup and [13](../13-content.md) (13 §6: the mockup is the source of screen wording until M1).
- **The approved mockup** (`docs/05-design-system-appendix/mockup/`, P3.4–P3.5) is the visual reference: match its shell (app bar, nav, status strip, health area) closely, but build it as React components, not by copying its JavaScript.
- Desktop only: designed for 1280–1920 px, usable at 1024 px (nav collapses to icons), no phone layout (05 §6).
- No telemetry, no external requests (NFR-1, NFR-5).

**Work:**
1. **Project** (`frontend/`): Vite 8 + React 19 + TypeScript 5.9 (strict), React Router, TanStack Query, Biome for lint and format, `tsc --noEmit`, Vitest. `npm run build` writes `frontend/dist/`. Layout per [04](../04-architecture.md): `src/screens`, `src/components`, `src/api`.
2. **Tokens and fonts:**
   - the Tailwind v4 theme comes from `brand/generated/tokens.css` (built from `brand/tokens.json`); import or copy it by a script, never by hand, and say which and why
   - the **ShelfSync token layer** from P3.4 ([runs/p3.4-mockups.md](p3.4-mockups.md) §4): app-bar tokens (the app bar is ink in both themes, `tone-dark`), fixed type sizes, code at 14 px, the `color-mix` tints, as tokens in one file
   - Archivo (variable) and IBM Plex Mono through the pinned `@fontsource` packages, bundled by Vite; file names, slugs and hashes in Plex Mono; versions, counts and times with tabular numbers
   - Lucide icons from `lucide-react`, tree-shaken
   - a **token contrast test** (Vitest): every text/background pair the shell uses, in light and dark, meets WCAG AA; the store identifier dots on every surface meet 3:1 ([07 §4](../07-testing.md), [05 §2.3](../05-design-system.md))
3. **The shell (UI-SHELL):**
   - app bar with the logo (`brand/assets/`, the approved lockup), side nav with all seven items and their Lucide icons, the Review and Cleanup count badges (static 0 for now), the store and S3 health area, "Pause everything", the status strip (auto-apply, trust ramp, last sync, next snapshot)
   - data the backend doesn't serve yet (counts, health, status) comes from **one typed placeholder module** in `src/api/`, clearly marked, with the "no data yet" states from 13 / the mockup (no invented numbers); M1b–M5 replace it with real endpoints
   - each nav item opens a route with the screen's title and its **empty state** (05 §6 "States on every screen"; wording from the mockup / 13 §3 ERR-07). The screens themselves are later milestones.
   - "Pause everything" is visible but disabled with a tooltip until M5 (wording: propose it in §4; the lead adds it to 13)
4. **Theme:** follows Windows (`prefers-color-scheme`) by default; a manual override (system, light, dark) in the app bar. Until M1b's Settings API exists, the override is kept in `localStorage` (a convenience only; wrapped in try/catch; the page works without it) and applied before first paint without an inline script (a small module loaded first). M1b moves it to the `theme` setting.
5. **Sign-in (the M1a.2 contract, [runs/m1a.2-security.md](m1a.2-security.md) item 11 and §3):**
   - on load, read `#t=` from the URL and remove it with `history.replaceState` **before any other request**
   - POST it as JSON `{"ticket": …}` to `/api/session` with `X-ShelfSync: 1` (the page's Origin is sent by the browser)
   - one small API client in `src/api/` that sends `X-ShelfSync: 1` on every write (any method except GET and HEAD); it never reads or stores the cookie (it's `HttpOnly`)
   - on 401 `signed_out` (or no ticket and no session), show the **signed-out state**: "This tab isn't signed in. Open ShelfSync from the tray icon or the Start menu." ([13 §3](../13-content.md)); no retry loop, no token prompt
   - the ticket never appears in logs, the console, `localStorage` or any error text
   - Vitest tests for each of these, with `fetch` mocked
6. **Static files (backend, small):**
   - serve `frontend/dist/` from `create_app` with Starlette's `StaticFiles` (html mode, so `/` gives `index.html`), mounted **inside** the M1a.2 middleware (Host check and security headers apply; no session needed, 06 §2)
   - add its path to `ALLOWED_OUTSIDE_API` in `tests/test_guard.py` in the same change (the route-table test fails until it does)
   - when `frontend/dist/` doesn't exist (backend-only CI, tests), the app starts without the mount and logs one line; test both cases
   - client-side routes (e.g. `/review`) must load `index.html` on refresh: use hash routing **or** a fallback; say which and why (a fallback must never answer under `/api`)
7. **CSP compliance:** the built app runs under M1a.2's CSP unchanged: no inline scripts or styles, no `eval`, no `data:` URLs (fonts and images as files). Radix and React set some styles from JavaScript. Verify with Context7 and MDN what `style-src 'self'` (without `'unsafe-inline'`) blocks in that case (expected: `<style>` elements and `style=""` attributes in HTML, but not styles set through the CSSOM from script), and check the built app in the built-in browser's console. If the CSP must change, stop and report; the lead decides.
8. **Types from the API:** `openapi-typescript` generates `src/api/schema.d.ts` from the backend's OpenAPI schema (exported by a small script that imports `create_app` and writes JSON, since the docs routes are off). An npm script regenerates it; CI checks it's current.
9. **CI (`ui` job in `.github/workflows/checks.yml`, ubuntu-24.04):** `setup-node` (Node 24.19.0, the pinned SHA) → `npm ci` → Biome → `tsc --noEmit` → Vitest → `npm run build` → the schema-current check → Playwright with **@axe-core/playwright** on the shell and every nav route, **light and dark**, zero violations allowed (WCAG 2.2 A and AA tags), plus a test that fails on any CSP violation in the console and one for keyboard navigation through the nav → `npm audit --omit=dev --audit-level=high`. Playwright runs against the **backend serving the built files** (a real 127.0.0.1 server with a test ticket issued in-process), so the CSP, Host check and sign-in flow are the real ones. Install the Playwright browser in CI only (`npx playwright install --with-deps chromium`). Upload the Playwright report with the pinned `upload-artifact` only on failure.
10. **Screenshots** (built-in browser, served by the real backend on this PC): the shell at 1440 px in light and dark, the signed-out state, the nav collapsed at 1024 px; save them in `docs/05-design-system-appendix/screenshots/m1a.3/` (the one `docs/` folder you may write to) and list them in §4. Compare with the mockup and list any difference with its reason.

**Done means** (through `tools/heavy.sh`, results in §4):
- in `frontend/`: `npm ci`, Biome, `tsc --noEmit`, Vitest (sign-in flow, API client, theme, contrast test), `npm run build`, `npm audit --omit=dev --audit-level=high` all pass on this PC
- the backend checks still pass: `uv run ruff check`, `ruff format --check`, `mypy`, `pytest` (with the mount tests and the updated route-table test)
- the brand tests still pass (`npm test --prefix brand`, 221)
- the built app loads from the backend in the built-in browser with no console errors and no CSP violations; the sign-in with a real ticket works; screenshots taken
- the Playwright + axe job exists and is valid; say "not run on GitHub yet"

**Out of scope** (owned elsewhere):
- the real screens (Dashboard M3–M5, Upload and Review M4–M5, Catalog M3, Cleanup M3, Activity M5, Settings M1b–M2, the wizard M3), live counts and SSE (M5)
- the theme setting API and Settings › App (M1b)
- the tray, launcher and opening the browser (M1a.4)
- the shared SecretField (M2), the wizard's Test-step badges (M2), "Installs in under a minute" (M1b)

**Report in §4:** skills loaded (`frontend-design` first), files changed, every command and its result, what Context7 said that changed your approach, screenshot paths, differences from the mockup, any placeholder data, proposed wording for 13, `.gitignore` lines, anything not verified, open questions.

## 2. Early check
_(Tier B: none.)_

## 3. Builder report
_(none: the designer does the one backend change)_

## 4. Designer report
_(empty)_

## 5. Review
_(empty)_

## 6. Integration notes
_(empty)_

## 7. Handover
_(lead, 2026-10-27)_ Brief written at Opus 5.5 medium. Waits for M1a.2's fix round and re-check, then the designer starts from the head of `feat/m1a.2-security`.
