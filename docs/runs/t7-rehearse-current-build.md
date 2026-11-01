Status: open
Tier: B (a developer tool for the updater; it writes throwaway registry values and Credential Manager entries, so the reviewer also runs `security-review`)
Usage: lead `claude-opus-5-5/high` (PC, orchestrator): 5-h 34 % at the brief

# T7: `tools/release/rehearse.py` runs against a current build

T7 of the 2026-11-02 parallel plan ([11](../11-decisions.md)). It closes the open follow-up "`tools/release/rehearse.py` doesn't run against a current build" (m2.1 review L3; [runs/m2.1-stores.md](m2.1-stores.md) O8 and L3: "the outdated server.py patches are untouched"). It runs on the PC (it needs a real embedded build and Windows), after T6 (#40), which changed the build.

## 1. Brief

### PRD IDs
SYS-06 and SYS-07 (the updater: install, update, roll back, refuse a tampered release, switch back from a broken one). Nothing in the app changes.

### What's wrong today
`build_version()` (`tools/release/rehearse.py:119-200`) copies a base build, overlays this checkout's code, then patches it. Its first five patches add m1b.2's wiring to m1b.1's `server.py` and `api/app.py` (`migrate_with_backup`, `build_update_service`, `source_ui_dir`). That wiring has been in `main` since m1b.2, so `replace()` stops with "rehearsal patch not found". Later changes may also have moved the other patch targets (M2's services in `create_app`; T6's `platform/names.py` and `build-suffix.txt`).

### What to do
1. **Drop the obsolete wiring patches.** Keep only what the rehearsal needs: the version, the release public key (a key made in memory), `FIRST_CHECK_SECONDS` pushed out, the throwaway Credential Manager service, the throwaway uninstall key, no browser tab. Check each against today's code and update its target.
2. **Throwaway Run value and AUMID (new since T6):** every fake version carries a valid throwaway `build-suffix.txt` (in the place `platform/names.py` reads it), so Start with Windows and toasts use `ShelfSync<suffix>` and `TecHaust.ShelfSync<suffix>`, never the real names. Prove it in the run (read the names back, or check the stamp).
3. **The overlay:** `OVERLAY` and the copy of `cryptography`/`cffi`/`pycparser` from the venv date from m1b.2, when the base build didn't ship them. Keep, change or drop each, with the reason in the report.
4. **Run it for real** against a fresh build from current `main`: `release-build.ps1 … -Suffix -rehearsal` (the CLAUDE.md "Release build" command; a new work folder of at most 60 characters, and run from a short path: T6 found that a long worktree path breaks `compileall` past 260 characters). Then `PYTHONPATH=backend uv run python tools/release/rehearse.py --base <the embedded build folder> --work <a new empty short folder>`. Every step in its sequence must report ok: install 0.0.1, update to 0.0.2 (one extra migration), roll back (backup restored), a tampered 0.0.3 refused, a broken 0.0.4 (its migration fails, exit 2) switched back.
5. **Clean up:** afterwards no throwaway Credential Manager entry, uninstall key, Run value or folder is left (check each), and nothing real was touched: the `ShelfSync` service, the `ShelfSync` Run value, the real uninstall key, the real data and install folders.
6. **Docs:** the docstring's "two wiring changes of this task" text, and any runbook or run file that names the rehearsal command, match what it does now.

### Files
- `tools/release/rehearse.py` (it isn't linted by ruff or checked by mypy, since `tools/` is excluded; keep it clean anyway and parse it with Python 3.14).
- A runbook line only if one names the command (`docs/runbooks/release.md`, if it does).
- This run file.
- **Never touch:** `backend/**` and `packaging/**` (if the app or the build must change for the rehearsal to work, stop and report with options), `frontend/**`, `pyproject.toml`, `uv.lock`, `docs/10-status.md`, `CHANGELOG.md`.

### Skills
`security-review` is the reviewer's. Context7 isn't needed unless a library call changes.

### Done
- The full rehearsal runs to the end with every check ok, against a fresh release build from current `main`; the output is in `.logs/t7-rehearse.log` and summarised in the report.
- The cleanup check passes, and the real names were never touched.
- The builder report lists each kept, changed and dropped patch with its reason.
- The full `uv run pytest` still passes (nothing in `tests/` should change; if a test covers rehearse.py, it passes).

### Out of scope
- T6's follow-ups: a rehearsal copy's data folder, real Credential Manager service at run time, single-instance name and `InstallDir`; the update service refusing to run in a suffixed build. Those are app changes for a later task.
- Any GitHub, store or S3 call (the rehearsal never makes one).

## 2. Early check

## 3. Builder report

## 5. Review

## 6. Integration notes

## 7. Handover
_(lead, 2026-11-02)_ Brief written. Next: the builder in its own worktree from `fix/rehearse-current-build`.
