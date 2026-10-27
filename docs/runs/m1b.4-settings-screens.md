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
   - the GitHub token in a SecretField. The API never returns the token, masked or not ([11](../11-decisions.md), 2026-10-27): show only whether one is saved and its expiry, plus Save, Remove, the expiry notice and the github_pat_ refusal;
   - drop "Installs in under a minute" (13 §6: not measured). Use "This takes about a minute." only inside the install dialog, as the m1b.2 wording has it;
   - each API error code shown with its 13 wording.
3. **Settings › App** (`appPage()` in the mockup), wired to `GET`/`PUT /api/settings/app` and `POST` reset-token in `api/session.py`:
   - Theme (system, light, dark): applied at once through the existing `theme/` module, and saved. The app bar's ThemeMenu and this page always show the same value;
   - Start with Windows and Notifications as Switches. The save answers `start_with_windows_result` (`applied`, `not_installed` or `failed`). On `failed`, say it was saved but Windows wasn't changed. On `not_installed`, give the development-copy reason below. Turn Save off while a save is in flight;
   - Port (47615–47624) and "Keep logs for" (1–365 days), checked in the form before saving, with the API's limits;
   - Save; when `restart_needed` is true, say the new port is used after the next start;
   - Notifications: say nothing about which notifications exist yet (SYS-05 is M5); the mockup's helper line stays;
   - Reset access token in the danger zone, behind a ConfirmDialog with the 13 §6 wording; after it, the tab is signed out (the existing session gate handles it);
   - `installed: false` (a development copy): Start with Windows is shown off and disabled, with a one-line reason.
4. **Shared parts** in `frontend/src/components/`:
   - **ConfirmDialog** on the native `<dialog>` element (`showModal()`), with a focus trap from the browser, Esc to cancel, the focus going back to the opener, and the destructive button styled `is-danger`;
   - **SecretField:** never puts a stored secret in the page; shows "saved" or "not set" from the API; a password input only for a new value, cleared after saving; Save and Remove;
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
_(designer: Opus 5.5 high, 2026-10-28, worktree branch `worktree-agent-a133ea61ee2221031` from `feat/m1b.3-app-settings` at 3c125d2)_

**Skills and tools.** `frontend-design` loaded before designing. What it changed:
- The design is restrained to the approved mockup: no new decoration, and the 45° cut stays where 05 §4 puts it.
- There is one moving part, the restart panel's thin progress bar, which runs only while ShelfSync is away. Reduced motion stops it.
- Two redundancies came out after the browser pass: the token's expiry is no longer shown twice when its notice is up, and a lasting switch result now carries its time, so it can't read as new days later.

`dataviz` wasn't needed (no chart or KPI tile). Context7 wasn't used: no API was unclear. React 19's static markup and react-router's exports were checked by running them. `code-review` and `security-review` were not loaded, as the brief says. No npm package was added.

### What was built
- **The Settings shell.** It lives at `#/settings/<page>`, and `#/settings` opens Stores. It has the six-entry sub-nav with the mockup's icons.
  - Stores, Storage, Rules and Backup show a plain "later version" panel.
  - An unknown page shows Not found.
  - After a navigation the focus goes to the sub-page's h2. AppShell now prefers `[data-nav-focus]` over the h1, which is what the mockup does.
- **Settings › Updates.** It is wired to GET `/api/updates`, the check, install and rollback POSTs, and PUT/DELETE `/api/secrets/github-token`.
  - It shows every state: loading, load failed, empty, up to date, no release, being downloaded, ready, checking, busy, development copy, no key, every check outcome, every last-switch outcome, every API error code, and the token notice.
  - Install goes ConfirmDialog → "preparing" (button busy, one line) → the restart panel. The panel polls `/api/health` every 2 s and reloads.
  - Roll back uses the files-only or the database wording, and sends `confirm_data_loss` when the database changed. A 422 `confirm_required` refreshes the page and opens the dialog again.
  - The GitHub token is in a SecretField: saved or not set, and the expiry when GitHub gave one.
  - "Installs in under a minute" is gone. "This takes about a minute." appears only in the install dialog.
