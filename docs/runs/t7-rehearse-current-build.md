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

### Builder's early report
_(builder, 2026-11-02; branch `t7/rehearse-current-build` from `fix/rehearse-current-build` 4cebb6a; commit 4378e76. Nothing real has run yet: no release build, no rehearsal, no registry, Credential Manager or mutex call.)_

**Skills.** None loaded, by the brief: `security-review` and `code-review` are the reviewer's; Context7 isn't needed (no library call changed: `winreg`, `ctypes`, `httpx`, `cryptography` are used as before, plus two documented Win32 calls, `CredEnumerateW`/`CredDeleteW` and `OpenMutexW`); `run` doesn't fit (the rehearsal starts the app itself).

**The approach.** The base build is now run **as built**: since m1b.2 every piece the old script added is in `main`, so the rehearsal copies `--base` and patches only what a rehearsal must change. Each patch must match **exactly once** (it raised only on "not found" before), so a moved target stops the run instead of patching the wrong place.

| Patch or step | Decision | Why |
|---|---|---|
| `server.py`: `migrate_with_backup` import and call, `build_update_service` import and wiring (4 patches) | **Dropped** | All in `main` since m1b.2 (`server.py` lines 21 and 216-219 today); they are why it stopped with "rehearsal patch not found". |
| `api/app.py`: copied from the checkout, then `UI_DIR = source_ui_dir()` | **Dropped** | `source_ui_dir` is in `main` (`api/app.py:46`); copying the checkout's file into the build was only needed for m1b.1's base. |
| `OVERLAY` (8 paths of the checkout copied over the build) | **Dropped** | They were m1b.2's new code on m1b.1's base. A base built from current `main` already has them, and the overlay (which lacked every M2 module, m2.1 L3) would mix two trees. In its place a **note** (never a failure) lists the checkout files that differ from the build's, so a stale `--base` is visible. |
| Copy of `cryptography`, `cffi`, `pycparser` and `_cffi_backend*` from the venv, and their compile | **Dropped** | They are locked run-time dependencies now (`pyproject.toml`: `cryptography==50.0.2`, which pulls `cffi` and `pycparser`), so `build.py` installs them from the lock with hashes. Copying the venv's over them would test files the release doesn't ship. Only `shelfsync/` is recompiled (`checked-hash`, as `build.py` does). |
| `__version__` | **Changed** | Was the literal `"0.1.0"`; now the one `__version__ = "…"` line, whatever the build's version (it carries a comment today), so a version bump doesn't break it. |
| Release public key (`update/release_key.py`), `FIRST_CHECK_SECONDS` (`update/service.py`), `SERVICE_NAME` (`platform/secrets.py`), `UNINSTALL_KEY` (`platform/uninstall_entry.py`), no tab (`os.startfile(url)` in `platform/shell.py`) | **Kept**, targets checked | Each target is unchanged in today's code and found exactly once (checked on a scratch copy of `backend/shelfsync`, which the build copies; the patched package parses). `shell.py` now has a second `os.startfile` (`open_folder`): the target keeps the `(url)` form, so only the tab is disabled. |
| `build-suffix.txt` | **New** (brief item 2) | Each copy gets `-rehearse-<run id>` in `shelfsync/platform/build-suffix.txt` (`names.SUFFIX_FILE_NAME`, where `platform/names.py` reads it), replacing the base's `-rehearsal`. A copy counts as installed (it sits in `versions\<its version>`) and Start with Windows is on by default, so the launcher **writes a Run value**: now `ShelfSync-rehearse-<id>`, never `ShelfSync` (the old script, run today, would have written the real one). A per-run name also leaves alone any `ShelfSync-rehearsal` value a rehearsal install may hold. |
| Proof of the names | **New** | After each copy is compiled, its own `python.exe -B` runs smoke.py's `NAMES_PROBE` (loaded from `packaging/smoke.py`, so it is the release build's own check) and must print `ShelfSync-rehearse-<id>` and `TecHaust.ShelfSync-rehearse-<id>` (4 checks). After 0.0.1 starts, the Run value `ShelfSync-rehearse-<id>` must exist and name the rehearsal's `current\pythonw.exe` (1 check). |
| Failure handling | **Changed** | A failed patch or step used to `raise SystemExit` / propagate past the result; now it is one FAIL line ("the sequence ran to the end") and the clean-up and its checks still run. |
| Clean-up | **Changed** | Also removes the throwaway Run value (that exact name only) and any Credential Manager target left under the throwaway service (a keyring `<entry>@<service>` copy), besides the `OWNED_SECRET_NAMES` under it. |
| Clean-up check (brief item 5) | **New**, section 6 of the output | Throwaway side: no Credential Manager target under the throwaway service, the throwaway uninstall key gone, the throwaway Run value gone, no AUMID key for the throwaway AUMID, `--work` gone (5 checks). Real side: read before the run and after, compared, **never printed**: every Run value whose name starts with `ShelfSync` (other than this run's), the real uninstall key's values, the real `TecHaust.ShelfSync` AUMID key, the target names under the `ShelfSync` service, and a listing (names, sizes, modified times; links never followed) of `%LOCALAPPDATA%\ShelfSync` and `%LOCALAPPDATA%\Programs\ShelfSync` (6 checks). |
| Start condition | **New** | It stops before making anything if ShelfSync is running: the copies use the app's real single-instance mutex (`Local\ShelfSync-<SID>`; a T6 follow-up, out of scope), so a running copy would make them second launches. Checked with `OpenMutexW` (opens, never creates or takes it). Also stops if `--base` has no `python.exe` or `shelfsync`. |
| Docstring | **Rewritten** | Says what it does now (no "two wiring changes"). No runbook names the command (`docs/runbooks/` checked); the m1b.2 and m2.1 run files name it as history and stay as written. |

**For the analyst to decide or check**
1. **Reading the real names.** The clean-up check reads the real names (brief item 5 asks for it). The Credential Manager part calls `CredEnumerateW` (all of this user's credentials, filter NULL): Windows returns whole `CREDENTIAL` structures, but the script's ctypes structure has only `Flags`, `Type` and `TargetName`, so Python reads target names only and never touches a secret; the buffer is freed with `CredFree`. The alternative is a prefix filter (`ShelfSync*`), which misses keyring's `<entry>@ShelfSync` targets.
2. **Run from inside the Claude app.** Its MSIX package keeps a private copy of new `%LOCALAPPDATA%` folders (04-A V36), and maybe of HKCU writes. The rehearsal reads and writes in the same context, so its before/after checks hold for that context; a write that went to the real Windows view (or only to the private one) would not be told apart. Running it in Windows PowerShell outside Claude would avoid the question; the brief has me run it.
3. **Expected checks:** 27 as before, plus 4 name probes, 1 Run value check, 11 clean-up checks: **43**.

**Stage 2 plan (after GO).** A short detached worktree of this branch (`C:\Users\r4rup\AppData\Local\Temp\sst7`; the 260-character `compileall` limit), `build-cache\` copied from the main checkout if present (otherwise `build.py` downloads the pinned embeddable zip from python.org, checked by SHA-256), `npm ci` and `npm run build` in its `frontend\`, then through `tools/heavy.sh`: `release-build.ps1 -Suffix -rehearsal -Work C:\Users\r4rup\AppData\Local\Temp\ssrbt7a`, the rehearsal (`--base <that worktree>\build\ShelfSync-0.1.0 --work C:\Users\r4rup\AppData\Local\Temp\sst7r`) logged to `.logs/t7-rehearse.log`, the full `uv run pytest`; then the docs and §3.

## 3. Builder report

## 5. Review

## 6. Integration notes

## 7. Handover
_(lead, 2026-11-02)_ Brief written. Next: the builder in its own worktree from `fix/rehearse-current-build`.
