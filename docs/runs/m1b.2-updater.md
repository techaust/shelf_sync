Status: open (brief draft; the final brief is written by the lead at Opus high, 12 §3 key step 1)
Tier: A ([12 §2](../12-models-and-usage.md): the updater signature check)
Usage: `analyst claude-opus-5-5/high` (no 09 §3 skill fits a planning draft): 5-h 3 → about 20 %

# M1b.2: Updater (and the M1b plan)

## 0. M1b plan (analyst draft, 2026-10-27; owner answers below)

### Owner answers (2026-10-27, rows in [11](../11-decisions.md))
- Python **3.14** replaces 3.12: the first M1b task (m1b.0). Every locked package is checked for 3.14 wheels first.
- Real test releases on the public repo: `v0.1.0`, `v0.1.1`, and a short-lived `v0.1.2` signed with a throwaway key, which the app must refuse (then deleted).
- The signing key lives in the owner's CREDENTIALS folder plus an offline copy.
- "Remove my data" at uninstall also removes the Credential Manager entries.
- About 3.5 days; the lead re-plans with the owner if day 3 ends without the exit test.
- NSIS from its portable zip on this PC.
- Earlier the same day: the update token is optional; the clean-install test uses a new local Standard account the owner creates.

### Tasks
| Order | Task | Tier | Agent | PRD IDs | Depends on |
|---|---|---|---|---|---|
| 0 | **m1b.0-python-3.14**: re-lock for 3.14, `requires-python`, mypy target, CI, `.python-version`, local Python via uv | B | `builder` Sonnet medium | NFR-7 | Package list approved |
| 1a | **m1b.1-packaging**: NSIS installer, embedded Python build, `release.yml`, `ui_dir()`, data-folder lock file, `--background` Run value, toast AUMID, cold-toast timing | B (+ `security-review`, installer row of 09 §3) | `builder` Sonnet medium | SYS-01, SYS-08, SYS-04 | m1b.0 |
| 1b | **m1b.2-updater** (this file) | **A** | `builder` Sonnet high → `analyst` early check → `reviewer` Opus high (`code-review` + `security-review`) | SYS-06, SYS-07, SET-04 (backend), 06 §6 | m1b.0; in parallel with 1a under the contracts below |
| 2 | **m1b.3-app-settings**: Settings API for UI-SET App, logs pruned by age, the `httpx` warning filter | B | `builder` Sonnet medium | SET-06, LOG-01 | m1b.1 merged |
| 3 | **m1b.4-settings-screens**: UI-SET Updates and App, ConfirmDialog (native `<dialog>`), SecretField, Switch | C code, A effort (first build of these screens) | `designer` Opus high → `reviewer` high (visual) | UI-SET Updates, UI-SET App | m1b.2 and m1b.3 API merged |
| 4 | Integration, releases, signing, exit test with the owner outside Claude | — | lead + owner | all | 1–3 merged |

At most two agents at once, never two with a browser: m1b.1 ∥ m1b.2; then m1b.2's early check and fixes ∥ m1b.3; then m1b.4 alone with the browser.

**Shared-file contracts for the parallel builders:**
- `server.py`: m1b.2 changes only the `migrate(connection)` call; m1b.1 changes the rest.
- `api/app.py`: each task adds only its own `include_router` lines; m1b.2 adds `app.state.updates` through a keyword-only `updates=` argument to `create_app` (default: a "development, updates off" service).
- `tray/launcher.py`: m1b.1 only. It publishes `app.state.request_quit: Callable[[], bool]`; m1b.2 reads it and answers 409 when it's missing (developer entry).
- Lock: m1b.2 calls `default_instance_lock()`; m1b.1 makes it cover the mutex and a data-folder lock file.
- Uninstall key `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\ShelfSync`: `DisplayName` "ShelfSync", `DisplayVersion` (NSIS, then the updater after each switch), `Publisher` "TecHaust Technologies", `DisplayIcon`, `UninstallString` `"<root>\uninstall.exe"`, `InstallLocation`, `NoModify`=1, `NoRepair`=1.
- Release assets: tag `v<X.Y.Z>`; `ShelfSync-Setup-<v>.exe`, `shelfsync-<v>-win64.zip`, `manifest.json`, `manifest.json.sig`.

