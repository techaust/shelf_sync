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
_(designer, Opus 5.5 high, 2026-10-27; branch `feat/m1a.3-app-shell` from `872dea4` + the brief `15b667a`; not pushed)_

**Skills and tools loaded:** `frontend-design` first (before any screen or component). It changed two things: the visual direction is pinned by the approved mockup, so the one bold element stays the diagonal cut on the active nav item and nothing new is decorated; and every new state (signed out, no answer, not found, nothing connected) was written as "what happened + what to do", with an action only where it works today. `dataviz`: not loaded (no chart, KPI tile or meter is built; the trust-ramp bar is the mockup's existing decorative meter, `aria-hidden`, with the count in text). Context7 for every library (below). Built-in browser (`mcp__Claude_Browser__*`) for every visual check. No Playwright MCP, no headless Chrome.

**Files** (all new unless marked):
- `backend/shelfsync/api/app.py` (changed): the static mount (`_UiMount`, `_mount_ui`, `UI_DIR`, `create_app(..., ui_dir=UI_DIR)`).
- `tests/support.py` (changed: `make_harness(ui_dir=None)`), `tests/test_guard.py` (changed: `ALLOWED_OUTSIDE_API = {""}`, route-table tests run with and without the mount, a test that the mount is the only route outside `/api`), `tests/test_static_ui.py` (new, 25 tests).
- `.github/workflows/checks.yml` (changed): the `ui` job.
- `frontend/`: `package.json`, `package-lock.json` (199 integrity hashes), `.npmrc`, `index.html`, `vite.config.ts`, `vitest.config.ts`, `tsconfig.json`, `biome.json`, `playwright.config.ts`; `scripts/sync-tokens.mjs`, `scripts/schema.mjs`, `scripts/export_openapi.py`; `e2e/server.py`, `e2e/support.ts`, `e2e/shell.spec.ts`; `public/favicon.svg`, `public/favicon.ico` (copied by script); `src/main.tsx`; `src/api/` (`client.ts`, `session.ts`, `placeholder.ts`, `schema.d.ts` generated, two test files); `src/app/` (`App.tsx`, `router.tsx`, `nav.ts`); `src/components/` (`AppShell`, `AppBar`, `SideNav`, `StatusStrip`, `HealthArea`, `StoreBadge`, `PauseButton`, `ThemeMenu`, `Tip`, `Page` with `EmptyState`, `useCollapsedNav`); `src/screens/` (`screens.tsx`, `SessionGate.tsx`); `src/theme/` (`theme.ts`, `early.ts`, `useTheme.ts`, test); `src/lib/time.ts`; `src/styles/` (`app.css`, `fonts.css`, `generated/tokens.css`, `generated/theme.css`, `generated/shelfsync-tokens.css`, `contrast.test.ts`, `tokens.test.ts`); `src/assets/brand/logo-primary-dark.svg` (copied by script).
- `docs/05-design-system-appendix/screenshots/m1a.3/` (16 images) and this §4.

**Decisions inside the brief:**
- **Tokens: copied by script, not imported.** `npm run tokens` (`scripts/sync-tokens.mjs`) copies `brand/generated/tokens.css` byte for byte, generates the Tailwind `@theme` from its light `:root` block (`--*: initial` first, so no Tailwind default colour or size exists) and the ShelfSync token layer (`generated/shelfsync-tokens.css`) from `brand/tokens.json`, and copies the dark lockup and the favicons. Why a copy: Vite, Tailwind and Biome then read only `frontend/`, and `npm run build` runs `sync-tokens.mjs --check` first, so a copy out of step with `brand/` fails the build instead of shipping; a Vitest test also compares the copy with `brand/` byte for byte. Tailwind's theme layer holds the light values; the unlayered `tokens.css` after it holds the same values plus the dark ones, so every utility follows the theme.
- **The ShelfSync token layer** (one generated file): app-bar tokens (`ink-900` light, `ink-750` dark; mist and `ink-300`), the `.tone-dark` scope (every semantic dark value), the fixed sizes from `tokens.json` (`--app-text-title` 36 px = `display-2.min`, `--app-text-kpi` 28 px = `h2.min`), code at 14 px (`--app-text-code`, `text.sm`), `--app-bar-height`, `--app-cut`, and the twelve `color-mix()` amounts from P3.4 §4 as `--tint-*` percentages (a mix that names `--tone` can't be resolved on `:root`, so components mix with these amounts).
- **Fonts:** `@font-face` for "Archivo" (variable, weight and width axes) and "IBM Plex Mono" 400/500, Latin and Latin Extended, pointing at the pinned `@fontsource` files; Vite bundles them as files. Declared by hand (not the packages' CSS) because the packages name the family "Archivo Variable" and the brand's stacks say "Archivo".
- **Routing: hash routes** (`#/review`), not a server fallback. The server serves files only, so a refresh asks for `/`; there is no catch-all that could ever answer under `/api`. The sign-in fragment is taken out before the router exists.
- **Static mount:** `_UiMount` at `/` declines every `/api` path. Found by test: a plain mount at `/` took any `/api` request whose route exists with another method (Starlette keeps looking after a partial match), so GET on a POST-only route became the files' 404 instead of the route's 405. Mounted last, inside `GuardMiddleware` and the headers; without `frontend/dist/index.html` the app serves the API only and logs one line (`UI files not found, so only the API is served (looked in …)`). `ui_dir=None` (most tests) is API-only and silent.
- **Theme before first paint:** `src/theme/early.ts` is the first import of `main.tsx` and sets `data-theme` before React renders (no inline script). Until it runs the stylesheet already follows Windows, and the page is empty. Residual: a manual override that differs from Windows can show one frame of the Windows background before the module runs; only a render-blocking classic script file would close that.
- **Unit tests run in Node** (no DOM package is in the 22 pins), so `theme.ts`, `client.ts` and `session.ts` take their window objects as arguments; components are checked by Playwright + axe (CI) and in the built-in browser.
- **"Pause everything"** is `aria-disabled` (not `disabled`), so keyboard users reach it and hear the tooltip.
- **Count badges:** static 0 from the placeholder; a 0 shows no badge, as in the approved mockup (the component shows the number and reads "Review, 3 waiting" when it isn't 0).
- **Sign-in in an already-open tab:** a `#t=` that arrives by `hashchange` (no page load) goes through the same steps (outside the contract's letter, same rules).

**Context7 and docs, and what changed because of them:**
- Vite 8 (`/vitejs/vite/v8.0.10`): small assets become `data:` URLs by default, which `font-src 'self'` and `img-src 'self'` refuse → `assetsInlineLimit: 0`; the module-preload polyfill is injected into the entry chunk (not inline) → turned off anyway (Edge and Chrome support it).
- Tailwind 4 (`/tailwindlabs/tailwindcss.com`): `@theme { --*: initial }` clears the defaults; `@theme inline` would bake light values into utilities, so the non-inline theme plus the unlayered `tokens.css` is used.
- MDN (`/mdn/content`): without `'unsafe-inline'`, `style-src` blocks `<style>` elements and `style=""` in HTML, and also `setAttribute("style", …)` and `style.cssText` from script; single properties set through the CSSOM (`el.style.x`, `setProperty`) are allowed. React DOM 19.3 writes styles with `style[name] =` and `setProperty` (read in `react-dom-client.production.js`; Context7's React results didn't cover it).
- Radix (`/radix-ui/primitives`, and the installed source): the menu's modal mode wraps content in `react-remove-scroll`, whose `react-style-singleton` creates a `<style>` element → refused by the CSP. So the theme menu is `modal={false}`; checked in the browser: 0 `<style>` elements with the menu open, no CSP report. Tooltip and Popper only set styles through React's `style` prop (CSSOM). **`@radix-ui/react-dialog` (pinned, unused here) uses the same scroll lock for every modal dialog** (open question 3).
- React Router 8 (`/remix-run/react-router`): `createHashRouter` + `RouterProvider` from `react-router`; `NavLink` sets `aria-current="page"`.
- TanStack Query 5: `retry` and `refetchOnWindowFocus` defaults; only a request that got no answer is retried (twice).
- Lucide 1.x (`/websites/lucide_dev_guide`): icons are `aria-hidden` by default; named imports, tree-shaken (the bundle is 466 KB, 149 KB gzip, for React, React Router, Radix, TanStack Query and the 26 icons used).
- Vitest 5: `environment: "node"`, `unstubGlobals`; Playwright 1.64: `webServer`, `emulateMedia({ colorScheme })`, console and `pageerror` events; @axe-core/playwright: `withTags`; `bypassCSP` stays false. openapi-typescript 7: the Node API (`openapiTS` + `astToString`). Biome 2.5: `files.includes` negations, `vcs.root`, `css.parser.tailwindDirectives`.

**Commands and results** (heavy ones through `tools/heavy.sh`, logs in `.logs/m1a.3-*.log`):
- `npm install --prefix frontend` (first lock): 146 packages, 0 vulnerabilities. `npm ls --depth=0`: exactly the 22 pinned versions. Then `npm ci --prefix frontend`: 146 packages, 0 vulnerabilities.
- `npx biome ci .`: 42 files, no findings. `npx tsc --noEmit -p tsconfig.json`: no errors.
- `npm test` (Vitest): **5 files, 223 tests passed** (client 24, session 27, theme 15, contrast 101, tokens 56).
- `npm run build`: tokens and brand files in step (6 files); `dist/` holds `index.html`, the JS and CSS, 4 woff2, the logo SVG, the favicons; no `data:` URL in the CSS or JS.
- `npm audit --omit=dev --audit-level=high`: 0 vulnerabilities. `npm run schema:check`: current. `npm run tokens:check`: in step.
- `npx playwright test --list`: 17 tests listed (config and specs load). **Not run** (CI only, owner's rule).
- `uv sync --locked`: ok. `uv run ruff check`: all passed. `uv run ruff format --check`: 56 files formatted. `uv run mypy`: no issues in 26 files. `uv run pytest`: **450 passed, 2 skipped, 9 deselected**. `coverage report --include=backend/shelfsync/secure/* --fail-under=90`: 100 %. `uv run bandit -r backend`: no issues.
- `npm ci --prefix brand` then `npm test --prefix brand`: **221 passed**.
- In the built-in browser, backend `frontend/e2e/server.py` on 127.0.0.1:47699 serving the build, test token in memory, tickets from the ticket route: sign-in with a real ticket works (the address becomes `/#/`; `localStorage` empty; `document.cookie` empty, the cookie is HttpOnly); a refresh stays signed in; no ticket shows the signed-out state; **no CSP violation and no `<style>` element** on any screen or with the menu and tooltips open; every resource from 127.0.0.1:47699; Archivo loaded from the bundle. Console: only "Failed to load resource" 401 (signed out) and 405 (the session check, open question 1). Keyboard pass: Skip to content, logo, Theme, Pause everything, the seven nav items, Collapse menu, the two strip tooltips, the screen's action, each with the 2 px focus ring; Enter on the theme button opens the menu on "Same as Windows", Enter picks it and focus returns. At 1024 px the nav is collapsed, nothing overflows, and the strip is one line (it ends at 843 px). Server stopped afterwards.

**Screenshots** (built-in browser; `.jpg`, also in `.logs/shots/m1a.3/`):
- `docs/05-design-system-appendix/screenshots/m1a.3/01-shell-dashboard-1440-light-whole.jpg`: the whole 1440 × 900 shell, scaled to 800 × 500
- `…/02-shell-dashboard-1440-light.jpg`, `…/03-shell-dashboard-1440-dark.jpg`: Dashboard, light and dark
- `…/04-upload-1440-light.jpg`, `…/05-review-1440-light.jpg`, `…/06-review-1440-dark.jpg`, `…/07-catalog-1440-light.jpg`, `…/08-cleanup-1440-light.jpg`, `…/09-activity-1440-light.jpg`, `…/10-settings-1440-light.jpg`: each screen's title and empty state
- `…/11-review-1440-light-override-while-windows-dark.jpg`: the Light override while Windows is dark
- `…/12-skip-link-focus-1440-dark.jpg`: the skip link with its focus ring
- `…/13-review-1024-collapsed-light.jpg`, `…/14-review-1024-collapsed-dark.jpg`: the nav collapsed at 1024 px
- `…/15-signed-out-1440-light-whole.jpg`, `…/16-signed-out-1440-dark-whole.jpg`: the signed-out state
- **Limits:** the pane returns at most 800 × 500 per capture. Files 01, 15 and 16 are the whole viewport scaled down; the others are the top-left 800 × 500 CSS px at 1:1 (the right end of the app bar, with Theme and Pause everything, isn't in them; it was checked through the page's DOM and computed styles instead). The 2× full-page capture helper can't run under the app's CSP (open question 4).

**Differences from the mockup, with reasons:**
1. No "?" help button: the help panel isn't built; a button that does nothing would mislead.
2. A Theme button in the app bar (Monitor, Sun or Moon icon): the brief puts the override there; the mockup had it only in its controls bar and Settings, App.
3. Health area with nothing connected: one dashed, muted chip "No stores or storage yet" (the mockup always had at least the S3 chip).
4. "Pause everything": dashed border and muted label, `aria-disabled`, tooltip.
5. No "N products in the catalog" under the nav and no "Sample data" tag: there's no data and nothing is sample.
6. Empty states keep the mockup's words but show an action only where it works now: Dashboard and Review "Open Upload", Activity "Upload a ZIP"; no "Add a store" (Catalog), "Sync now" and "Last check at" (Cleanup), or "Drop ZIPs above, or use Browse files" (Upload); the Dashboard shows only the latest-updates empty card (KPI tiles, drop zone, connections and chart are M3 to M5).
7. Status strip: "Last sync not yet" (new), trust ramp 0 / 50; the mockup's measured compaction steps are replaced by two CSS breakpoints (the meter and the chip latencies hide below 1152 px); at 1024 px it stays on one line.
8. The skip link is a button (an `<a href="#main">` would be read by the hash router as a screen).
9. New: the signed-out, no-answer and refused panels, and a "Not found" screen.
10. Empty-state text up to 64 characters wide with balanced lines (the mockup's 52 broke the Dashboard line one word short).

**Placeholder data** (`src/api/placeholder.ts`, marked PLACEHOLDER): counts 0 and 0; no stores; no storage; auto-apply off for the trust ramp; trust ramp 0 / 50 (fresh install; 50 from 03 D-6); last sync none; sync every 15 minutes (03 SYNC-01 default, named in Cleanup's empty state); next snapshot 02:00 (03 SYNC-03 default). No sample data anywhere. In tests only: the two stores' dot colours from 05 §2.3 (contrast test) and a throwaway ticket-shaped string.

**Proposed wording for 13** (new strings; everything else is the mockup's or 13's):
- Pause everything, tooltip until M5: "Nothing runs yet, so there's nothing to pause."
- Health area, nothing connected: "No stores or storage yet"
- Status strip before the first sync: "Last sync **not yet**"
- No answer at sign-in: "ShelfSync didn't answer, so this tab can't sign in." + "Open ShelfSync from the tray icon or the Start menu." + button "Try again"
- Refused at sign-in: "ShelfSync refused to sign this tab in (HTTP <status>)." + the same line
- Unknown address in the app: title "Not found", "There's no screen at this address.", button "Open Dashboard"
- Theme menu: label "Theme"; button name "Theme: <Same as Windows | Light | Dark>" (items from the mockup's Settings, App)
- Collapsed-nav tooltips: each item's own label; tab title "<Screen>, ShelfSync"

**`.gitignore` lines for the lead:** `frontend/playwright-report/` and `frontend/test-results/` (Playwright output). `frontend/node_modules` and `frontend/dist` are already covered by the existing `node_modules/` and `dist/` lines (checked with `git status`).

**Not verified:**
- Playwright + axe, the CSP-violation test and the keyboard test: written and listed, **not run** (CI only); CI: **not run on GitHub yet**. axe was not run locally either.
- `tsc` checks `src/` only: `@types/node` isn't in the pins, so `playwright.config.ts`, `vite.config.ts` and `e2e/*.ts` aren't type-checked (Playwright and Vite compile them; Biome lints them).
- Reduced motion and forced colours: checked in the code only (the duration tokens go to 0 ms and an unlayered rule turns transitions off), not emulated.
- Screenshots are 800 × 500 pane captures (see Limits), not 2× full-page images; dark shots exist for Dashboard and Review only (all seven routes in both themes are in the Playwright axe test).
- The ticket never in logs: covered by the unit tests (console spied, storage stubbed, error text and state checked) and by the backend's existing never-logged tests; the browser console was read and holds no ticket.
- Linux: nothing ran on Linux; the UI job's `uv run` and `npm ci` steps are as in the other jobs.

**Open questions for the lead:**
1. **"Am I signed in?" has no route.** Without a ticket (refresh, second tab) the page must know whether its cookie is still good. The contract has no such route, and adding one is the builder's lane. Until there is one, the page sends `GET /api/session/reset-token` (`SESSION_PROBE_PATH`, one place): 401 means signed out, 405 means the cookie got through (GET never resets anything). It works, but Chrome logs the 405 as a console error on every refresh, and the Playwright fixture has to excuse 401/405 on those two paths. Recommended: the builder adds `GET /api/session` (204 signed in, 401 `signed_out`, no body), then the probe and the excuse go.
2. **"A test ticket issued in-process":** `create_app` keeps its `SessionStore` inside, so the Playwright server (`e2e/server.py`) holds a throwaway token in memory and each test asks the real ticket route for a fresh ticket, as the launcher does (tickets last 60 s, so one ticket made at start-up couldn't serve 17 tests). Nothing is loosened. Confirm that reading.
3. **Radix Dialog and the CSP:** every modal Radix Dialog (and a modal DropdownMenu) injects a `<style>` element, which `style-src 'self'` refuses (the scroll lock still works through other means, but the browser reports a violation and the Playwright test fails). It matters from the first ConfirmDialog (M2+). Options for the lead: the native `<dialog>` element for modals, or Radix with `modal={false}` and our own focus handling; loosening the CSP isn't proposed.
4. **Screenshots under the CSP:** the P3.5 capture helper draws through `data:`/`blob:` images and posts to a second port; the app's CSP refuses both, by design. If 2× full-page images of the real app are wanted, the lead's pane can take them, or a later task builds a capture path that doesn't need the page's permission.
5. **Where the installer puts the UI:** `UI_DIR` is the source layout (`<repo>/frontend/dist`); M1b's packaging decides the installed path.
6. A Playwright browser (chromium 1248, dated 2026-10-11, from another project) already exists in `%LOCALAPPDATA%\ms-playwright` and matches Playwright 1.64's revision. Not used here; noted so nobody downloads a second one.
7. The Playwright test server logs its refusals ("request refused by the session check: GET /api/session/reset-token") to stderr through Python's handler of last resort, because it doesn't set up ShelfSync's log file. Test-only, path and method only.

### Fix round 1
_(designer, Opus 5.5 medium, 2026-10-27; commits `9e0fc65`, `e5891fe` on `feat/m1a.3-app-shell`; not pushed)_

**Skills and tools:** `frontend-design` loaded first; it kept the fixes inside the approved look (no new decoration; the forced-colours highlight uses the Windows menu colours). `dataviz` not loaded (no chart). Context7: Playwright (`/microsoft/playwright`): `forcedColors: "active"` and `reducedMotion: "reduce"` are `test.use` / context options, so each case is its own `describe` with `test.use`. React Router (`/remix-run/react-router`): the docs don't cover `dispose()`; the installed source (`lib/router/router.js`) shows it removes the history (`popstate`) listener and aborts pending loads, and its type marks it `@private`, so it is used and noted here. Built-in browser for every visual check.

**One line per triage row** (what changed; the test that proves it):
1. Theme menu highlight: an outline (`2px`, offset `-2px`) instead of an inset shadow, and in forced colours `Highlight` / `HighlightText` with `forced-color-adjust: none` (`app.css`). Proved by e2e "forced colours › the theme menu's highlighted item keeps a visible outline" (CI); in the pane: solid outline on the highlighted item, light and dark (shots 04, 06).
2. `#t=` in a signed-in tab: start-up moved to `src/app/boot.ts` (main.tsx calls it); `popstate` and `hashchange` listeners on `window` in the **capture** phase, added before the router exists, strip the ticket and sign in (one handler; `hashchange` finds nothing left). Proved by `boot.test.ts` (5 tests: order, capture flags, strip before POST, screen hashes left alone) and e2e "a sign-in address opened in a signed-in tab never reaches the router"; in the pane on `#/review`: a bubble-phase `popstate` listener (where the router listens) saw only `#/`, no "Not found" heading appeared, one API call (`/api/session`), then a refresh stayed signed in.
3. Windows theme on every screen: "Same as Windows" now removes `data-theme`; the two dark rules in `app.css` (`.card`, `.store-dot`) have the media-query form beside the `[data-theme="dark"]` form, as `tokens.css` does. Proved by `theme.test.ts` ("system" removes the attribute) and e2e "the signed-out state follows a Windows light/dark switch live, with no reload"; in the pane: the signed-out page went from `rgb(246,247,245)` to `rgb(13,22,19)` with no reload (shots 01, 02).
4. Cache headers: `_UiFiles(StaticFiles)` in `app.py` sets `no-cache` on the page and unhashed files and `public, max-age=31536000, immutable` on `/assets/*` (200 and 304); `/api` keeps `no-store`. Proved by `tests/test_static_ui.py` (4 new tests, 304 included); `curl -I` on the real server: `/` `cache-control: no-cache` (with an ETag), `/assets/index-DKjBaNFP.js` `cache-control: public, max-age=31536000, immutable`, `/api/health` `no-store`.
5. "Try again": the `unreachable` state carries `canRetry` (false after a ticket sign-in, true after a session check); SessionGate shows the button only when true. Proved by `session.test.ts` and e2e "no answer to a ticket sign-in offers no Try again" / "no answer to the session check offers Try again, which checks once more"; in the pane, with the server stopped, an in-tab ticket gave "ShelfSync didn't answer…" with no button (shot 09).
6. Router disposal: the router is made in an effect when the tab is signed in and `dispose()`d in its cleanup (sign-out, a new sign-in, StrictMode's extra mount). Proved in the pane by the in-tab sign-in in row 2 (old router gone, new one at `#/`); no unit test (no DOM package in the pins).
7. Weak tests: the real start-up order is tested through `boot()` (`boot.test.ts`); the contrast test reads `--color-appbar-bg/fg/muted` from the generated `shelfsync-tokens.css` (light `:root`, dark block, and the media-query block); e2e `forcedColors` (axe on the signed-out page and the shell, plus the menu outline) and `reducedMotion` (no element with a running transition, the menu outline, axe). **Found while doing this:** Vitest turned every CSS import into an empty string, `?raw` included, so the "tokens.css is brand's, byte for byte" test and the no-hand-typed-colour scan of CSS files compared nothing. `vitest.config.ts` now lets `*.css?raw` through, and `tokens.test.ts` asserts the copy isn't empty; both pass on the real content.
8. IBM Plex Mono Latin Extended 400 and 500 from the pinned `@fontsource/ibm-plex-mono` (no new package), with the package's own unicode range. Proved by `fonts.test.ts` (each face has both subsets; 6 faces, all bundled woff2); the build emits the two new files.
9. Playwright output: `trace: "off"`, `video: "off"`, screenshots on failure, HTML report. Sign-in addresses are opened from `about:blank` through `page.evaluate` (never `page.goto`, whose URL goes into step titles), and ticket checks assert booleans, so no failure message repeats a ticket. New `e2e/check-output.mjs` reads `playwright-report/` and `test-results/`, opens the report's embedded base64 zip, and fails on a ticket-shaped `#t=` value, a `Bearer` value, a `"ticket"` JSON value or the run's token; the CI job makes a masked throwaway token, runs the check on failure, and uploads only if the check passed. Proved locally on three fabricated reports: clean exit 0, one with a ticket address exit 1, one with a Bearer header exit 1.
10. `rampPercent()` (`src/lib/ramp.ts`): 0 for a target of 0, negative or non-finite values (`ramp.test.ts`, 10 cases). `ErrorCode` is the schema's `ErrorResponse["error"]`; the runtime list is a `Record<ErrorCode, true>`, so tsc fails if they drift, and `client.test.ts` compares it with the enum in `schema.d.ts`. Every `create_app(` call in `tests/` passes `ui_dir` (four files changed) and `test_every_test_names_its_ui_folder` enforces it; `e2e/server.py` passes `ui_dir=UI_DIR`. `useTheme` no longer writes during render: early.ts applies the stored choice before React, and a new choice is applied once in the menu's event handler (not an effect: an event handler is where React wants a side effect of a click, and it needs no first-run skip); the `matchMedia` listener is gone (CSS follows Windows).
- **`GET /api/session/status`** (`api/session.py`, `SESSION_STATUS_PATH`): 204 with no body, a normal route not in `SESSION_EXEMPT_PATHS`, so the guard answers 401 `signed_out` first. The page's `checkSession` uses it (204 signed in, 401 signed out, anything else refused). The `reset-token` workaround is gone from `session.ts`, its tests, `e2e/support.ts` (only 401 on `/api/session` and `/api/session/status` is excused now; no 405) and `tests/test_static_ui.py`. Proved by `tests/test_session_routes.py` (5 new tests: 204 and no-store, 401 without a cookie, 401 with a stale or made-up cookie, not exempt, 405 for writes), the route-table test (`checked >= 2`) and `session.test.ts`; in the pane a refresh made one `GET /api/session/status` → 204 and the console has no 405.

**Commands and results** (heavy ones through `tools/heavy.sh`, logs `.logs/m1a.3-fix-*.log`):
- `npm ci --prefix frontend`: 0 vulnerabilities. `npx biome ci .`: 48 files, no findings. `npx tsc --noEmit -p tsconfig.json`: no errors.
- `npm test` (Vitest): **8 files, 254 passed** (boot, client, session, theme, ramp, fonts, contrast, tokens).
- `npm run build`: passes; `dist/` adds the two Plex Mono Latin Extended files; no `data:` URL in the CSS or JS.
- `npm run schema` then `npm run schema:check`: current (the status route is in `schema.d.ts`). `npm run tokens:check`: in step. `npm audit --omit=dev --audit-level=high`: 0 vulnerabilities.
- `npx playwright test --list`: **24 tests** listed. Not run (CI only).
- `uv run ruff check`: passed. `uv run ruff format --check`: 56 files formatted. `uv run mypy`: no issues in 26 files. `uv run pytest`: **466 passed, 2 skipped, 9 deselected** (the one warning is Starlette's existing httpx deprecation).
- Built-in browser against `frontend/e2e/server.py` on 127.0.0.1:47699 (throwaway token in a scratch file, tickets from the ticket route): every row above; 0 `<style>` elements; keyboard: Enter on Theme opens on "Same as Windows", arrows move the outlined highlight, Enter picks and focus returns to the button; 1024 px collapsed, no overflow. Console: one 401 from the first signed-out load and one `ERR_CONNECTION_REFUSED` after I stopped the server on purpose; nothing else. Server stopped afterwards (process on port 47699 ended).

**Screenshots** (`.logs/shots/m1a.3-fix/`, pane captures, 800 px wide):
- `01-signed-out-light.jpg`: signed out, Windows light
- `02-signed-out-after-windows-dark-no-reload.jpg`: the same page after Windows switched to dark, no reload
- `03-review-1440-dark-after-in-tab-sign-in.jpg`: the shell after the signed-in-tab `#t=` and a refresh
- `04-theme-menu-highlight-dark.png`, `06-theme-menu-highlight-light.png`: the outlined highlight
- `05-review-1440-light-override-focus-returned.jpg`: Light override while Windows is dark, focus back on Theme
- `07-review-1024-collapsed-light.jpg`: 1024 px, nav collapsed
- `08-review-1440-light-same-as-windows.jpg`: back on "Same as Windows"
- `09-no-answer-to-ticket-no-try-again-light.jpg`: no answer to a ticket, no Try again

**Not verified:**
- The Playwright suite (24 tests, including the new forced-colours, reduced-motion, signed-in `#t=` and abort cases) and the CI job: written and listed, **not run** (CI only); not run on GitHub yet.
- Forced colours: the pane can't emulate them, so the `Highlight` rule was checked in code only; the e2e case runs in CI.
- `check-output.mjs` was run against fabricated reports, not a real failing Playwright report.
- Row 6 has no automated test (needs a DOM); checked in the pane only.

**Observed, not changed (outside the triage):** switching theme while the screen is open, the buttons' background eases over 120 ms while their text colour switches at once, so one frame can show dark text on a still-dark button (seen once in a capture at 1024 px; settled a moment later). Adding `color` to the `.btn` transition, or no transition on a theme switch, would remove it.

**For the lead:** `npx playwright test --list` writes `frontend/playwright-report/index.html`; the `.gitignore` lines proposed above cover it (I deleted the one it made).

## 5. Review
**Review** _(reviewer, Opus 5.5 high, `code-review` + `security-review` by hand on `872dea4..3d6007e`, visual review in the built-in browser, 2026-10-27)_ **SEND BACK** for one high (expected APPROVE once fixed). No high-confidence vulnerability; static mount, sign-in, CSP, tokens, landmarks and the CI job checked sound; geometry matches the mockup (app bar 56, nav 248, items 44). Ran: `npm ci`, Biome, tsc, Vitest 223, build, `schema:check`, `npm audit` 0, `pytest` 450 passed. Not run: Playwright and axe (CI only). Note: `frontend-design` was not actually loaded by the reviewer; the visual review used 05 and the mockup directly.

**Triage** _(lead, Opus 5.5 medium, 2026-10-27; Tier B)_

| # | Sev | Finding | Decision |
|---|---|---|---|
| 1 | H | Theme menu highlight invisible in forced colours | **Fix now:** an outline on `.menu__item[data-highlighted]` (and `Highlight` in the forced-colours block) |
| 2 | M | `#t=` in a signed-in tab reaches the router (`popstate` fires before `hashchange`) | **Fix now:** a capture-phase `popstate` listener on `window`, registered before the router, strips `#t=`; e2e case for a signed-in tab |
| 3 | M | Signed-out and error screens don't follow a Windows theme change | **Fix now:** "system" sets no `data-theme`; CSS media queries do it (dark-only rules moved to the media-query form) |
| 4 | M | The page has no `Cache-Control`; after an update a cached `index.html` asks for old assets | **Fix now:** `Cache-Control: no-cache` outside `/api`, `public, max-age=31536000, immutable` on `/assets/*` (hashed names); tests |
| 5 | L | "Try again" can't succeed after a failed ticket sign-in | **Fix now:** hide it when the attempt was a ticket |
| 6 | L | Old hash router never disposed | **Fix now:** `router.dispose()` in cleanup |
| 7 | L | Weak tests: ticket-order test checks its own order; app-bar contrast uses palette names; forced colours and reduced motion untested | **Fix now:** test `main.tsx`'s real order; contrast test reads the generated `--color-appbar-*` mapping; Playwright cases with `forcedColors: "active"` and `reducedMotion: "reduce"` (axe plus a visible-focus check on the menu) |
| 8 | L | IBM Plex Mono ships Latin only | **Fix now:** add the Latin Extended subset from the pinned `@fontsource/ibm-plex-mono` |
| 9 | L | A kept Playwright trace holds the test token and tickets, uploaded on a public repo | **Fix now:** no traces; keep screenshots and the HTML report only, and check the report holds no `Authorization` header or `#t=` |
| 10 | L | `NaN%` at a trust-ramp target of 0; `ERROR_CODES` repeats the schema enum; `ui_dir` defaults to `UI_DIR` in tests; `useTheme` writes during render | **Fix now** (derive the codes from the generated schema; tests pass `ui_dir` explicitly; effects, applied once) |
| 11 | L | Activity empty-state wording differs between 13 and the mockup | **Keep the mockup's text**; the lead updates 13 at integration |
| — | — | "Am I signed in?" route | **Fix now:** new `GET /api/session/status` (204 signed in, 401 not), a normal session-protected route (no exemption, so the method-blind exemption on `/api/session` isn't widened); remove the `reset-token` workaround from `session.ts`, its tests and `e2e/support.ts`; update `tests/test_static_ui.py`. `api/session.py` may change for this route only |
| Q | — | Designer's questions | Test server asking the real ticket route: **confirmed**. Radix Dialog: modals use native `<dialog>` with `showModal()`; decided in the M2 brief, CSP unchanged. Pane screenshots are enough; the CSP isn't weakened for a capture helper. `UI_DIR` from `paths.py` and a missing UI as an error in the installed app → **M1b brief**. Badges hidden at 0 as in the mockup. `.gitignore` lines: lead adds at integration |

Fixes by the `designer` at medium, then a re-check (code and visual) by the `reviewer` at medium.

## 6. Integration notes
_(empty)_

## 7. Handover
_(lead, 2026-10-27)_ Brief written at Opus 5.5 medium. Waits for M1a.2's fix round and re-check, then the designer starts from the head of `feat/m1a.2-security`.