- **Settings › App.** It is wired to GET/PUT `/api/settings/app` and POST `/api/session/reset-token`.
  - Theme is one store shared with the app bar's ThemeMenu. A choice is applied at once and saved from either place.
  - Start with Windows and Notifications are Switches. Start with Windows is locked off with a reason in a development copy.
  - Port and log days are checked before saving with the API's limits.
  - Save is off while a save runs. Its result appears beside Save: applied, applied with a new port, `failed`, or `not_installed`.
  - Reset access token sits behind a danger ConfirmDialog that starts on Cancel. After it the tab is signed out through the session store.
- **Shared parts.**
  - `ConfirmDialog` uses a native `<dialog>` with `showModal()`. Esc is Cancel, and waits while the action is sent. The focus goes back to the opener.
  - `SecretField` never holds a stored value, not even a mask. It has a password input for a new value, emptied after saving, plus Save and Remove.
  - `Switch` is a button with `role="switch"` and `aria-checked`, a `<label>` and a helper line. When locked it stays focusable through aria-disabled.
  - There are also `Alert` and `FieldError`.

### Decisions taken (routine; for 11 as "Lead (proposed)")
1. **The theme is saved from both places, and the saved one wins at load.**
   - A theme change sends a fresh GET's stored values with only the theme changed, so it never saves a field still being edited.
   - All App writes go one at a time (`settingsWriter`).
   - localStorage stays the early-paint cache.
2. **Install and Roll back close their dialog on confirm; the page shows the waiting.**
   - If the install or rollback POST gets no answer at all, that is taken as "restarting", since ShelfSync may close before it answers. The health poll finds out which version comes back.
3. **When the page reloads.** It reloads when the target version answers, or when ShelfSync answers again after it was seen gone (`kept_old` or `not_switched`; the reloaded page shows the result).
   - The old copy answering before it closes never triggers a reload.
   - After 3 minutes it shows one extra line and keeps asking.
4. **Switch results stay visible.** A good last switch is a quiet line with its time. A bad one is a notice with its time until the next switch.
5. **Reason codes without 13 wording show only the outcome line.** These are `old_copy_hung`, `junction_error`, `target_invalid` and `from_mismatch`. A joined reason (`a+b`) is read by its first code. Nothing from the API is echoed as text.
6. **Roll back with a changed database and no matching backup is off.** It uses 13's `backup_missing` line as the reason.
7. **A development copy keeps the stored Start with Windows value on save.** It is shown off, but a save never changes it.
8. **Removing the token has no dialog.** It can be added again at once.

