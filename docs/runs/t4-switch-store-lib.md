Status: closed (merged as #38, 2026-11-02)
Tier: C (screens; a move only, nothing on screen changes)
Usage (from `node tools/model-audit.mjs 2026-11-01` in the cloud session, 01:11 IST, 2026-11-02). The one 5-h reading, posted by the orchestrator, is 31 % at 00:51 IST, 2026-11-02; there was no newer reading, so the end % isn't known.
- lead `claude-opus-5-5/high`: skills none per the audit. `frontend-design` isn't in this session's Skill tool, so it was read from `/mnt/skills/public/frontend-design/SKILL.md`, which the audit can't see.
- designer `claude-opus-5-5/high`: skills none per the audit, **flagged "no skill loaded"**, for the same reason; it also read `frontend-design` from the file. 5-h 31 % → not read.
- reviewer `claude-opus-5-5/high` [code-review]: 5-h 31 % → not read.
- general-purpose `claude-opus-5-5/high`: the `code-review` skill's own read-only helper, inside the reviewer. The audit noted it as a built-in agent; it changed no files.
- the orchestrator on the PC (integration and visual check, 2026-11-02): lead `claude-opus-5-5/high`.

# T4: `switchStore` and the Updates model out of `screens/`

One of the parallel follow-up tasks the orchestrator (a PC session) runs; the owner approved the plan on 2026-11-02. It closes the open follow-up in [10](../10-status.md): "`switchStore` stays in `screens/settings/` until Settings › Updates' model and wording move out of `screens/`" ([11](../11-decisions.md), 2026-10-29).

## 1. Brief
- **PRD IDs:** none new. The code moved serves SYS-06, SYS-07 and SET-04 (Settings › Updates) and UI-SET (its wording); behaviour is unchanged.
- **Why:** CLAUDE.md "Screen code layers": `api/` → `lib/` → `components/` → `app/` and `screens/`; `components/`, `lib/` and `api/` never import from `screens/`. Today `app/`, `main.tsx` and `theme/useSavedTheme.ts` reach into `screens/settings/switchStore.ts`, which in turn needs `updatesModel.ts` (`Phase`) and `wording.ts` (the Updates action lines). So the switch can't move to `lib/` until the Updates model and wording do.
- **Files (screens layer only; no backend):**
  - New in `frontend/src/lib/`:
    - `updatesWording.ts`: the Settings › Updates and GitHub-token wording now in `screens/settings/wording.ts` (`U`, `T`, `checkProblem`, `NO_RELEASE`, `checkedAt`, the "Last switch" lines and `lastSwitch`, the Updates API errors, `BUSY_LINE`, `updatesActionError`, `updatesActionTone`), byte for byte. Precedent: `lib/storesWording.ts`.
    - `updatesModel.ts` and `updatesModel.test.ts`: moved from `screens/settings/`.
    - `switchStore.ts` and `switchStore.test.ts`: moved from `screens/settings/`.
    - A test that fails when any file in `api/`, `lib/` or `components/` imports from `screens/` (`lib/layers.test.ts`).
  - `screens/settings/wording.ts` keeps the shell's and Settings › App's wording (`SETTINGS_TITLE`, `LATER`, `A`); its header comment says where the Updates wording went.
  - Importers updated: `app/AppShell.tsx`, `app/useStores.ts`, `app/boot.test.ts`, `main.tsx`, `theme/useSavedTheme.ts`, and in `screens/settings/`: `actions.ts`, `actions.test.ts`, `forms.ts`, `forms.test.ts`, `AppPage.tsx`, `AppView.tsx`, `BackupPage.tsx`, `StoragePage.tsx`, `RestartScreen.tsx`, `UpdatesPage.tsx`, `UpdatesView.tsx`, `views.test.ts`. (`app/boot.ts` only names `switchStore` in a comment; it imports nothing from it.)
  - No re-exports left behind in `screens/settings/`: every importer points at the new module, so there is one place for each name.
- **Skills:** `frontend-design` (09 §3: any screen or UI component); Context7 for any library touched. This is a move of existing code: no new library API is used (the layer test uses Vite's `import.meta.glob` with `?raw`, as `components/chunkBoundary.test.ts` and `styles/tokens.test.ts` already do).
- **Done when** (in `frontend/`, each through `bash tools/heavy.sh --log <name> …`):
  - `npm run lint`, `npm run typecheck`, `npm test` and `npm run build` pass;
  - the layer test proves nothing in `lib/`, `components/` or `api/` imports from `screens/`, and `git grep` finds no import of `screens/` outside `app/`, `screens/` and `main.tsx`;
  - nothing on screen changes: no wording, class or markup change (the moved code is identical apart from import paths and comments);
  - the reviewer approved.
- **Out of scope / owned by others:** `frontend/src/styles/**` (T5); `backend/`, `packaging/`, `brand/`, `tools/`, `.github/`, `pyproject.toml`, `uv.lock` (T6, P0 and others); `docs/10-status.md` and `CHANGELOG.md` (the orchestrator). No visual check here (CLAUDE.md rule 10: the orchestrator does it on the PC before it opens the PR). No PR from this session.

## 4. Designer report
Cloud session, so there are no screenshots, no sample data and no placeholders. `frontend-design` was read from its SKILL.md first and changed nothing, since this is a move. Context7 wasn't used because no library API was touched.
- **Commits:**
  - `18ed0d2` refactor(ui): move the Updates wording to lib/
  - `852622d` refactor(ui): move switchStore and the Updates model to lib/
  - `5fb7dc3` test(ui): api/, lib/ and components/ never reach screens/
  - `f05887c` (after the review) test(ui): layer test sees .js specifiers, vi.mock and multi-line imports

  Each commit passed typecheck and the tests on its own.
- **Files (24):**
  - New `lib/updatesWording.ts`: the Updates and GitHub-token block, moved byte for byte. `cmp` matched the 196 lines, SHA-256 `d54c49bd…`.
  - `screens/settings/wording.ts` keeps `SETTINGS_TITLE`, `LATER` and `A`; the 55 lines match the old file minus the block.
  - Moved with `git mv` into `lib/`: `updatesModel.ts` and `switchStore.ts`, with their tests (similarity 96–99 %, import paths and comments only).
  - The 17 importers named in §1 now point straight at `lib/`. No re-exports are left in `screens/`.
  - New `lib/layers.test.ts`. It reads every `.ts`/`.tsx` under `src/` as text (Vite `?raw`) and builds the import graph from static, multi-line, side-effect and dynamic imports and `vi.mock`. It fails if any file in `api/`, `lib/` or `components/` (tests included) reaches `screens/`, directly or through other modules, and prints the chain. A self-check pins known edges and fails on any relative import that doesn't resolve.
- **The layer test on the old tree** (`6f2fdbe`'s `src/` plus the test) failed on exactly `components/ThemeMenu.tsx → theme/useSavedTheme.ts → screens/settings/switchStore.ts`, the violation this task removes. On the new tree it passes. Planted imports in `lib/` all fail by name:
  - a `screens/` import, a `.js`-suffixed one and a `vi.mock`;
  - an import that can't be resolved, which fails the self-check.
- **Nothing on screen changes:**
  - Outside the wording split and the new test, the diff has 0 changed lines that aren't imports or comments.
  - The old and new `dist/` match once file-name hashes are ignored: CSS, fonts, SVG and `index.html` are identical; the JS chunks are the same, with sizes within 2 characters; all 7,287 string literals match chunk by chunk. Only the minifier's local names differ.
- **Checks** (through `tools/heavy.sh`): `npm ci`, lint (124 files), typecheck, test (29 files, 941 tests) and build all passed.
- **Not verified:** screenshots, keyboard use and the console (cloud session, rule 10); `npm run e2e` (CI only); `schema:check` (no API file changed).
- **Comment-only change:** the "proposed (m1b.4)" line in both wording headers now says "new in m1b.4" instead of "new in this task".

## 5. Review
**Code review: APPROVE** (`reviewer`, `code-review` loaded; no visual review in a cloud session). The reviewer checked these itself:
- the wording split is identical (diffed by section);
- there is one switch store per tab, and its code and the Updates wording sit only in the main chunk, as before; the lazy page chunks are unchanged;
- `lib/` imports nothing from `app/`, `components/`, `screens/` or `theme/`, so there's no circular import;
- the scope matches the owned files, and no stale paths remain in them.

Its own checks passed: lint, typecheck, test (941) and build.

Findings:
- **medium (outside T4's files, for the orchestrator):** `docs/13-content.md:55` still names `frontend/src/screens/settings/wording.ts` as the source of the whole "Settings screens" row. Fix: name both files, `screens/settings/wording.ts` (shell, App) and `lib/updatesWording.ts` (Updates, GitHub token).
- **low (for the orchestrator):** [11](../11-decisions.md)'s 2026-10-29 `switchStore` row is now resolved. Add a row recording T4: the Updates model, wording and switch are in `lib/`, there are no re-exports, and `lib/layers.test.ts` enforces the rule.
- **low (fixed in `f05887c`):** the layer test's skip filter also skipped `.js`/`.jsx` specifiers, so such imports passed unseen.
- **low (fixed in `f05887c`):** `vi.mock` wasn't seen. A comment now names the forms still not seen (a template-literal `import()`, a non-raw `import.meta.glob`), none of which is in `src/` today.
- **low (fixed in `f05887c`):** the self-check's title claimed "re-exported" imports; it now checks a real multi-line import instead.
- **low (from before T4, carried unchanged; for triage):** `lib/switchStore.ts` `run()`. If the server refuses an Install or Roll back after `SEND_WAIT_MS` has already shown the restart panel, the refusal is dropped and the panel stays on its late line. The comment says this is deliberate ("the wait ran out first: the panel stays"). It may deserve its own follow-up.
- **Noted, not findings:** the test checks only the `screens/` rule, not every upward import (e.g. `components/SideNav.tsx` → `app/nav`), which matches the brief and CLAUDE.md. A shared `?raw` helper is a possible cleanup.

**Re-check of the fix diff `5fb7dc3..f05887c`: APPROVE**, no new findings. Test (941), lint and typecheck passed.

## 6. Integration notes
- **Merged:** the designer's commits were fast-forwarded onto `refactor/switch-store-lib`, with no squash; the orchestrator's PR squashes them.
- **Full checks by the lead at `f05887c`** (through `tools/heavy.sh`, logs `.logs/t4-lead-*.log`): lint (124 files, no fixes), typecheck, test (29 files, 941 tests) and build all passed.
- **No `screens/` imports outside the top layer:** `git grep` finds none outside `app/`, `screens/` and `main.tsx`.
- **For the orchestrator:**
  1. `docs/13-content.md:55` (medium above).
  2. A row in [11](../11-decisions.md) for T4, and close the follow-up in [10](../10-status.md).
  3. Triage the pre-existing `switchStore` refusal-after-timeout behaviour.
  4. The visual check on the PC: Settings › Updates, App, Storage and Backup, and the restart panel should look exactly as before.
  5. Open the PR.
- **Not verified here:** the visual check (rule 10), Playwright and axe (CI only), and the 5-h % at the end, since no newer reading was posted.

## 7. Handover
The code is done, and the review and its re-check both approved it. The branch `refactor/switch-store-lib` is pushed, and no PR was opened. Next, for the orchestrator: the visual check on the PC, then the PR, and the record items in §6.

_(lead, 2026-11-02, 08:20 IST)_ Merged on green as [#38](https://github.com/techaust/shelf_sync/pull/38). The PC check found its built CSS byte-identical to `main`'s; rebased and pushed as `refactor/switch-store-lib-int`. The owner closed the cloud session. Task closed.
