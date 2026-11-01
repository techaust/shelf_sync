Status: open
Tier: C (screens; a move only, nothing on screen changes)
Usage: lead `claude-opus-5-5/high` (cloud session; `get_session` reports `effort_level: high`) [frontend-design]. 5-h reading posted by the orchestrator: 31 % at 00:51 IST, 2026-11-02

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
