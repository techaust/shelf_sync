Status: open (brief written; waits for the owner's yes)
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
_(builder)_

## 4. Designer report
_(none: the installer uses the existing brand art)_

## 5. Review
_(reviewer: `code-review` + `security-review`)_

## 6. Integration notes
_(lead)_

## 7. Handover
_(lead, 2026-10-27)_ Brief written, waiting for the owner's yes. Then:
1. the lead downloads NSIS 3.13 and pins its hash;
2. the builder starts (Sonnet medium, own worktree);
3. the m1b.2 final brief at Opus high, so both builders can run side by side.
