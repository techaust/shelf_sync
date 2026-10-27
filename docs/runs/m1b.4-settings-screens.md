Status: open (brief written 2026-10-28; the owner's standing instruction of 2026-10-28 covers build, review and merge)
Tier: C code with A effort, as the M1b plan says ([m1b.2 §0](m1b.2-updater.md)): the first build of these screens
Usage: lead `claude-opus-5-5/high` wrote this brief (the effort was left at high overnight; see 10)

# M1b.4: Settings › Updates and Settings › App screens

The M1b plan is in [runs/m1b.2-updater.md](m1b.2-updater.md) §0. The APIs these screens use are merged: Updates and the GitHub token (m1b.2, #16) and App settings (m1b.3).

## 1. Brief

### PRD IDs
- UI-SET Updates (SYS-06, SYS-07, SET-04) and UI-SET App (SET-06, LOG-01).

### Agent and skills
- **`designer`:** Opus 5.5 at high, in its own worktree. It never pushes. Load `frontend-design` before designing. Use Context7 for React and Radix if an API is unclear.
- **Don't load** `code-review` or `security-review`: the reviewer runs them.
- **Screenshots:** the built-in browser pane only (CLAUDE.md rule 10). No other agent uses a browser while the designer runs.

### What to build
1. **The Settings shell** at `#/settings/<sub>`, as the approved mockup has it (`docs/05-design-system-appendix/mockup/js/screens-b.js`, `settings()`, lines 502–675):
   - the sub-nav with all six entries (Stores, Storage, Rules, Updates, Backup, App);
   - Stores, Storage, Rules and Backup show a plain "coming in a later version" panel for now: propose its wording in the report;
   - the focus moves to the page title on a sub-nav change, as the mockup does.
2. **Settings › Updates** (`updatesPage()` in the mockup), wired to `GET /api/updates`, `POST /api/updates/check`, `POST /api/updates/install`, `POST /api/updates/rollback`, and the GitHub token routes in `api/secrets.py`:
   - every state the API can report, with the wording in [m1b.2 §3](m1b.2-updater.md) ("Proposed owner-facing wording"), which the lead adds to 13 §3 in this task as "Lead (proposed)";
   - the empty state uses the new wording (the token is optional), not the mockup's;
   - the development-copy and no-key states turn the buttons off and say why;
   - **Install:** a "preparing" state while the download and check run; "Install {v} and restart" opens a ConfirmDialog; after the 202, a "ShelfSync is restarting" panel that polls `/api/health` and reloads when the new version answers;
   - **Roll back:** the ConfirmDialog with the two wordings (files only, or a database change with the date). The second one sends what the API's `confirm_required` asks for;
   - the GitHub token in a SecretField: show only the API's masked form, Save, Remove, the expiry notice, and the github_pat_ refusal;
   - drop "Installs in under a minute" (13 §6: not measured). Use "This takes about a minute." only inside the install dialog, as the m1b.2 wording has it;
   - each API error code shown with its 13 wording.
3. **Settings › App** (`appPage()` in the mockup), wired to `GET`/`PUT /api/settings/app` and `POST` reset-token in `api/session.py`:
   - Theme (system, light, dark): applied at once through the existing `theme/` module, and saved. The app bar's ThemeMenu and this page always show the same value;
   - Start with Windows and Notifications as Switches. When `start_with_windows_applied` is false, say it was saved but Windows wasn't changed;
   - Port (47615–47624) and "Keep logs for" (1–365 days), checked in the form before saving, with the API's limits;
   - Save; when `restart_needed` is true, say the new port is used after the next start;
   - Notifications: say nothing about which notifications exist yet (SYS-05 is M5); the mockup's helper line stays;
   - Reset access token in the danger zone, behind a ConfirmDialog with the 13 §6 wording; after it, the tab is signed out (the existing session gate handles it);
   - `installed: false` (a development copy): Start with Windows is shown off and disabled, with a one-line reason.
4. **Shared parts** in `frontend/src/components/`:
   - **ConfirmDialog** on the native `<dialog>` element (`showModal()`), with a focus trap from the browser, Esc to cancel, the focus going back to the opener, and the destructive button styled `is-danger`;
   - **SecretField:** never puts a stored secret in the page; shows the masked form from the API; a password input only for a new value; Save and Remove;
   - **Switch:** `role="switch"` with `aria-checked`, a visible label and a helper line.
   - Use the existing Radix packages only where they already fit (Tooltip). **No new npm package.**
5. **The API client:** use the generated types in `src/api/schema.d.ts` and `client.ts`'s typed calls and error codes. Every write sends what the guard needs (the client does already).
6. **Strings:** every new owner-facing string listed in the report with its 13 wording.

### Done means
- In `frontend/`: `npm run lint`, `npm run typecheck`, `npm test` (Vitest: each state of both screens, the dialogs' keyboard behaviour, the form limits, the restart poll with a fake clock) and `npm run build` pass. `npm run schema:check` passes.
- The Python checks still pass (`uv run pytest`), since the server serves `frontend/dist/`.
- **Screenshots** in the built-in browser pane, light and dark, at 1280 px wide: Updates (empty, up to date, ready, error, development copy) and App (normal, Start with Windows not applied, a field error). Use the dev server with mocked API answers, or the real server with a throwaway `SHELFSYNC_DATA_DIR`. Save them under `docs/runs/m1b.4-shots/` only if they're small PNGs; otherwise just report what was checked.
- axe-style checks by hand: labels, focus order, contrast from the tokens (the contrast test).
- The designer report (§4) lists files, commands and results, what wasn't verified, and the 13 wording.

### Out of scope
- Stores, Storage, Rules and Backup pages (M2 and M5).
- An "update ready" toast (M5).
- Changing the port live.

## 4. Designer report
_(designer)_

## 5. Review
_(reviewer)_

## 6. Integration notes
_(lead)_

## 7. Handover
_(lead, 2026-10-28)_ Brief written; the designer starts once m1b.3 is merged.