### New owner-facing strings (proposed in m1b.4; everything else is quoted from 13 §3 or the mockup, see `frontend/src/screens/settings/wording.ts`)
**The "later version" panels** (13 §2's empty-state pattern):

| Page | First line | Second line |
|---|---|---|
| Stores | "Store settings come in a later version of ShelfSync." | "This is where you'll add each store's address and Shop Manager key, and test the connection." |
| Storage | "Storage settings come in a later version of ShelfSync." | "This is where you'll add the S3 bucket ShelfSync uploads to, and test its keys." |
| Rules | "Rules come in a later version of ShelfSync." | "This is where you'll set auto-apply, its brakes and the words used for matching." |
| Backup | "Backup settings come in a later version of ShelfSync." | "This is where you'll export and import your settings, and choose how long backups are kept." |

**Updates:**
- Install dialog title: "Install ShelfSync <v>?"
- While the files are checked: "Checking the files of <v> before it's installed."
- Restart panel: "ShelfSync is restarting" (the brief's words), then "This tab reloads when ShelfSync <v> answers."
- After 3 minutes: "ShelfSync hasn't answered yet. If it doesn't open by itself, open it from the Start menu."
- The status can't be loaded: "ShelfSync didn't answer, so the update status can't be shown." or "ShelfSync refused to show the update status (HTTP <status>)." Both come with "Try again".
- Any other error code: "ShelfSync refused that (HTTP <status>), so nothing was changed." No answer: "ShelfSync didn't answer, so nothing was changed."
- A check problem with no version known (after a restart): "An update was found but refused: …" and "An update couldn't be downloaded. …".

**The token:**
- "Not set", and "Expires on <date>." beside "Saved".
- "ShelfSync didn't answer, so the token wasn't saved." and "ShelfSync didn't answer, so the token wasn't removed."

**App:**
- Development copy: "This copy of ShelfSync runs from source, so it can't start with Windows."
- Field limits: "Use a port from 47615 to 47624." and "Use a number of days from 1 to 365."
- After a save:
  - "Settings saved." (plus "The new port is used after the next start." when the port changed);
  - "Settings saved, but Windows wasn't changed: Start with Windows couldn't be set. Save again to try once more."
- A save fails: "ShelfSync didn't answer, so nothing was saved." or "ShelfSync refused the settings (HTTP <status>), so nothing was saved."
- The theme isn't saved: "The theme applies to this tab, but ShelfSync didn't save it."
- The app settings can't be loaded: "ShelfSync didn't answer, so the app settings can't be shown." or "ShelfSync refused to show the app settings (HTTP <status>)."
- The reset fails: "ShelfSync didn't answer, so the access token wasn't reset." or "ShelfSync refused the reset (HTTP <status>), so the access token is unchanged."

**From the mockup, kept:**
- The page and dialog: "Save app", "GitHub token (read-only)", "Replace", "Remove", "Paste the new value", "Close".
- The token field's hint: "Kept in Windows Credential Manager. It's never shown again or sent to this page."
- The App helper lines.
- The reset texts (13 §6).

**{date} format:** "28 October 2026 at 09:30 India Standard Time" (local time with the zone's long name).

### Files
- New in `frontend/src`:
  - `api/`: `settings.ts`, `settingsWriter.ts`
  - `app/`: `services.tsx`
  - `components/`: `Alert.tsx`, `ConfirmDialog.tsx`, `dialog.ts`, `FieldError.tsx`, `SecretField.tsx`, `Switch.tsx`
  - `lib/`: `restartPoll.ts`
  - `screens/settings/`: `Settings.tsx`, `UpdatesPage.tsx`, `UpdatesView.tsx`, `updatesModel.ts`, `AppPage.tsx`, `AppView.tsx`, `forms.ts`, `wording.ts`
  - `styles/`: `settings.css`
  - `theme/`: `useSavedTheme.ts`
- Changed: `app/App.tsx` (services provider), `app/router.tsx`, `components/AppShell.tsx`, `components/ThemeMenu.tsx`, `lib/time.ts`, `screens/screens.tsx` (old placeholder removed), `styles/app.css` (import), `theme/useTheme.ts` (one shared store).
- Tests (new):
  - `api/settings.test.ts`
  - `components/dialog.test.ts`
  - `lib/restartPoll.test.ts`
  - `screens/settings/forms.test.ts`, `updatesModel.test.ts`, `views.test.ts`
  - plus new pairs in `styles/contrast.test.ts`
- `e2e/shell.spec.ts`: the theme test waits for the theme's save before it reloads, so the reload can't cut it off.

### Commands and results (this PC)
- `npm run lint`: passed (74 files).
- `npm run typecheck`: passed, after one fix in `views.test.ts`.
- `npm test`: 503 passed in 14 files, then the view tests again after the typecheck fix: 26 passed.
- `npm run build`: passed. Vite now warns the main chunk is 506 kB (over its 500 kB advice). That is a warning, not a failure, and nothing was split.
- `npm run schema:check`: current.
- `uv run pytest`: 1437 passed, 16 skipped, 49 deselected.

All of these ran through `tools/heavy.sh` except the targeted Vitest and tsc re-runs. `UV_PYTHON_DOWNLOADS=never` was set, and `uv sync --locked` was run in the worktree first.

### Screenshots (built-in browser pane, not committed: 800-px-wide JPGs of the pane, not 2× PNGs)
They are in `.logs/shots/m1b.4/`, at a 1280 × 900 viewport unless the name says 1024. They were taken against the Vite dev server over `frontend/` with **mocked, sample API answers** from a scratch config outside the repo. There was no real server, no GitHub call and no real token; the sample versions are 0.2.0, 0.3.0 and 0.1.4.
- Updates, light: `updates-empty-light-1280.jpg`, `updates-uptodate-light-1280.jpg`, `updates-ready-light-1280.jpg`, `updates-error-light-1280.jpg`, `updates-development-light-1280.jpg`
- Updates, dark: `updates-empty-dark-1280.jpg`, `updates-uptodate-dark-1280.jpg`, `updates-ready-dark-1280.jpg`, `updates-error-dark-1280.jpg`, `updates-development-dark-1280.jpg`
- App: `app-normal-light-1280.jpg`, `app-normal-dark-1280.jpg`, `app-field-error-light-1280.jpg`, `app-field-error-dark-1280.jpg`, `app-start-not-applied-light-1280.jpg`, `app-start-not-applied-dark-1280.jpg`, `app-development-light-1024.jpg`
- Extras: `dialog-install-light-1280.jpg`, `dialog-rollback-database-light-1280.jpg`, `dialog-reset-error-light-1280.jpg`, `updates-preparing-light-1280.jpg`, `updates-install-refused-light-1280.jpg`, `updates-restarting-light-1280.jpg`, `settings-stores-later-light-1280.jpg`, `updates-loading-dark-1024.jpg`

### Checked by hand in the pane
- **Dialogs.** Esc closes them and the focus returns to the opener. Danger dialogs start on Cancel, others on the confirm button. Enter confirms.
- **Install flow.** Preparing, then a 409 with its 13 line; preparing, then the restart panel, with the focus on its title.
- **Token.** A wrong shape is refused before sending. A sample-shaped value saves, the input is emptied, and the focus moves to Replace. Remove moves the focus to the input and says "Token removed."
- **Theme.** A choice on the App page updates the app bar's menu, `data-theme`, localStorage and the saved setting; the other way round too.
- **Keyboard.** The Tab order on App is theme, Start with Windows (locked but focusable), Notifications, Port, Keep logs for, Reset, Save.
- **1024 px.** No horizontal overflow, and the form fields stack.
- **Console.** No errors apart from the mock's deliberate 409.
- **Contrast.** Every new tinted fill (alerts, pills, the update card, the selected theme card, switches, danger, progress) is now in the contrast test, light and dark, and passes.

### Not verified
- Playwright + axe (CI only), including my one-line change to the e2e theme test.
- Screen readers and forced colours (a forced-colours rule for the switch was added but not looked at).
- The modal backdrop shows in the computed style but not in pane screenshots.
- A real install, roll back and health poll against the switcher.
- The real server with a throwaway data folder: the mock covered every state.

### Open questions for the lead
1. **After a restart, the reloaded tab is signed out.** Sessions are in memory, and the switcher opens a new signed-in tab. Should the restart panel say so, or should the old tab close itself or just stop polling?
2. **Duplicate headings.** The mockup's "App" card title repeats the "App" sub-page heading; I kept it. Should it go?
3. **The token guide.** The mockup's "How to make the token" guide button is left out until the help panel exists.
4. **The 13 rows.** 13 §3 rows for the strings above, and 11 rows for the decisions, are the lead's to add.

## 5. Review
_(reviewer)_ The review itself (SEND BACK, 7.5/10, 21 items) reached the designer through the lead's message. The fixes are below.

### Review fixes
_(designer, 2026-10-28; worktree head before: 30eeaca)_ "Test" names the test that covers the change. "Pane" means it was checked in the built-in browser pane against the mocked API.

| # | Level | Fix | Test |
|---|---|---|---|
| 1 | High | When the restart poll sees ShelfSync again, it asks `GET /api/session/status` with a plain request that never signs the tab out. A 401 means a new copy answered: the poll stops and the panel says "ShelfSync is back" / "It opened in a new tab, signed in. You can close this one." A 204 means the old copy is still running: the poll waits while `GET /api/updates` reports `busy`, then reloads (the not_switched case). The panel's waiting line is now "When ShelfSync is back, it opens in a new tab." | `restartPoll.test.ts` (new_tab; the 204 wait then reload); `switchStore.test.ts` (back: true; reload); `views.test.ts` (the back panel); pane |
| 2 | High | The ConfirmDialog test passes its child as `createElement`'s third argument. The component's type is cast to say children come from there. There is no biome-ignore. `npm run lint` passes | lint |
| 3 | Med | `dialog.ts` also listens for `close`. If React still wants the dialog open and the action is being sent, it opens again (`showModal()`). Otherwise React is told, through onCancel, and the focus goes back. A late `close` after a reopen is ignored | `dialog.test.ts` (second Esc while busy reopens; browser close tells React; our own close reports no Cancel) |
| 4 | Med | `createThemeSync`: each choice holds a pending count until its save answers. A server theme (from a refetch, or an older save's answer in the cache) applies only when nothing is pending | `actions.test.ts` (light → system → light → system: only the last is applied; nothing pending applies) |
| 5 | Med | The roll back words are chosen from `databaseChanged` alone, the same flag that sends `confirm_data_loss`. Without the backup's time the database line goes without its date. A changed database never reads "your data stays as it is" | `actions.test.ts` (roll back words, three cases); `views.test.ts` (dialog body) |
| 6 | Med | The roll back dialog uses 13 §6's owner-decided rows for both cases, with "<version>" being the installed version. Kept: "ShelfSync will close and open again." first, "A copy of the current data is kept in the backups folder." after the database text, and the buttons "Roll back" and "Cancel" | as 5; pane, light and dark |
| 7 | Med | Each poll question (health, session, busy) is ended after 3 s through an AbortSignal; the API client's `request` and `get` now take one. "Late" is its own 3-minute timer, so it fires even while a question hangs. A quick restart of the old version is caught by the session check (401) | `restartPoll.test.ts` (time limit with a hanging question; late on its own timer; quick restart; stop clears both) |
| 8 | Med | `switchStore.ts` is a module store, like themeStore. It holds the phase and owns the restart poll, so leaving Settings › Updates and coming back never stops them. A second run while switching is refused | `switchStore.test.ts`; pane (App and back: the panel is still there) |
| 9 | Med | Updates and App show the failure card only when `isError && !data`. A failed refresh keeps the page and adds "ShelfSync didn't answer just now, so this may be out of date." | `views.test.ts` (stale notice with the page kept) |
| 10 | Med | `actions.ts` holds checkNow, saveToken, removeToken, resetAccess, saveApp and pollAnswers as plain functions. `switchStore.run` holds switchTo. SecretField's Save is `submitSecret` | `actions.test.ts`; `switchStore.test.ts`: no answer → restarting; confirm_required → asks again; a 409 → its 13 line; Reset → signed_out; SecretField empties after a save and keeps after a failure; theme sync |
| 11 | Low | The password input is uncontrolled. Its value is read from the ref on submit and cleared through the ref, never kept in state or the value attribute | `views.test.ts` (no value attribute on the input); `actions.test.ts` (submitSecret) |
| 12 | Low | `num` added to the dialog titles (Install, Roll back), the roll back body and alert, and the restart panel's line | `views.test.ts` |
| 13 | Low | The optional-token line is hidden in a development copy (`showEmpty`) | `updatesModel.test.ts`; `views.test.ts` |
| 14 | Low | Install's `aria-describedby` points at the no-key notice when the build has no key | `views.test.ts`; `updatesModel.test.ts` (`why: "no-key"`) |
| 15 | Low | The busy notice reuses API_ERRORS.busy (`BUSY_LINE`) | `updatesModel.test.ts` |
| 16 | Low | No answer is never stated as an outcome. The new lead wording is listed below | `actions.test.ts`; `updatesModel.test.ts` |
| 17 | Low | ConfirmDialog opens and closes only on a change of `open`, through a ref guard. A change of `danger` while open moves nothing | the dialog tests; pane (Esc and focus back still work) |
| 18 | Low | An Install or Roll back request still unanswered after 3 minutes falls through to the restart panel (`SEND_WAIT_MS`) | `switchStore.test.ts` |
| 19 | Low | A 409 busy after Check now (or after a switch) uses the info tone, as the GET state does | `actions.test.ts`; `switchStore.test.ts`; `views.test.ts` |
| 20 | Low | The token's expiry shows the date only. The notice reads "Your GitHub token expires in N days, on <date>. Make a new one before then." ("1 day"; past or today falls back to 13's "expires on <date>") | `updatesModel.test.ts`; pane |
| 21 | Low | No chunk split, as asked. The build's main chunk is now 510.6 kB (the 500 kB advice) | none |

**Wording changed or added in this round (for 13; the §4 list above is otherwise current):**
- **Roll back dialog** (13 §6, the owner's decision):
  - Lines: "ShelfSync will close and open again." + "<version> didn't change the database, so your data stays as it is. You can install <version> again from Settings › Updates."
  - Or: "<version> changed the database. ShelfSync restores the backup taken just before the update, on <date>. Changes made since then are lost and can't be brought back. You can install <version> again from Settings › Updates." + "A copy of the current data is kept in the backups folder."
  - No-date variant: drop ", on <date>".
  - Buttons: "Roll back" and "Cancel".
- **Restart panel** (proposed): "When ShelfSync is back, it opens in a new tab." When a new copy answers, it becomes "ShelfSync is back" / "It opened in a new tab, signed in. You can close this one." This replaces "This tab reloads when ShelfSync <v> answers."
- **No answer** (lead wording):
  - "ShelfSync didn't answer, so the reset may not have happened. Reload this page to check."
  - "ShelfSync didn't answer, so the settings may not have been saved. Reload this page to check."
  - "ShelfSync didn't answer, so the token may not have been saved. Reload this page to check."
  - "ShelfSync didn't answer, so the token may not have been removed. Reload this page to check."
  - "ShelfSync didn't answer, so that may not have happened. Reload this page to check." (any Updates action)
  - "The theme applies to this tab, but it may not have been saved. Reload this page to check."
- **Stale page** (proposed): "ShelfSync didn't answer just now, so this may be out of date."
- **Token expiry** (13 §3 + the mockup): "Your GitHub token expires in <n> days, on <date>. Make a new one before then." ("in 1 day"), with the date only. "Expires on <date>." beside Saved, also the date only.

**Run after the fixes (this PC).** All five ran through `tools/heavy.sh`:
- `npm run lint`: passed (78 files).
- `npm run typecheck`: passed.
- `npm test`: 539 passed in 16 files.
- `npm run build`: passed, with the same chunk-size warning.
- `npm run schema:check`: current.

`uv run pytest` was not run again: no backend file changed since the 1437-passed run in §4.

**Fresh screenshots** are in `.logs/shots/m1b.4/` (pane, 1280 × 900, mocked sample answers):
- Restart panel: `review-restart-waiting-light-1280.jpg`, `review-restart-waiting-dark-1280.jpg`, `review-restart-back-light-1280.jpg`, `review-restart-back-dark-1280.jpg`
- Roll back, files only: `review-dialog-rollback-files-light-1280.jpg`, `review-dialog-rollback-files-dark-1280.jpg`
- Roll back, database changed: `review-dialog-rollback-database-light-1280.jpg`, `review-dialog-rollback-database-dark-1280.jpg`
- Expiry notice: `review-updates-ready-expiry-days-light-1280.jpg`

The mock's restart sends empty answers while ShelfSync is "gone", then a new copy that answers the session check with 401. The console showed only those deliberate failures.

**Not verified:**
- Chrome's second-Esc close while busy, in a real browser. It is covered by the fake in `dialog.test.ts`, but the only busy dialog (Reset) answers too fast to try by hand.
- The real switcher.
- Playwright and axe, which run in CI only.

## 6. Integration notes
_(lead)_

## 7. Handover
_(lead, 2026-10-28)_ Brief written; the designer starts once m1b.3 is merged.