**Installer notes for m1b.1** (inference unless verified): `RequestExecutionLevel user`; `InstallDir $LOCALAPPDATA\Programs\ShelfSync`; `versions\<v>\` plus a `current` junction made with `cmd /c mklink /J` (no admin, V39); `uninstall.exe` at the root; shortcuts run `current\pythonw.exe -m shelfsync.launcher`; refuses to run while ShelfSync runs (the lock file); keeps data and one previous version on reinstall; the uninstaller removes the `current` junction first without recursing, never follows a junction out of `$INSTDIR` (V40), removes the Run value and the uninstall key, and removes the data folder and the Credential Manager entries only when "Remove my data" is ticked. Built-in plugins only (MUI2, nsDialogs, nsExec, System). `release.yml` (tags `v*` only, `windows-2025`) builds the UI and the folder, smoke-tests `/api/health`, runs `makensis`, installs and uninstalls silently with a planted-junction sentinel, writes the unsigned manifest and makes a draft release (only that job gets `contents: write`).

**Gaps found in M1a code (for m1b.1):** the Run value has no flag and the first copy always opens a tab (`platform/autostart.py:115-118`, `tray/launcher.py:62,136`), so every Windows sign-in would open the browser; the approved wording says ShelfSync starts in the tray. The mockup's Updates empty state ("Add a read-only GitHub token to check for updates.", `docs/05-design-system-appendix/mockup/js/screens-b.js:591`) contradicts the optional token: new wording for 13.

### Package and tool list (analyst draft; versions still to check from the registries)
| Kind | Item | Why |
|---|---|---|
| Python, run time (new) | cryptography | Ed25519 verify; also the release tools (and AES-GCM in M2). Its dependencies (`cffi`, `pycparser`) to check |
| Python, dev | none | GitHub mocked with `httpx.MockTransport`; hypothesis is locked |
| npm | none | native `<dialog>`; icons already in lucide-react |
| CI | `windows-2025` runner for releases | NSIS preinstalled there? (V50) |
| PC tool | NSIS 3.x portable zip (owner: yes) | local `makensis` |
| PC + CI | Python 3.14 embeddable package, amd64 | the shipped runtime; pinned SHA-256 plus `Get-AuthenticodeSignature` on every `.exe`/`.dll`/`.pyd` (PSF signer) |
| PC | Python 3.14 for development (through uv) | m1b.0 |
| Signing helper | our own `tools/release/{keygen,sign,verify_setup}.py` on cryptography | no certificate (ADR 0002) |

Record fixes found: 04 §7's "token decided in the M1b brief" is settled; 11's certifi row: certifi is already run time (httpx moved there in M1a.4); `key-rotation.md` is needed at M1b.

### Risks (04-A rows to add)
R1 Python 3.12 builds (settled: 3.14). R2 the junction switch isn't atomic (V39, fault tests). R3 the switch process may die with its parent's job (V43, outside Claude). R4 toast AUMID by registry may not be enough (V41). R5 HKCU writes may be virtualized inside the Claude package (V42; owner's `reg query`). R6 NSIS `RMDir /r` following a junction (V40, CI sentinel). R7 a missing stdlib module or VC++ runtime in the embedded Python; a second account on this PC isn't a clean PC (V38, CI smoke start). R8 `.pyc` writes changing `versions\<v>` (V47, `compileall --invalidation-mode checked-hash`). R9 GitHub details: drafts and prereleases in `releases/latest`, asset redirect hosts, 60 requests an hour without a token, the expiry header's format (V45, V26). R10 the owner signs what CI built (`sign.py` shows `source_commit`; residual risk in 06 §10). R11 SmartScreen or Defender on the unsigned `Setup.exe`; Smart App Control state (V48). R12 cold toast vs the 10 s stage 2 (V49). R13 NSIS on `windows-2025` (V50). R14 "installs in under a minute" not measured. R15 cryptography's encrypted key format (V46).

**Done by the owner outside the Claude app (V36):** create the Standard account; `keygen.py` and `sign.py`; `verify_setup.py` before the first install; installs on this PC and the clean account; the update, the refused tampered release, Roll back app; uninstall with and without "Remove my data" and a reinstall; `pytest -m windows`; `reg query` for the Run, Uninstall and AUMID keys; one reboot for Start with Windows.

## 1. Brief
_(analyst draft, 2026-10-27; the lead writes the final at Opus high. Summary of the draft's items; the full text is the analyst's report of 2026-10-27, which the final brief replaces.)_

**Key design points:**
1. The switch and the health check are run by the known-good version in a separate process (`python -m shelfsync.update.switch`, started from `versions\<current>\pythonw.exe`), which waits for the app to quit, holds the single-instance lock while it moves `current`, starts the new version, checks its health and switches back if needed.
2. A rollback after a migration restores the pre-migration backup **before** the old version starts: `db/migrate.py:77-82` refuses a database written by a newer version (exit 2). So SYS-07's backup is part of this Tier A task.

**Items:** `update/versions.py` (strict X.Y.Z); `update/manifest.py` (canonical JSON: format, app, version, tag, source_commit, built_at, schema_version, assets, files; Ed25519 signature over the exact bytes, verified **before** parsing; duplicate keys, bad paths and case duplicates refused); `update/release_key.py` (`PUBLIC_KEY` None until the owner's key exists → every install refused; nothing can replace it); `update/github.py` (`releases/latest`, token only if set and only to `api.github.com`, `trust_env=False`, redirects followed by hand to an allowlist without the token, no URL query strings logged; outcomes token_refused, rate_limited, not_public, unreachable; the 14-day expiry notice); `update/download.py` (stream, hash, size cap, free-space check); `update/unpack.py` (06 §4 entry checks; the tree must equal `manifest.files`; `.incoming-<v>` then rename); `update/layout.py` (`SHELFSYNC_INSTALL_DIR` for tests only); `db/backup.py` (online backup before pending migrations on a non-empty database; restore on failure; integrity checks); `update/state.py` (`update\state.json`, `result.json`); `update/service.py` (check at start + 60 s, then every 24 h, and on Check now; background download and verify; single-flight install and rollback; re-verify a kept folder before using it); `update/switch.py` (wait for the old PID up to 70 s; lock; junction `current.next` → rename; `DisplayVersion`; start; health check by `runtime.json`, the V33 owner check with the target's images given explicitly, `/api/health` version, still healthy 5 s later; never sends the install token; on failure end its own child, restore the backup if the schema moved, re-point, start and check the old version; prune to two versions on success); `platform/junction.py`, `platform/process.py`, `platform/uninstall_entry.py` (with fakes); `api/updates.py` and `api/secrets.py` (`github-token` only; write-only; masked; DELETE allowed; behind the deny-by-default guard and in the route-walk test); `tools/release/{keygen,sign,verify_setup}.py` (owner, outside Claude, `getpass`); every new owner-facing string proposed for 13.

**Tests:** the signature cases (unsigned, wrong key, tampered bytes, any single-bit flip by hypothesis, valid signature with bad content, no key in the build, no setting can change the key); download (hash, size, cap, redirect allowlist, no token to the asset host, nothing secret in logs); unpack (zip-slip, extra, missing, wrong hash); token outcomes and the 10-day/15-day notice; SYS-07 (backup only when needed, restore on a failed second migration, a fixture of the previous release's schema); the switch's happy path and each health-check failure (no answer, wrong version, exit 2, untrusted listener), rollback with and without a migration, missing backup, old copy that won't quit, a fault after each step, a tampered previous folder, development copy 409, second install 409, no install-token read; API guard cases. Windows checks: real junction, detached child surviving its parent (V43), image path through a junction (V44), `DisplayVersion` on a throwaway key, no file change after one start (V47).

**Done means:** the CI checks; ≥ 90 % coverage on `update/` and `db/backup.py` (the lead adds `update` to `checks.yml`); `-m windows` inside and then outside Claude; a local rehearsal with throwaway roots and keys (install 0.0.1 → update 0.0.2 → roll back; tampered 0.0.3 refused; broken 0.0.4 switched back).

**Out of scope:** NSIS, `packaging/`, `release.yml` (m1b.1); the Settings App API (m1b.3); screens (m1b.4); BAK-01 daily backups (M2; must never delete a pre-migration backup a kept version needs); M2 secrets; delta updates; automatic install without asking; Authenticode signing; reproducible builds; the M5 upload quit guard.

## 2. Early check
_(analyst, once `manifest.py`, `versions.py`, `release_key.py`, `github.py`, `switch.py`, `db/backup.py` and the API routes are committed)_

## 3. Builder report
_(builder)_

## 4. Designer report
_(screens are m1b.4)_

## 5. Review
_(reviewer)_

## 6. Integration notes
_(lead)_

## 7. Handover
_(lead, 2026-10-27)_ The analyst's M1b plan and updater draft are saved above, and the owner answered every question (§0). Next: check the package list (Python 3.14 wheels for every locked package; versions of cryptography, Python 3.14, the 3.14 embeddable zip and NSIS, each the newest release at least 14 days old) and put it to the owner for one yes; then m1b.0 (the Python move); then the final briefs, this one at Opus high.
