Status: builder done (m1b.1-build branch); waits for the reviewer
Tier: B ([12 §2](../12-models-and-usage.md)); the installer row of [09 §3](../09-tooling.md) adds `security-review`
Usage: lead `claude-opus-5-5/medium` wrote this brief: 5-h 36 → 37 %

# M1b.1: Installer and packaging

The M1b plan, the owner's answers and the shared-file contracts are in [runs/m1b.2-updater.md](m1b.2-updater.md) §0. This task runs beside m1b.2 under those contracts.

## 1. Brief

### PRD IDs
SYS-01 (per-user `Setup.exe`, embedded Python, shortcuts, AppUserModelID, opens the wizard), SYS-08 (data kept unless "Remove my data"; the program folder removed completely), SYS-04 (the Run value starts ShelfSync in the tray). Also the M1a carry-overs listed in [10](../10-status.md) "Open follow-ups" that §0 gives this task.

### Agent and skills
`builder`, Sonnet 5.5 at medium, in its own worktree; it never pushes. It loads Context7 for uv (`uv pip install --target`, `uv export`), windows-toasts (custom AUMID) and pystray before writing code that uses them, and reads NSIS's own docs at nsis.sourceforge.io (Context7 has none, [09](../09-tooling.md)). The reviewer then runs `code-review` and `security-review` (installer and `platform/` rows of 09 §3).

