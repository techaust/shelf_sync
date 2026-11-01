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
5. **Clean up:** afterwards no throwaway Credential Manager entry, uninstall key, Run value or folder is left (check each), and nothing real was touched: the `ShelfSync` Run value, the real uninstall key, the real data and install folders (each read before and after, and the same). The real `ShelfSync` Credential Manager service is **not read**: it is proven unreachable instead (analyst C3: only `platform/secrets.py` talks to Credential Manager, and each copy reports the throwaway service).
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
- The cleanup check passes, and the real names were never touched (the real Credential Manager service proven unreachable, never read).
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
3. **Expected checks:** 27 as before, plus 4 name probes, 1 Run value check, 11 clean-up checks: **43**. _(Lead, after the review: the old sequence had 30 checks, not 27 (3 + 8 + 8 + 4 + 7), so the run's 46 is the right total.)_

**Stage 2 plan (after GO).** _(Superseded by the lead's locations below.)_ A short detached worktree of this branch, `build-cache\` copied from the main checkout, `npm ci` and `npm run build` in its `frontend\`, then through `tools/heavy.sh`: the release build, the rehearsal logged to `.logs/t7-rehearse.log`, the full `uv run pytest`; then the docs and §3.

### Analyst: CHANGE (C1–C7)
_(analyst's early check, relayed by the lead, 2026-11-02; builder's resolutions, commit after 2a43438. The patch list itself was confirmed: every drop is in `main`, every kept target matches once, the suffix is valid and reaches every copy.)_

| # | Finding | Resolution |
|---|---|---|
| C1 (high) | The name probe only recorded a FAIL; the copy was still signed and run. | **Done.** One probe and one check per copy (`copy_report`); anything but the expected five lines records the FAIL and raises `RehearsalError` before `write_manifest`, so the copy is never signed or started, and the clean-up still runs. |
| C2 (high) | A hard-killed run leaves `Run\ShelfSync-rehearse-<id>`; at the next sign-in that copy would start with no `SHELFSYNC_DATA_DIR` and use the **real** data folder (real database migrated to 9001/9002). | **Done.** (a) Copy-only patch in `shelfsync/paths.py`: `    return DataPaths(Path(local_app_data) / "ShelfSync")` (exactly once) becomes `    raise RuntimeError("a rehearsal copy runs only with SHELFSYNC_DATA_DIR")`, so such a start stops at "the data folder is unknown" (`run_application`, exit 3) before any lock or database. Gate: the copy's own Python, with `SHELFSYNC_DATA_DIR` removed from its environment, must print `no-data-folder` from `resolve_data_paths()`. (b) Stage 2 runs the rehearsal with `run_in_background` and never stops it. (c) The first line names the run id, the throwaway service, the Run value with its key, `HKCU\Software\ShelfSyncRehearsal-<id>`, the AUMID and the `--work` folder; the manual steps are below. |
| C3 (medium) | The unfiltered `CredEnumerateW` returned every credential's structure to the process. | **Done.** `throwaway_targets()` passes only `f"{SERVICE}*"` (the run id makes it this run's own); `throwaway_entries_left()` adds `KeyringSecretStore(SERVICE).get(name) is None` for each `OWNED_SECRET_NAMES` (covers keyring's `<entry>@<service>` targets). The real-service read and the `SERVICE_NAME` import are gone. Proof by construction instead: (i) the per-copy probe prints `secrets.SERVICE_NAME` and `secrets.KeyringSecretStore.__init__.__defaults__[0]`, both must equal the throwaway service (part of the C1 gate); (ii) before anything is made, one check that no `shelfsync/**/*.py` of `--base` other than `platform/secrets.py` matches `keyring|win32cred|Cred(Read|Write|Delete|Enumerate)` (a failure ends the run with nothing made). Docstring and the brief's item 5 and Done now say the real service is not read but proven unreachable. |
| C4 (medium) | `clean_up` could stop halfway (the logs copy raising skipped `rmtree(work)` and `check_clean`); the uninstall key was made outside the `try`. | **Done.** Each clean-up step runs through `guarded()` (a failure is a `clean-up: …` FAIL line and the next step runs); every clean-up check runs through `check_safely()`; `clean_up` and `check_clean` both run in the `finally`; the data folder and the throwaway uninstall key are made inside the `try`. |
| C5 (low) | `App.stop` ended whatever PID `runtime.json` named. | **Done.** It opens a watch on the PID (`self.processes.watch`), and terminates only while holding it, only if the normcased image starts with the normcased `--work` path plus the separator; otherwise it says so and leaves it. |
| C6 (low) | The PowerShell kill put the path inside the command with `-like`. | **Done.** The path goes through `SHELFSYNC_REHEARSAL_WORK`; the filter is `$_.Path -and $_.Path.StartsWith($p, [System.StringComparison]::OrdinalIgnoreCase)` with `$p` the path plus `\`. |
| C7 | Report the script's own count. | **Will do** in §3: the script's "N of N checks passed" line, quoted as printed (the planned total is now 30 + 4 copy probes + 1 `--base` check + 5 throwaway + 5 real = 45, plus the Run value check inside the sequence's 31 = 46, but the report quotes the run). |

**Checked offline** (no build, no Windows state; the venv's Python stood in for a copy's, as `tests/test_build_suffix.py` does): all seven copy patches match exactly once on a scratch copy of `backend/shelfsync`; the probe on the patched copy prints `ShelfSync-rehearse-<id> TecHaust.ShelfSync-rehearse-<id> ShelfSyncRehearsal-<id> ShelfSyncRehearsal-<id> no-data-folder` (gate passes); on the unpatched checkout it prints `ShelfSync TecHaust.ShelfSync ShelfSync ShelfSync data-folder-found` (gate fails, as it must); the `--base` scan finds nothing in today's package and finds a planted `import keyring` in `api/`. `ruff check`, `ruff format --check`, `mypy --explicit-package-bases` on `rehearse.py`: clean.

**Stage 2 locations (lead).** The detached worktree at `D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\sst7` (so `--base` is `…\sst7\build\ShelfSync-0.1.0`), `--work` `D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\sst7r`, and the release build's `-Work` `C:\Users\r4rup\AppData\Local\Temp\ssrbt7a` (≤ 60 characters). Not under `%LOCALAPPDATA%`, where a build made inside Claude may exist only in the app's private copy.

**Open (lead's decision):** T7 merges on the run inside Claude; **the owner's run outside Claude** (Windows PowerShell) is recorded as open, carried to [10](../10-status.md) by the lead. The analyst's steps (`<base>` = a build folder made from `main` after T7 merges, on D:):
1. Quit ShelfSync from its tray icon.
2. In Windows PowerShell (not inside Claude), check the base folder is visible (it should print `True`):
   ```
   Test-Path "<base>\python.exe"
   ```
3. Run the rehearsal, with its output kept in `.logs\t7-rehearse-outside.log`:
   ```
   Set-Location "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\shelf_sync"; $env:UV_PYTHON_DOWNLOADS = "never"; $env:PYTHONPATH = "backend"; uv run python tools\release\rehearse.py --base "<base>" --work "$env:TEMP\sst7o" 2>&1 | Tee-Object -FilePath ".logs\t7-rehearse-outside.log"
   ```

#### If a rehearsal run is killed
The first line of its output (`.logs/t7-rehearse.log`) names the run id `<id>` and the `--work` folder `<work>`. In Windows PowerShell (in the same place the run was started: inside the Claude app if it ran there), one command at a time, with `<id>` and `<work>` replaced:

1. End anything still running from the folder:
   ```
   $p = '<work>\'; Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($p, [System.StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force
   ```
2. Remove the throwaway Run value (Start with Windows):
   ```
   Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'ShelfSync-rehearse-<id>'
   ```
3. Remove the throwaway uninstall key:
   ```
   Remove-Item -Path 'HKCU:\Software\ShelfSyncRehearsal-<id>' -Recurse
   ```
4. Remove the throwaway Credential Manager entries: Start → type **Credential Manager** → open it → **Windows Credentials** → under **Generic Credentials**, each entry whose name starts with `ShelfSyncRehearsal-<id>` or ends with `@ShelfSyncRehearsal-<id>` (keyring's copies) → expand it → **Remove** → **Yes**.
5. Remove the folder (`rmdir` doesn't follow the `current` junction):
   ```
   cmd /c rmdir /s /q "<work>"
   ```

Even if step 2 is missed, the copy the Run value names stops at once at the next sign-in (C2a: no `SHELFSYNC_DATA_DIR`, so no data folder), and touches nothing real. It does show ShelfSync's "couldn't start" toast naming `%LOCALAPPDATA%\ShelfSync` at each sign-in until the Run value is removed: that toast is expected here and means nothing was touched.

## 3. Builder report
_(builder, 2026-11-02; branch `t7/rehearse-current-build`: 4378e76, 2a43438, e76b2a8 and this report's commit, on 4cebb6a. Run inside the Claude app on this PC.)_

**Result:** the full rehearsal ran to the end against a fresh `-Suffix -rehearsal` release build of e76b2a8 (current `main` plus this branch, which changes only `tools/` and `docs/`). The script's own line: **`46 of 46 checks passed`** (`.logs/t7-rehearse.log`). The clean-up check passed and the real names and folders read the same before and after. The full `uv run pytest` passed.

**Skills:** none loaded (see §2: `security-review` and `code-review` are the reviewer's, Context7 wasn't needed, `run` doesn't fit).

**Files changed**
- `tools/release/rehearse.py`: the patches, gates and clean-up in §2 (the builder's early report and the analyst's C1–C7).
- `docs/runs/t7-rehearse-current-build.md`: §2, brief item 5 and Done (C3 wording), the manual clean-up steps, the owner's outside-Claude steps, this report.
- No runbook names the command, so none changed. The m1b.2 and m2.1 run files name it as history and stay as written. Nothing in `backend/`, `packaging/`, `frontend/`, `tests/`, `pyproject.toml` or `uv.lock` changed.

**Commands and results** (all with `UV_PYTHON_DOWNLOADS=never`; heavy ones through `tools/heavy.sh`, which waited its turn behind a techaust_platform test and another ShelfSync worktree's pytest)
| # | Command | Result |
|---|---|---|
| 1 | `git worktree add --detach D:\…\SOFTWARE\sst7 e76b2a8`; `build-cache\python-3.14.8-embed-amd64.zip` copied from the main checkout (nothing downloaded; `build.py` checks its SHA-256) | done |
| 2 | `heavy.sh --log t7-npm-ci npm --prefix …\sst7\frontend ci` | exit 0 (146 packages; npm reports 3 moderate advisories, unchanged lock) |
| 3 | `heavy.sh --log t7-npm-build npm --prefix …\sst7\frontend run build` | exit 0 (tokens in step, vite build) |
| 4 | `heavy.sh --log t7-release-build powershell -NoProfile -ExecutionPolicy Bypass -File …\sst7\packaging\release-build.ps1 -Python C:\Users\r4rup\AppData\Local\Programs\Python\Python314\python.exe -Makensis "D:\…\tools\nsis-3.13\makensis.exe" -Work C:\Users\r4rup\AppData\Local\Temp\ssrbt7a -Suffix -rehearsal -SourceCommit e76b2a8fde64af49f366b2ec7df5452ee9ae79dd` (the commit given, so the script needn't run git in the other worktree) | exit 0: `Built …\sst7\build\ShelfSync-0.1.0 (4370 files)`; smoke passed (Run value and AUMID `ShelfSync-rehearsal` / `TecHaust.ShelfSync-rehearsal`); 98 installer checks `ok`, "All installer checks passed"; manifest written |
| 5 | `heavy.sh --log t7-rehearse uv run --locked python tools/release/rehearse.py --base "D:\…\SOFTWARE\sst7\build\ShelfSync-0.1.0" --work "D:\…\SOFTWARE\sst7r"` (`PYTHONPATH=backend`, from this worktree, in the background, not stopped) | exit 0, **46 of 46 checks passed** |
| 6 | Independent look afterwards (PowerShell, throwaway names only): `Test-Path` of `sst7r` and `HKCU:\Software\ShelfSyncRehearsal-e124cf27`, the Run value `ShelfSync-rehearse-e124cf27`, processes under `sst7r` | folder gone, key gone, value gone, 0 processes |
| 7 | `heavy.sh --log t7-pytest uv run --locked pytest` | exit 0: **2464 passed, 18 skipped, 52 deselected** in 215 s; coverage 93 % |
| 8 | `ruff check`, `ruff format --check`, `mypy --explicit-package-bases` (with `MYPYPATH=backend;tools/release`) on `rehearse.py` | clean |
| 9 | `heavy.sh --log t7-lint uv run --locked ruff check` and `heavy.sh --log t7-format uv run --locked ruff format --check` (the full lint, once, last; `tools/` is excluded by the configuration, so row 8 covers `rehearse.py`) | exit 0: "All checks passed!", "167 files already formatted" |

**The rehearsal's output, summarised** (run id `e124cf27`; the first line names the service `ShelfSyncRehearsal-e124cf27`, the Run value `ShelfSync-rehearse-e124cf27` in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, the key `HKCU\Software\ShelfSyncRehearsal-e124cf27`, the AUMID and the folder):
- `--base` scan: no module but `platform/secrets.py` names a Credential Manager API (1 check).
- Each of the four copies (0.0.1–0.0.4), before it was signed: its own Python printed `ShelfSync-rehearse-e124cf27 TecHaust.ShelfSync-rehearse-e124cf27 ShelfSyncRehearsal-e124cf27 ShelfSyncRehearsal-e124cf27 no-data-folder` (4 checks, all gates passed).
- 1. Install 0.0.1: health 0.0.1; schema 2 (the build's own latest); Start with Windows wrote `ShelfSync-rehearse-e124cf27` naming the rehearsal's `current\pythonw.exe`; `GET /api/updates` installed 0.0.1, not development, key present (4).
- 2. Update to 0.0.2: 202; `updated`; a new process answers 0.0.2; `current` → 0.0.2; schema 9001; throwaway `DisplayVersion` 0.0.2; one pre-migration backup; previous 0.0.1, roll back possible, database changed, backup available (8).
- 3. Roll back: the running image was `…\sst7r\Programs\ShelfSync\versions\0.0.2\pythonw.exe`; 422 `confirm_required` without confirmation; 202 with it; `rolled_back`; 0.0.1 runs; schema back to 2 (backup restored); `DisplayVersion` 0.0.1; one pre-rollback snapshot; both version folders kept (8).
- 4. Tampered 0.0.3: 409 `manifest_invalid` (wrong key); 409 `files_changed` (a file swapped after signing); the same 0.0.1 process still runs; `current` still 0.0.1 (4, plus its copy probe).
- 5. Broken 0.0.4: 202; `kept_old` with `migration_failed`; 0.0.1 runs again; `current` 0.0.1; schema 2, no half-done table; `DisplayVersion` back to 0.0.1; the last result reported by `GET /api/updates` (7, plus its copy probe).
- 6. Clean-up: nothing under the throwaway service (prefix targets and every owned entry); the throwaway uninstall key, Run value and `--work` folder gone; no AUMID key for the throwaway AUMID; the ShelfSync Run values, the real uninstall key, the real AUMID key, the real data folder and the real install folder the same as before (10). No `clean-up: …` FAIL line, so every clean-up step ran without an error.

**Left behind and removed**
- `sst7r` (`--work`): removed by the script's own clean-up (and confirmed gone).
- `sst7` (the detached build worktree): the script doesn't touch it; removed by me with `git worktree remove --force` (it held the build, `node_modules` and `build-cache`, all untracked).
- `C:\Users\r4rup\AppData\Local\Temp\ssrbt7a` (the release build's `-Work`): still holds `Setup-0.0.1.exe` and `Setup-99.0.0.exe`, the two test Setups `release-build.ps1` leaves there; not removed (outside the brief; safe to delete).
- `.logs/rehearsal/` in this worktree: the copies' log and updater files, kept by the script on purpose (git-ignored).

**Not verified**
- **Outside the Claude app.** Everything ran inside it, so the real-side checks hold for the view this context has (the app's private copy of new `%LOCALAPPDATA%` folders, 04-A V36, and possibly of HKCU writes). The owner's run in Windows PowerShell is the open item in §2, with the analyst's steps.
- **The real `ShelfSync` Credential Manager service** was not read, by design (C3): it is proven unreachable by the `--base` scan and the four copy probes, not observed.
- **The single-instance mutex** keeps the real name in the copies (T6 follow-up, out of scope). The real ShelfSync wasn't running (the start check passed); had the owner started it during the run, it would have been a second launch and opened nothing.
- **A killed run** wasn't rehearsed. The manual steps in §2 and the C2a patch weren't exercised end to end (the patch is proven by the four probes printing `no-data-folder`).
- The `-SourceCommit` I passed is the branch head, e76b2a8. The build's code equals `main`'s (#40), plus this branch, which changes no shipped file. The rehearsal printed no "code differs" note, so the build's `shelfsync/` matched this checkout.

**Open questions:** none beyond the owner's outside-Claude run (§2).

## 5. Review
_(reviewer `claude-opus-5-5/high`, `code-review` and `security-review` (both first ran on the wrong diff; applied by hand to `4cebb6a..7eb90cd`), 2026-11-02)_ **APPROVE**, 9/10. No critical, high or medium finding. Checked and holding: every throwaway name carries the run id and nothing real is deleted; the per-copy gate comes before signing or start; the `paths.py` patch stops a leftover copy before the mutex, the lock or the database; every patch matches exactly once; Credential Manager is read by prefix only and the buffer freed; the clean-up and its checks always run; termination only inside `--work`; no injection; the run file matches the code and the log (46 PASS, 0 FAIL). Lows:
1. The real service is proven unreachable, not blocked: a future `KeyringSecretStore("ShelfSync")` call would pass the scan and the probe. Fix: a copy patch so `KeyringSecretStore.__init__` raises unless `service == SERVICE`. **Follow-up** (needs another real rehearsal run).
2. Manual step 4 missed keyring's `<entry>@<service>` copies. **Fixed by the lead** (§2).
3. One failed credential delete skips the rest of the clean-up. Fix: guard each delete. **Follow-up.**
4. A `<name>@SERVICE` copy for a name outside `OWNED_SECRET_NAMES` would go unseen (the rehearsal creates no stores, so not today). **Follow-up** (when a rehearsal adds a store).
5. `--work` isn't refused inside a real ShelfSync folder. Fix: refuse it. **Follow-up.**
6. The kill note didn't mention the "couldn't start" toast. **Fixed by the lead** (§2).
7. The planned count said 43; the old sequence had 30 checks, so 46 is right. **Fixed by the lead** (§2).

## 6. Integration notes
_(lead, 2026-11-02)_ Integrated on `fix/rehearse-current-build-int` (the builder's five commits plus the lead's run-file fixes), rebased onto `main`; the full Python checks ran again after the rebase (results in the PR). No release build: `tools/release/` isn't shipped, and the builder's real run used a release build of its own commit.
- **Open, the owner's:** the run outside the Claude app (§2's steps).
- **Follow-ups:** review lows 1, 3, 4, 5 (one change, then one more real rehearsal run).

## 7. Handover
_(lead, 2026-11-02)_ Brief written. Next: the builder in its own worktree from `fix/rehearse-current-build`.