### Facts checked for this brief (2026-10-27; rows in [04-A](../04-architecture-appendix/A-stack-verification.md))
- **NSIS 3.13** (released 2026-09-27) is the newest. Its portable `nsis-3.13.zip` (2.4 MB) is in SourceForge's file listing (`NSIS 3/3.13/`), not on the download page. **No checksum is published**, so its SHA-256 is pinned from the first download (V37).
- **NSIS isn't installed on GitHub's `windows-2025` runner** (image 20261021.299.1 lists Inno Setup, not NSIS), so `release.yml` downloads the same zip and checks the same SHA-256 (V50, settled).
- The **Python 3.14.8 embeddable package** is `python-3.14.8-embed-amd64.zip` (12.0 MB), SHA-256 `a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310` (python.org's release page). Python 3.14 has no PGP signatures; the build checks this hash, then `Get-AuthenticodeSignature` on every `.exe`, `.dll` and `.pyd` (signer "Python Software Foundation", V12).
- **windows-toasts** takes a custom AUMID through `InteractableWindowsToaster(..., notifierAUMID=...)`, once that AUMID is registered under `HKCU\Software\Classes\AppUserModelId\<id>` (its docs and `register_hkey_aumid.py`, Context7). Whether that alone gives the toast ShelfSync's name and icon, with no AUMID on the shortcut, isn't verified (V41).

### Before the builder starts (lead; done 2026-10-27 with the owner's yes)
1. **Done:** `nsis-3.13.zip` downloaded once (2,363,925 bytes, SHA-256 `ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8`, recorded in [04 §2.1](../04-architecture.md)). Every entry was checked to be under `nsis-3.13/`, then extracted to `D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\tools\nsis-3.13\`. That is outside the repo, needs no admin and installs nothing system-wide. `makensis.exe -VERSION` prints `v3.13`. Use `tools\nsis-3.13\makensis.exe` from there, and never copy it into the repo.
2. `packaging/build.py` downloads the embeddable zip itself and refuses any other hash.

### What to build

**Install layout** (04 §8, contracts in m1b.2 §0):
```
%LOCALAPPDATA%\Programs\ShelfSync\
  current            junction → versions\<v>   (made with cmd /c mklink /J, no admin)
  versions\<v>\      the embedded Python, Lib\site-packages\, the shelfsync package, ui\, shelfsync.ico
  uninstall.exe
%LOCALAPPDATA%\ShelfSync\   data (unchanged from M1a), plus instance.lock
```

**Backend (Python, Linux CI and fakes first, Windows adapters behind the existing interfaces):**
1. **`paths.ui_dir()`** replaces `api/app.py`'s `UI_DIR`:
   - an installed copy uses `<version folder>\ui`;
   - the source layout keeps `frontend/dist`;
   - an installed copy with no `ui\index.html` is a start-up error (exit 3 and a notice, wording for 13). A development run keeps the M1a "API only" log line.
2. **The data-folder lock** (`instance.lock` in the data folder), so a second logon session of the same user can't start a second server. `default_instance_lock()` covers the mutex and the lock file:
   - the mutex first, then the file, opened with no sharing and held for the life of the process;
   - either one taken means a second launch;
   - a crash leaves no stale lock, because Windows closes the handle;
   - the fake covers both.
3. **`--background`**:
   - `launcher_command()` writes `"<...>\current\pythonw.exe" -m shelfsync.launcher --background`, so signing in to Windows starts ShelfSync in the tray with no tab;
   - shortcuts and a second launch keep opening a signed-in tab;
   - an existing Run value without the flag is rewritten at the next start (the "unchanged" comparison already does that);
   - parse arguments with `argparse`; an unknown argument is an error, not ignored.
4. **`app.state.request_quit: Callable[[], bool]`**, published by `tray/launcher.py` for m1b.2:
   - it asks the tray to quit exactly like the menu's Quit, and returns False if a quit guard refuses;
   - the developer entry (`python -m shelfsync`) doesn't set it.
5. **ShelfSync's own toast AUMID**, `TecHaust.ShelfSync`:
   - an installed copy passes it to `InteractableWindowsToaster`; a development run keeps the M1a behaviour;
   - the installer registers it under `HKCU\Software\Classes\AppUserModelId\TecHaust.ShelfSync` (`DisplayName` "ShelfSync", `IconUri` → `current\shelfsync.ico`), and the uninstaller removes it.
6. **Cold toast timing:** a `-m windows` check measures, in a fresh process, the time from start to a shown toast. The result goes in the builder report and 04-A V49. If it's over 5 s (half of the safety exit's 10 s last stage), say so; don't change the timings.
7. **`python -m shelfsync.uninstall --remove-data`**, run by the uninstaller from `current\python.exe` before any file is removed, only when "Remove my data" is ticked:
   - removes every Credential Manager entry ShelfSync owns. Today that's the install token: take it from one list in `platform/secrets.py`, so M2's secrets join it;
   - then removes the data folder without following any link or junction (reuse `paths.remove_entry`);
   - exit 0 on success. On non-zero, the uninstaller says the data couldn't all be removed, names the folder, and goes on removing the program.
8. **Strings:** every new owner-facing string goes in `messages.py` (or the NSIS script's string table), with the proposed wording listed in the builder report for 13. The lead approves it before merge.

**Packaging (new `packaging/` folder, 04 §3):**
1. **`packaging/build.py`**, run with `python -I`, writes `build\ShelfSync-<v>\` and `build\shelfsync-<v>-win64.zip`:
   - downloads and hash-checks the embeddable zip;
   - writes `python314._pth` from a template (`python314.zip`, `.`, `Lib\site-packages`, `import site`; V11);
   - installs the run-time wheels into `Lib\site-packages` from `uv export --locked --no-dev` with hashes required and binary wheels only, for win_amd64 and CPython 3.14;
   - copies `backend/shelfsync`, `frontend/dist` as `ui\`, and `brand/assets/app/shelfsync.ico`;
   - precompiles with `compileall --invalidation-mode checked-hash`, so a first start writes nothing into `versions\<v>` (V47);
   - checks every executable's signature on Windows;
   - writes `build\files.txt` (relative path, size and SHA-256 of every file) for m1b.2's manifest.

   The version comes from `pyproject.toml` and must equal the tag in CI. Nothing here reads a secret.
2. **`packaging/ShelfSync.nsi`**, built-in plugins only (MUI2, nsDialogs, nsExec, System):
   - `RequestExecutionLevel user`; `InstallDir $LOCALAPPDATA\Programs\ShelfSync`; `Unicode true`;
   - the brand's `installer-header.bmp` and `installer-panel.bmp`;
   - **refuses to run while ShelfSync runs**: `instance.lock` can't be opened (wording for 13);
   - **refuses a Setup older than the installed version** (the database might be newer, and `db/migrate.py` would refuse it; wording for 13). The same version reinstalls (repair);
   - installs into `versions\<v>`, then re-points `current`. On reinstall or upgrade, keeps the data, the running version (the one `current` pointed at) and nothing older;
   - Start-menu and desktop shortcuts to `current\pythonw.exe -m shelfsync.launcher`, with `shelfsync.ico`;
   - the uninstall key exactly as m1b.2 §0 says, and the AUMID key;
   - the Finish page has "Open ShelfSync" ticked, which runs the shortcut's command. The wizard (SYS-01) is the app's own first screen;
   - **uninstall**, in this order:
     1. refuse while ShelfSync runs;
     2. if "Remove my data" is ticked (off by default), run `shelfsync.uninstall --remove-data`;
     3. remove the `current` junction itself first, without recursing;
     4. remove `versions\`, never following a junction out of `$INSTDIR` (V40: if `RMDir /r` can't be shown to stop at junctions, remove each version folder's links first);
     5. remove the shortcuts, the Run value, the AUMID key, the uninstall key and `$INSTDIR`.
3. **`.github/workflows/release.yml`**:
   - triggers: tags `v*`, and `workflow_dispatch`, which builds and tests only and uploads the build as a workflow artifact, with no release;
   - `windows-2025`; `permissions: contents: read` at the top. Only the job that makes the **draft** release gets `contents: write`;
   - actions pinned by commit SHA, reusing `checkout`, `setup-python`, `setup-uv` and `setup-node` at the commits `checks.yml` already pins (no new actions); `UV_PYTHON_DOWNLOADS: never`;
   - steps: build the UI (`npm ci`, `npm run build`); download NSIS 3.13 and check its pinned SHA-256; `build.py`;
   - **smoke test**: the built folder's `python.exe -m shelfsync` with a throwaway `SHELFSYNC_DATA_DIR` answers `/api/health` with the right version and serves `ui/index.html`, and afterwards nothing under `versions\<v>` has changed (V47);
   - `makensis`;
   - **silent install, then uninstall**: install, and check the junction, shortcuts and keys. Plant a sentinel: a junction inside `versions\<v>` pointing at a folder outside `$INSTDIR` that holds a file. Uninstall silently, waiting for it to end (NSIS's `_?=` rule), and check that `$INSTDIR` is gone and the sentinel file survived (V40);
   - on a tag: a draft release with `ShelfSync-Setup-<v>.exe` and `shelfsync-<v>-win64.zip`;
   - **the manifest step is a marked placeholder.** m1b.2's `update/manifest.py` writes `manifest.json` from `files.txt`, and the lead wires it in at integration (task 4);
   - no secret is used, and nothing is signed in CI (06 §6).

### Shared files
Follow the m1b.2 §0 contracts exactly:
- `server.py`: everything except the `migrate(connection)` call;
- `api/app.py`: only your own `include_router` lines and the `ui_dir()` change;
- `tray/launcher.py` is yours;
- the lock is yours (m1b.2 only calls `default_instance_lock()`);
- release asset names as listed there.

Don't touch `update/`, `db/backup.py`, `api/updates.py`, `api/secrets.py` or `tools/release/`.

### Done means
- **The CI checks pass:** ruff, format, mypy, pytest with the coverage gates, bandit and pip-audit. New Python code under `platform/`, `tray/`, `paths.py` and `uninstall.py` is tested with fakes on Linux:
  - `ui_dir()` in both layouts and the missing-UI error;
  - the lock's four cases (free, mutex taken, file taken, both);
  - `--background` (no first tab) and the rewritten Run value;
  - `request_quit` with and without a refusing guard;
  - the AUMID choice;
  - `--remove-data` (entries from the list removed, a planted junction in the data folder not followed, a non-zero exit when an entry can't be removed);
  - `build.py`'s pure parts (the `_pth` text, `files.txt`, the version check, a wrong hash refused).
- **`-m windows` checks**, with throwaway names and folders:
  - the lock file across two real processes;
  - the AUMID registry key written and removed;
  - the cold toast time;
  - `--remove-data` against a throwaway Credential Manager entry.
- **A local build and install on this PC**, with throwaway roots, from the extracted NSIS: `build.py`, `makensis`, then silent install and uninstall into a temporary `InstallDir` with the sentinel. Report each command and its result. A run inside the Claude app is virtualized (V36), so this is a rehearsal only. The real install, the clean-account test and the `reg query` checks are the owner's, outside Claude, at integration (task 4).
- **`release.yml` passes once by `workflow_dispatch` on the PR branch.** The lead triggers it, with the owner's yes, after the reviewer's APPROVE.
- **The builder report lists:**
  - every file changed and every command run, with its result;
  - the SHA-256 values recorded;
  - the proposed wording for 13;
  - what wasn't verified.

### Out of scope (owner)
- The updater, the manifest, signing, `tools/release/` and the uninstall key's `DisplayVersion` after an update: m1b.2.
- The Settings App API, logs pruned by age and the `httpx` warning filter: m1b.3.
- Screens: m1b.4.
- The `release.md`, `clean-account.md` and `key-rotation.md` runbooks, the README's install section with the SmartScreen note, the 13 wording, and making real releases: the lead, at integration.
- The optional install-folder image check and the socket-owner re-check: m1b.3, or noted as a follow-up.
- Authenticode signing: none, ADR 0002.
- Measuring "installs in under a minute" (13 §6): the exit test.

## 2. Early check
_(Tier B: none)_

## 3. Builder report
Builder: `builder` (Sonnet 5.5). Branch `m1b.1-build` (cut from `b46d73c`; the worktree had started on `a230782`). Nothing pushed.

**Skills and tools loaded (09 §3 rows):**
- Context7 for **windows-toasts** (`/websites/windows-toasts_readthedocs_io_en`: `InteractableWindowsToaster(applicationText, notifierAUMID=...)`, custom AUMID under `HKCU\Software\Classes\AppUserModelId`), **uv** (`/astral-sh/uv`: `uv export --no-dev`, `uv pip install --target --python-platform windows --python-version --require-hashes --only-binary :all:`) and **pystray** (`/moses-palmer/pystray`: `Icon.stop()` semantics; the tray code is unchanged).
- NSIS: Context7 has none. nsis.sourceforge.io couldn't be fetched (no web tool), and `hh.exe -decompile` of the local `NSIS.chm` produced nothing. I read the local `Include\MUI2.nsh`, `FileFunc.nsh`, `WordFunc.nsh` and `Contrib\Modern UI 2\Pages\Finish.nsh`, and settled the behaviours that mattered by running them (below). **Not verified against the official docs.**
- `security-review` and `code-review`: the reviewer's. `aws-*`, `frontend-design`, `dataviz`, `artifact-design`: don't apply (no S3, no screen, no page). `run`: not loaded; the built folder's smoke test is the check of the running app.

### Files changed (25; commits `0342ec6`, then the build and installer commits, then this report)
- **App:** `backend/shelfsync/paths.py` (`ui_dir()`, `source_ui_dir()`, `is_packaged_layout()`, `UiMissingError`, `DataPaths.instance_lock`), `api/app.py` (`UI_DIR` now comes from `paths.source_ui_dir()`; kept because `frontend/e2e/server.py` and `test_static_ui.py` import it), `server.py` (everything except `migrate(connection)`: `ui_dir()` at start-up, `UiMissingError` gives exit 3 and a notice), `messages.py`, `tray/instance.py`, `tray/launcher.py`, `platform/autostart.py`, `platform/notify.py`, `platform/aumid.py` (new), `platform/secrets.py` (`OWNED_SECRET_NAMES`), `secure/token.py` (name now from that list), `uninstall.py` (new).
- **Packaging:** `packaging/build.py`, `packaging/smoke.py`, `packaging/ShelfSync.nsi`, `packaging/test-installer.ps1`, `.github/workflows/release.yml`, `.gitignore` (+`build-cache/`).
- **Tests:** `tests/test_m1b1_launcher.py`, `test_uninstall.py`, `test_packaging_build.py`, `test_release_files.py` (new); `test_autostart.py`, `test_launcher.py`, `test_exit_guard.py` edited (the Run value now ends in `--background`; `launcher.main([], ...)`).
- Not touched: `update/`, `db/backup.py`, `api/updates.py`, `api/secrets.py`, `tools/release/`, `frontend/`, `brand/`, `docs/` other than this file.

### Contracts for m1b.2 (as built)
- `default_instance_lock()` keeps its no-argument signature. It returns `CombinedInstanceLock(WindowsInstanceLock(), WindowsFileLock(<data folder>\instance.lock))`.
- `app.state.request_quit: Callable[[], bool]` is set in `TrayServe.__call__` (the menu's Quit and the app's call are the same method; `False` when a quit guard refuses). The developer entry never sets it.
- `launcher.main(argv=None, *, ...)`: `argv` is new and first. Any caller must pass `[]` in tests (argparse would read pytest's arguments).
- `OWNED_SECRET_NAMES = ("install-token", "github-token")`. I added `github-token` because §0 names it for m1b.2's `api/secrets.py`; deleting an entry that was never stored is not an error. Remove it if m1b.2 names it differently.
- **Zip layout (decide at integration):** `shelfsync-<v>-win64.zip` holds the version folder's files with **no top-level folder**, in the same order and with the same paths as `build\files.txt` (`path<TAB>size<TAB>sha256`, sorted, forward slashes, LF). `files.txt` is not inside the zip.
- The installer finds "the version `current` pointed at" from the Uninstall key's `DisplayVersion` (the updater rewrites it after each switch), not by reading the junction.

### What was built, per item of the brief
1. `paths.ui_dir()`: a packaged layout (a `python*._pth` beside the package) uses `<version folder>\ui` and raises `UiMissingError` without `index.html` (exit 3, `messages.START_FAILED_UI_MISSING`); the source layout keeps `frontend/dist` (M1a "API only" line).
2. Data-folder lock: mutex first, then `instance.lock` opened with `CreateFileW` share mode 0 and `FILE_FLAG_OPEN_REPARSE_POINT`; a refused file lock gives the mutex back; a folder where the file should be is refused (fail closed). Fakes: `FakeInstanceLock` + `FakeFileLock` under `CombinedInstanceLock`.
3. `--background`: `argparse` (`allow_abbrev=False`; an unknown argument exits 2). The Run value is `"<...>\current\pythonw.exe" -m shelfsync.launcher --background`; the shortcuts and a second launch have no flag and open a tab. An M1a value without the flag is rewritten by the existing "unchanged" comparison.
4. `request_quit`: see contracts.
5. AUMID `TecHaust.ShelfSync`: an installed copy uses it **only when the key exists** (`aumid.is_registered()`); otherwise the M1a default, because Windows may drop a toast sent for an unregistered AUMID. The installer writes `DisplayName` and `IconUri`; the uninstaller removes the key. `platform/aumid.py` also has `register`/`unregister`, the twin of the installer's writes, used by the Windows tests.
6. Cold toast time: see commands.
7. `python -m shelfsync.uninstall --remove-data`: removes `OWNED_SECRET_NAMES`, then the data folder entry by entry with `paths.remove_entry`, carries on after a failure and exits 1; exit 3 (refused, nothing touched) unless the folder is named `ShelfSync*` or holds `shelfsync.db` (a wrong `SHELFSYNC_DATA_DIR` can't become a wide delete). **Bug found by its own test and fixed:** a data folder that was itself a junction was emptied through the link (`Path.is_symlink()` is False for junctions on Windows); it now uses `os.path.isjunction` too.
8. Strings: `messages.py` and the NSIS string table (wording below).
- `build.py`, `smoke.py`, `ShelfSync.nsi`, `test-installer.ps1`, `release.yml`: as the brief; details in the files' headers. `release.yml` adds no action (the four checks.yml SHAs plus `upload-artifact` v7.0.2); the draft job fetches the artifact with `gh run download` instead of `download-artifact` (a new action), needs `actions: read` besides `contents: write`, and runs no repository code. The manifest step is a comment placeholder.

### Findings that change what the docs say
- **04-A V40: confirmed on this PC.** A throwaway NSIS 3.13 program that makes a junction inside a folder and runs `RMDir /r` on the folder **deleted the file in the junction's target** (result `FOLLOWED`). So the installer and uninstaller never use `RMDir /r` directly: `UnlinkAll` first runs `cmd /c for /f ... in ('dir /AL /S /B "<dir>"') do rmdir "%i"` (removes each link itself), then `RMDir /r`. `test_release_files.py` forbids a bare `RMDir /r` in the uninstall section. The sentinel check passed with it.
- **V47: passed locally.** After a first start of the built folder (`python.exe`, throwaway data folder, in-memory secret store) the folder's 1,624 files are byte-identical (`checked-hash` precompile).
- **V38: partly.** The embedded Python plus the locked wheels starts the server and serves the UI here. This PC isn't a clean PC; CI's runner is the real answer.
- **V49 (cold toast):** 0.35 to 0.61 s from process start to `show_toast` returning (three runs: 0.61, 0.35, 0.37), a fresh `python -I` process, throwaway AUMID. **Under 5 s.** Caveat: that is the time to the call returning; whether the toast was rendered on screen in time (Focus Assist, this being inside the Claude app) was not observed.
- Raw `uv pip install --target` for win_amd64 works from the lock with hashes; `compileall` prints one harmless `SyntaxWarning` for `pystray/_util/gtk.py`.
- `python.exe` and 32 other files in the embeddable zip are signed by "Python Software Foundation" or "Microsoft Corporation" (the VC++ runtime DLLs): `build.py` accepts those two signers and refuses anything else (`Valid` status required).

### SHA-256 values
- Python embed zip `python-3.14.8-embed-amd64.zip`: `a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310` (computed by `build.py` on the downloaded file; equals the pin).
- NSIS zip: the pin `ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8` is in `release.yml`; not re-downloaded here (the lead extracted it).
- Local build (not reproducible, for reference only): `shelfsync-0.1.0-win64.zip` `cf02c8b42bb52977a16a1c6e4ccd3370418d064ed75502d40eaad1b434501205`; `files.txt` `a93bd5afa4e4f8730c87a52b659b1deb0c1fe28daef5ad9a33bde8f6737a620d` (1,624 files); rehearsal `Setup` `DC1145AD3DF5141C93CBCF4AA45F4232FCB4C1AD49BE9D315F5A8605ABD30A7F` (20,139,927 bytes). The built folder is 67 MB.

### Commands run (all with `UV_PYTHON_DOWNLOADS=never`) and results
| Command | Result |
|---|---|
| `uv sync --locked` | ok |
| `uv run ruff check` and `uv run ruff format --check` | All checks passed; 88 files formatted |
| `bash tools/heavy.sh --log mypy-full uv run mypy` | Success: no issues in 40 source files |
| `bash tools/heavy.sh --log pytest-full uv run pytest` | **774 passed, 12 skipped**, 37 deselected, exit 0 (87 % total). Run on Windows only; **not run on Linux**: the new tests are written to be portable (symlinks instead of junctions, Windows-only parts under `skipif`) but unproven there. The folders with a 90 % gate (`secure`, `inspect`, `match`, `apply`) are unchanged by this task apart from `secure/token.py`'s constant |
| `uv run bandit -r backend` | No issues identified (`packaging/` is outside bandit's CI scope; its `subprocess` and `urlopen` lines carry `nosec` notes) |
| pip-audit as CLAUDE.md describes | No known vulnerabilities found |
| `bash tools/heavy.sh --log pytest-windows uv run pytest -m windows --no-cov -s` | **36 passed**, 1 skipped (the V31 Defender check, owner-only), exit 0. Includes the new ones: the lock file across two real processes (held, refused, freed when the holder is killed), the AUMID key written, read and removed under a throwaway id, the cold toast, and the existing keyring and mutex checks |
| `bash tools/heavy.sh --log npm-ci npm ci --prefix frontend` and `... --log ui-build npm run build --prefix frontend` | 146 packages, 0 vulnerabilities; build ok (frontend/ files unchanged) |
| `bash tools/heavy.sh --log build-final .venv/Scripts/python.exe -I packaging/build.py` | exit 0, 1,624 files, run outside `uv run` as CI will |
| `... packaging/smoke.py build/ShelfSync-0.1.0 --version 0.1.0` | passed: version 0.1.0 answered, UI served, folder unchanged |
| `makensis /DVERSION=0.1.0 /DBUILD_DIR=... /DSUFFIX=-rehearsal` (NSIS v3.13, from `tools\nsis-3.13`, not copied) | exit 0, about 42 s, 20 MB |
| `bash tools/heavy.sh --log install-rehearsal-final powershell -File packaging/test-installer.ps1 -Setup ... -Version 0.1.0 -Root <throwaway> -Suffix -rehearsal` | **All installer checks passed** (35 checks): silent install exits 0; `current` is a junction to `versions\0.1.0`; both shortcuts have the right target, arguments and icon; every Uninstall-key value and the AUMID key; installed Python imports `shelfsync 0.1.0`; Setup refuses (exit 5) while `instance.lock` is held; sentinel junction planted; silent uninstall with `_?=` exits 0 and leaves only `uninstall.exe`; the file behind the junction survived; shortcuts, keys and Run value gone |
| Extra rehearsal (ad hoc script, same Setup built as 0.0.9, 0.1.0, 0.1.1, 0.1.2) | upgrade keeps old and new (`0.1.0,0.1.1`); an **older Setup is refused (exit 6)** and nothing changes; the next upgrade prunes to `0.1.1,0.1.2`; a repair of the same version removes nothing (I had it pruning the rollback copy; fixed before the final run); uninstall leaves no key |
| Rehearsal of `/REMOVEDATA` with a data folder that isn't ShelfSync's | the module refused (exit 3), the uninstaller carried on, the program was removed, the data file was kept |

All rehearsals used throwaway roots, the suffix `-rehearsal` on every key, value and shortcut, and a throwaway `SHELFSYNC_DATA_DIR`. The Desktop shortcut was written to this PC's real Desktop (OneDrive) under the throwaway name and removed by the uninstaller.

### Proposed wording for 13
In `messages.py`:
- `START_FAILED_UI_MISSING`: "ShelfSync is missing its screens, so it didn't start. Run the ShelfSync installer again to repair it. Details are in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log"

In the NSIS string table (`packaging/ShelfSync.nsi`):
- Running at install: "ShelfSync is running. Quit it from its tray icon, then run this installer again."
- Running at uninstall: "ShelfSync is running. Quit it from its tray icon, then run the uninstaller again."
- Older Setup: "This installer is ShelfSync <version>, but a newer ShelfSync is already installed. Installing an older version could damage your data, so the installer stopped. Download the newest installer, or uninstall ShelfSync first."
- Junction failed: "The installer couldn't switch ShelfSync to the new version. Nothing else was changed. Close any window showing the ShelfSync folder and run the installer again."
- Finish page checkbox: "Open ShelfSync"
- Uninstall page title: "Remove my data"; text: "ShelfSync keeps your database, backups and logs, and the sign-in token it stored for you, even after it is removed, so a later install picks up where you left off."; checkbox (off by default): "Remove my data too (the database, backups, logs and the stored token). This can't be undone."
- Data not fully removed: "ShelfSync couldn't remove all of your data. Delete what is left of this folder yourself:" followed by the folder.
- Exit codes of Setup/uninstaller: 5 running, 6 older, 7 junction failed.

### Not verified
- **`release.yml` has never run.** Untested in it: the SourceForge URL for `nsis-3.13.zip` (redirects; the hash check is the guard), `uv pip install --python` on a runner with no venv (I ran `.venv\Scripts\python.exe -I build.py`, which is close but not the same), the smoke with `--real-secrets` (the real `python -m shelfsync`, so keyring in the embedded Python), `gh run download` and `gh release create --draft --verify-tag` in the draft job, `-RemoveData` with the real Credential Manager. A local run of `-RemoveData` was impossible: it would delete this owner's real `ShelfSync` Credential Manager entries.
- The installer's **screens were never seen**: the Welcome, Finish ("Open ShelfSync" ticked and starting the app) and the uninstall "Remove my data" page, and the brand bitmaps in them. Silent mode skips them.
- **V36/V42:** every rehearsal ran inside the Claude app, whose `%LOCALAPPDATA%` and `%APPDATA%` (and possibly HKCU writes) are virtualized, so "the check saw its own files and keys" proves the script, not what Windows sees. The owner's clean-account install and `reg query` outside Claude are still needed.
- The `--background` sign-in start and a reboot; SmartScreen and Defender on the unsigned Setup (V48); whether the toast was visible within the cold-start time; the Linux CI run of the new tests; Start-menu shortcut placement under a normal (non-virtualized) `%APPDATA%`; the junction switch under an open file handle (`current` is re-pointed by `RMDir` then `mklink /J`, not atomically: V39 stays open for m1b.2's fault tests).
- The uninstaller removes `$INSTDIR` with a plain `RMDir` (only if empty), so anything unknown in the program folder's root is left behind rather than risking a recursive delete of a wrongly chosen `/D=` folder.

### Open questions for the lead
1. Zip layout (no top-level folder) and `files.txt` format: does m1b.2's `unpack.py`/`manifest.py` want something else?
2. `github-token` in `OWNED_SECRET_NAMES`: keep, or let m1b.2 add it?
3. `UI_DIR` stays in `api/app.py` as an alias of the source layout; `frontend/e2e/server.py` (the designer's) still imports it. Fine, or move that import at m1b.4?
4. Setup/uninstaller exit codes 5, 6, 7: any the runbook should name?
5. Should a repair (same version) re-run the keep-one-previous rule? As built it removes nothing.

## 4. Designer report
_(none: the installer uses the existing brand art)_

## 5. Review (round 1, SEND BACK)
Findings as sent by the lead; every fix is in commit `8beabd4` (branch `m1b.1-build`).

| Id | Where | Finding | Fix |
|---|---|---|---|
| HIGH 1 | `ShelfSync.nsi` `UnlinkAll`/`RemoveTreeSafely` | `dir /AL /S /B X` never lists X itself, so `RMDir /r X` follows X when it is a junction (the installer's pre-clean or prune of a version folder, or `versions` itself at uninstall); the guard also fails if an `rmdir` fails or the path doesn't survive cmd's code page | Both removed. `DeleteTree` (System plugin, `GetFileAttributesW` on every entry, the top folder included): a reparse point (0x400) is removed itself with `RMDir`/`Delete`, real folders only are entered, and if anything is left the whole delete stops, a notice names the path and the exit code is 8. `test-installer.ps1` cases: a version folder that is a junction (pre-clean and prune), `versions` itself a junction, a junction held open so it can't be removed (exit 8, nothing behind it deleted, a second run succeeds), a link inside a junction's target |
| MEDIUM 1 | nsi `current` | `current` removed before `mklink`: a failed `mklink` leaves no `current` | `current.next` is made first (a failure leaves `current` untouched); then `current` is moved to `current.old`, `current.next` into place, and `current` is put back if that fails. `STR_LINK_FAILED` now says the installed version was left as it was |
| MEDIUM 2 | `uninstall.py`, `test_uninstall.py` | A data folder that is itself a link was unlinked, not reported | Left alone; exit 1 and the target is printed (so the uninstaller shows its partial notice); test updated |
| MEDIUM 3 | nsi, `uninstall.py` | The "running" check is only in `.onInit`/`un.onInit` | `IsRunning`/`un.IsRunning` again at the top of both sections (exit 5). `remove_data` holds `default_instance_lock(paths)` for the whole job and refuses (exit 4, a new NSIS notice) if it is held or can't be checked; the lock file is removed last, after the lock is let go |
| LOW 1 | `server.py`, `tray/instance.py` | `OSError` from `acquire()` gave the generic notice | It gives `START_FAILED_DATA_FOLDER`; `default_instance_lock(paths=None)` takes the data folder `run_application` resolved (no-argument calls still work) |
| LOW 2 | `tray/instance.py` | A sharing violation was decided at once | Retried for 1 s; a folder where the file should be is still refused at once |
| LOW 3 | nsi | Bare `cmd` | `"$SYSDIR\cmd.exe"` (the only remaining use, `mklink`) |
| LOW 4 | nsi | `--remove-data` exit 3 told the owner to delete the folder | New `STR_DATA_NOT_OURS` ("left this folder alone ...") |
| LOW 5 | nsi, `uninstall.py` | A `-rehearsal` build's `/REMOVEDATA` would touch the real Credential Manager service | `--service ShelfSync${SUFFIX}` is always passed; the module takes `--service` and accepts only `ShelfSync[A-Za-z0-9._-]*`. The `-RemoveData` rehearsal now runs locally |
| LOW 6 | `tray/launcher.py` | A `--background` second launch opened a tab | Exits 0 quietly, no tab, no toast |
| LOW 7 | `tray/launcher.py` | `add_quit_guard` docstring | Guards may run on the tray's or a server thread: thread-safe, never block on either loop |
| LOW 8 | `platform/notify.py` | `_toaster_aumid` written, never read | Dropped |
| LOW 9 | nsi | Older-Setup guard used only `DisplayVersion` | Also compares every version folder name under `versions\` that starts with a digit; tested by setting `DisplayVersion` to 0.0.0 |
| LOW 10 | `packaging/build.py` | Signer compared as a substring | `subject_fields()` parses `CN=`/`O=` and compares them exactly; spoofed subjects are tested |
| LOW 11 | `test-installer.ps1`, `release.yml` | No CI test for exit 6, the prune and the running refusal; exit 5 not exact | The script covers all three (and the running refusal for the uninstaller), expects exit 5 exactly; `release.yml` compiles two extra `/DFAST` Setups (0.0.1, 99.0.0, test files only) and passes them |
| LOW 12 | `tray/instance.py`, `secure/token.py` | `FakeFileLock`; the `INSTALL_TOKEN_NAME` alias | `FakeFileLock` merged into `FakeInstanceLock`. The alias is **kept**: `second_launch`, `launcher`, the token code and many tests import `INSTALL_TOKEN_NAME` from `secure.token` |
| Extra | `_pth` | Does `python314._pth` give isolated mode? | **Yes** (checked): in the built folder `sys.flags.isolated == 1`, `safe_path == True`, `PYTHONPATH` is ignored and the working folder is not on `sys.path` (a `json.py` and a probe module in the cwd with `PYTHONPATH` set were not loaded). `smoke.py` now asserts it, so a start from any working folder loads nothing from it; no shortcut start-in change was needed |

## 3b. Fixes (round 2 note, then round 1)
Round 2 follow-ups (table in §5) are fixed in the commit after `ad9a9b8`. Re-run: ruff check and format clean (89 files); mypy no issues (40 files); bandit no issues; `pytest` **797 passed, 12 skipped** (Windows only); `pytest -m windows --no-cov` **38 passed**, 1 skipped (V31); `build.py` (the stricter signer parse accepted all 33 real signatures) and `smoke.py` passed; four Setups compiled; local rehearsal `test-installer.ps1 ... -RemoveData`: **89 checks, all ok** (`.logs/install-rehearsal-r3.log`), including the killed-switch recovery, the junction-derived prune and `current.old` at uninstall. The notice texts shown by `MessageBox` were not seen (silent runs only).

### Round 1
All of §5's findings are fixed in `8beabd4`. Re-run after the fixes (all with `UV_PYTHON_DOWNLOADS=never`):
- `ruff check` and `ruff format --check`: clean (89 files). `mypy`: no issues, 40 files. `bandit -r backend`: no issues. `pip-audit`: not re-run (no dependency changed since the last clean run).
- `pytest`: **786 passed, 12 skipped** (Windows only; Linux not run). `pytest -m windows --no-cov`: **38 passed**, 1 skipped (the V31 Defender check).
- Rebuilt: `build.py` (exact signer check passed on all 33 files), `smoke.py` (now also asserts the isolated Python): passed. Four Setups compiled with `makensis` v3.13 (`-rehearsal` suffix; the 0.1.0 one, 0.0.1 and 99.0.0 with `/DFAST`).
- Local rehearsal, `test-installer.ps1 ... -OlderSetup -NewerSetup -NewerVersion 99.0.0 -RemoveData`: **70 checks, all ok** (log `.logs/install-rehearsal-r2.log`). Includes: install, contract keys, shortcuts; Setup and uninstaller both refuse with exit 5 while `instance.lock` is held; sentinel junction survives; a version folder that is a junction survives the installer's pre-clean and its prune; `versions` as a junction survives the uninstall; a held junction makes the uninstall stop with exit 8 and delete nothing behind it, and the retry finishes; upgrade keeps `0.1.0` and `99.0.0` only; a repair removes nothing; an older Setup is refused with exit 6, also when only the version folders show it; `/REMOVEDATA` removed the throwaway data folder and spared the file behind a junction inside it (the suffixed build used the throwaway Credential Manager service `ShelfSync-rehearsal`).
- Still not verified: the same list as in §3 (release.yml never run; installer screens; clean-account and `reg query` outside Claude). New: the NSIS `DeleteTree` was exercised through the CI-style script only, not through the GUI uninstaller.

### Review round 2 (APPROVE) and follow-ups
| Id | Where | Follow-up | Fix |
|---|---|---|---|
| 1 MEDIUM | nsi `STR_UNSAFE` | Wrong for any entry that can't be deleted | Neutral wording in two strings (`STR_STUCK_SETUP`, `STR_STUCK_UNINSTALL`): couldn't remove a file or link in its program folder; close any window using it and run again. `DeleteTree` now returns the stuck path (deepest first) and the notice shows it |
| 2 | nsi `DeleteTree` | Any `-1` counted as gone | `GetFileAttributesW ... ?e`, then the last error is read: only 2 and 3 mean gone; any other error is a failure, for the top folder, for children and in the final check |
| 3 | nsi swap | The restore rename wasn't checked | Checked; a failure shows the new `STR_RESTORE_FAILED` ("run the installer again to finish the install", exit 9). A restore is only tried when `current` had been moved aside |
| 4 | nsi uninstall | `current.old` left behind | Removed with `RMDir` (no `/r`), next to `current.next` |
| 5 | `uninstall.py` | A dangling junction reported "running" | The `is_link(root)` check (exit 1, target printed) now runs before the lock; nothing else is removed in that case |
| 6 | `uninstall.py` | `exists()` on the lock file | `os.path.lexists` |
| 7 | `uninstall.py` | A failed `--service` store fell back to the real service | `UnavailableStore` (every delete fails, so every entry is reported); no store for another service is ever built |
| 8 | `build.py` | Loose subject parsing | `subject_fields` reads in order, each match starting where the last ended, and refuses a subject that doesn't parse completely |
| 9 | nsi prune | Kept only the registry's `DisplayVersion` | The target of `current` and of a leftover `current.old` is read from the junctions themselves (`CreateFileW` + `GetFinalPathNameByHandleW`) before anything changes and kept as well |
| 10 NEW | nsi, `test-installer.ps1` | Setup again must recover a missing `current` with `current.old`/`current.next` left over (a switch killed between its two renames) | The swap already removed both leftovers (`RMDir`, no `/r`) and creates `current`; now proven. Planted in `test-installer.ps1` ("recover", "recover-upgrade", and a leftover `current.old` at uninstall), so `release.yml` runs it |

Tests added: `test_uninstall.py` (dangling link before lock, `lexists`, no fallback service), `test_packaging_build.py` (subjects that don't parse completely, real-looking subjects), `test_release_files.py` (the script guards, the planted switch), and in `test-installer.ps1` the "recover", "keep-current" (registry says 0.0.3 while `current` points at the running version: that one is kept) and "recover-upgrade" scenarios.

### Review round 3 (APPROVE) and the item 5 regression
| Id | Where | Finding | Fix |
|---|---|---|---|
| M1 | `uninstall.py` | With the link check first, a data folder that is a link no longer had its Credential Manager entries removed | The link check stays first, then: a live link takes the lock through it (exit 4 if held, nothing removed); a dangling one skips the lock; in both cases `remove_secrets` runs, the link line is printed and the exit is 1. Tests assert the secrets are gone for a live and a dangling link, and that a held live link refuses. `STR_DATA_PARTIAL` is now true for it (data behind a link is left in place; the stored token was removed where possible) |
| L1 | nsi `GetLinkVersion` | Used `$R2` whatever `GetFinalPathNameByHandleW` returned | Only when `0 < $R4 < 1024` |
| L2 | nsi swap | With no `current` to begin with, a failed final rename said `STR_LINK_FAILED` | `STR_RESTORE_FAILED` (exit 9: the install has no `current`, run the installer again) |
| L3 | nsi uninstall | "Remove my data" used only `current\python.exe` | Falls back to `current.old\python.exe`, then `current.next\python.exe`; if none exists the new `STR_DATA_NOTHING` says nothing was removed (data and token included) and the program is still removed |
| L4 | `test-installer.ps1` | `Plant-KilledSwitch` pointed both leftovers at one folder | `current.old` is the running version, `current.next` is the new version's folder (it exists). New scenarios "remove-data-killed-switch" (data removed with `current.old`'s Python) and "remove-data-no-python" (nothing removed, data kept, program removed). The exit-9 path is **not** exercised: forcing the final rename of the freshly made `current.next` to fail isn't cheap, so it is checked as text only |

Re-run: ruff check and format clean (89 files); mypy no issues (40 files); bandit no issues; `pytest` **799 passed, 12 skipped**; `pytest -m windows --no-cov` **38 passed**, 1 skipped (V31); `build.py` and `smoke.py` passed; four Setups compiled; local rehearsal with `-OlderSetup -NewerSetup -RemoveData`: **97 checks, all ok** (`.logs/install-rehearsal-r4.log`). The notice texts were not seen (silent runs).

### Review round 4 (APPROVE for the PR) and small fixes
| Id | Where | Finding | Fix |
|---|---|---|---|
| N1 | nsi `STR_RESTORE_FAILED` | Wrong on one of its two paths | "...couldn't finish switching ShelfSync to the new version, so it has no working version right now. Run the installer again to finish the install." |
| N2 | nsi, `uninstall.py` | A Credential Manager failure shared the data-left notice; a non-numeric `$3` fell into it | Exit 5 = only an entry couldn't be removed, 6 = both, 1 = data left (now only data); new `STR_DATA_SECRETS` names Credential Manager and says the token may still be stored; `STR_DATA_PARTIAL` is for data only. Anything else in `$3` (99 no Python, nsExec "error" or "timeout", exit 2, a crash) is `STR_DATA_NOTHING`. Tests for 1, 5 and 6 and for the nsi branches |
| N3 | `uninstall.py` | A dangling link skipped every lock | The session mutex (`WindowsInstanceLock`) is taken on its own (injectable `session_lock`); held or unavailable gives exit 4 and nothing removed |
| Order | nsi | "Remove my data" fallback | `current`, then `current.next` (the newer build, with the longer `OWNED_SECRET_NAMES`), then `current.old` |
| Port | test run | The reviewer's run hit a held 127.0.0.1:47615 | Checked before the full run (`Get-NetTCPConnection -LocalPort 47615`: nothing listening; `heavy.sh` also queues behind the other builder's runs). The clean run is reported below |

Re-run: ruff check and format clean (89 files); mypy no issues; bandit no issues; `pytest` **802 passed, 12 skipped** (clean run, port free); `pytest -m windows --no-cov` **38 passed**, 1 skipped (V31); `build.py` and `smoke.py` passed; four Setups compiled; local rehearsal `-OlderSetup -NewerSetup -RemoveData`: **97 checks, all ok** (`.logs/install-rehearsal-r5.log`). The notice texts were not seen (silent runs), and exit codes 5 and 6 are exercised by the Python tests only, not by a real Credential Manager failure.

## 6. Integration notes
_(lead)_

## 7. Handover
_(lead, 2026-10-27)_ Brief written, waiting for the owner's yes. Then:
1. the lead downloads NSIS 3.13 and pins its hash;
2. the builder starts (Sonnet medium, own worktree);
3. the m1b.2 final brief at Opus high, so both builders can run side by side.
