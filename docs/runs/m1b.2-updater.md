Status: ready for PR (reviewer approved, re-check round 2 approved; builder follow-ups done 2026-10-27)
Tier: A ([12 §2](../12-models-and-usage.md): the updater signature check)
Usage: `analyst claude-opus-5-5/high` (no 09 §3 skill fits a planning draft): 5-h 3 → about 20 %; lead `claude-opus-5-5/high` (12 §3 key step 1) wrote the final brief: 5-h 37 → 49 % (the m1b.1 builder running meanwhile)

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
_(final, by the lead at Opus 5.5 high, 2026-10-27; it replaces the analyst's draft. Every point of the draft is kept unless it says otherwise)_

### PRD IDs and threat
SYS-06 (in-app updates, signed), SYS-07 (backup before migrations, restore on failure), SET-04 (the Updates API, no screen), [06 §6](../06-security.md).

The guarantee this task must keep: **ShelfSync installs no code whose manifest isn't signed by the owner's offline Ed25519 key, and every file is checked against that manifest.** That holds even if someone took over the GitHub account or the network.

Accepted residual risks (to go in 06 §10):
- **Freeze.** GitHub could hide a newer release, so the app never sees it.
- **Local malware.** Malware running as the owner can change anything on the PC.
- **The owner signs what CI built.** `sign.py` shows `source_commit`, so the owner can check it first.

### Agent and skills
1. **`builder`**, Sonnet 5.5 at **high**, in its own worktree, on branch `feat/m1b.2-updater` (cut from the m1b.1 brief commit `b46d73c`). It never pushes.
   - No other row of 09 §3 applies: there's no S3 here.
   - Before writing code it loads Context7 for cryptography (`/pyca/cryptography`), httpx, FastAPI and Python's `sqlite3` backup API.
   - It reads `security-review`'s checklist before the early-check commit.
2. **`analyst`**, Opus high: the early check (§2).
3. **`reviewer`**, Opus high: `code-review` and `security-review`.

### Facts checked for this brief (2026-10-27; rows in [04-A](../04-architecture-appendix/A-stack-verification.md))
- **`GET /repos/{owner}/{repo}/releases/latest`** returns "the most recent non-prerelease, non-draft release" (docs.github.com, V45). Without a token GitHub allows **60 requests an hour per IP**, reported in `x-ratelimit-limit` and `x-ratelimit-remaining`. Going over gives **403 or 429** with `x-ratelimit-remaining: 0` (docs, and seen on a public repo today).
- **An asset requested with `Accept: application/octet-stream`** answers either **200 or 302**, and clients must handle both (docs). Seen today without a token: one `302 Found` to `https://release-assets.githubusercontent.com/...`, for both the API's asset URL and `browser_download_url`.
- **`github-authentication-token-expiration`** is **not in GitHub's documentation pages checked today** (REST troubleshooting, and "Token expiration and revocation"). V26 stays "to verify", with the owner's real token at the exit test. The design already copes when the header is missing: no early notice, and the "token expired" message still appears.
- **cryptography:**
  - `Ed25519PublicKey.from_public_bytes` takes exactly 32 raw bytes (otherwise `ValueError`);
  - `private_bytes(PEM, PKCS8, BestAvailableEncryption(pw))` gives `-----BEGIN ENCRYPTED PRIVATE KEY-----`;
  - the docs say BestAvailableEncryption's algorithm "may change over time". So `keygen.py` records which algorithm it actually wrote, `sign.py` must load any file `keygen.py` made, and a test proves that (V46).

### Decisions taken in this brief (rows in [11](../11-decisions.md), "Lead (proposed)")
1. **The signature is raw:** `manifest.json.sig` is exactly the 64 bytes of Ed25519 over the exact bytes of `manifest.json`. Anything else is refused. The signature is checked **before** the JSON is parsed.
2. **Never a downgrade by update:** a manifest is accepted only if its `version` is strictly higher than the installed version, its `tag` is `v` + `version`, and it matches the release it came from. Only "Roll back app" goes back, to the kept folder.
3. **Each version keeps its manifest:** `Programs\ShelfSync\manifests\<v>.json` and `<v>.json.sig`, outside the version folders. The first install (by `Setup.exe`) has no manifest yet, so at the first successful check the service downloads the **running** version's own signed manifest from its release, verifies it and stores it. Roll back refuses a folder that has no verified manifest, or whose files don't match it.
4. **Hosts allowed for downloads:** `api.github.com`, `github.com` and `release-assets.githubusercontent.com` (seen today).
   - HTTPS only, at most 3 redirects, followed by hand.
   - Any other host is refused, and the log names the host only.
   - The token goes **only** to `api.github.com`, never across a redirect.
   - If GitHub adds a host later, updates fail safe until a release adds it to the list.
5. **The switch code that runs is the old version's:** `switch.py` runs from the version being left. Its command line is a versioned contract (`--format 1`), and v0.1.0's switch must already be right.
6. **Wiring:** `server.py` may be changed in exactly two places, which amends the m1b.2 §0 contract:
   - the `migrate(connection)` call;
   - one `updates=` keyword on the `create_app(...)` call. This line conflicts with m1b.1's `ui_dir=` change, and the lead merges both at integration.

   `api/app.py` gets a lifespan that starts and stops the service.
7. **After a successful switch, a signed-in tab opens.** The switcher never reads the install token. It starts the new version with `--background`, and once the version is healthy it runs one plain `pythonw -m shelfsync.launcher`. That is a second launch, so the running copy opens the tab with its own ticket.
8. **The token setting** accepts only fine-grained tokens:
   - `github_pat_` + 20–255 characters of `[A-Za-z0-9_]`;
   - stored as Credential Manager entry `github-token`, registered with `redact` when set and at start;
   - added to m1b.1's "Remove my data" list;
   - `GET` says only `{"set": true|false}` and the expiry date if known. The token is never returned, masked or not.
9. **No toast for "update ready" in M1b:** toasts that can be clicked are SYS-05 (M5), so m1b.4 shows the notice in the app.

### What to build (draft items kept; settled details added)

**Signing and the manifest**
- **`update/versions.py`:** strict `X.Y.Z`, no leading zeros, no pre-release, compared as integers.
- **`update/manifest.py`:**
  - `manifest.json` is UTF-8 JSON written canonically (`sort_keys`, `separators=(",", ":")`, `ensure_ascii=False`, no trailing newline). Fields:
    - `format` (1), `app` ("shelfsync"), `version`, `tag`, `source_commit` (40 hex), `built_at` (UTC ISO);
    - `schema_version` (the highest migration number);
    - `assets` (name → `{size, sha256}`, for `ShelfSync-Setup-<v>.exe` and `shelfsync-<v>-win64.zip`);
    - `files` (relative path with `/`, mapped to `{size, sha256}`).
  - Refused: duplicate keys (`object_pairs_hook`), unknown or missing fields, paths with `..`, a drive letter, a leading slash, a backslash, a reserved Windows name, or case-insensitive duplicates, and a size cap of 2 MB.
  - Also `make_manifest(files_txt, assets, …)` for CI: m1b.1's `build\files.txt` is the input, and the lead wires it into `release.yml` at integration.
- **`update/release_key.py`:** `PUBLIC_KEY: bytes | None = None` until the owner's key exists. With None, every install and roll back is refused (checks still run).
  - Verification reads only this constant. No setting, environment variable, file or API can change it.
  - Tests patch the module.

**Fetching and installing**
- **`update/github.py`:**
  - `httpx.Client(trust_env=False, follow_redirects=False)`, explicit timeouts, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`.
  - The repo is `techaust/shelf_sync`, a constant.
  - Outcomes: `ok`, `no_release`, `token_refused` (401), `rate_limited` (403 or 429 with remaining 0), `not_public` (404 with no token), `unreachable`. A 403 without remaining 0 is `token_refused` when a token is set.
  - The expiry notice is shown 14 days before expiry (SYS-06; tests at 10 and 15 days).
  - No URL with a query string, and no header value, is ever logged.
- **`update/download.py`:**
  - streams into `%LOCALAPPDATA%\ShelfSync\update\downloads\` (made on demand, emptied at start);
  - the manifest and signature first, verified, then the zip;
  - the zip is capped at its manifest size and at 300 MB, and hashed while it streams;
  - free space on the program drive must be at least 3× the zip.
- **`update/unpack.py`:**
  - [06 §4](../06-security.md)'s entry checks (zip-slip, reserved names, links and special entries refused, 500 MB per entry, 1 GB in total, a ratio cap);
  - the unpacked tree must equal `manifest.files` exactly: no extra, no missing, every hash;
  - into `versions\.incoming-<v>`, then renamed to `versions\<v>`. A leftover `.incoming-*` is removed at start without following links.
- **`update/layout.py`:** the install root. `SHELFSYNC_INSTALL_DIR` is honoured **only when this isn't the installed copy** (tests and rehearsals). It also handles the paths of the `current`, `current.next` and `current.old` junctions.

**Database backup (SYS-07)**
- **`db/backup.py`, `migrate_with_backup(connection, paths)`**, run at every start, not only after updates:
  - if migrations are pending **and** the database already has a version, take an online backup (`sqlite3` backup API) to `backups\pre-migration-<from>-to-<to>-<UTC>.db`, check it with `PRAGMA integrity_check`, and record it in `update\state.json` (path, from, to, time) **before** migrating;
  - if any migration fails, restore that backup before start-up exits with code 2.
  - **Restore:** check the backup's integrity; with no connection open (the instance lock is held), remove any stale `-wal` and `-shm`, then `os.replace` a verified copy over the database.
  - The backup stays at least until the next successful update. BAK-01 (M2) must never delete one that a kept version needs.

**State, service and switch**
- **`update/state.py`:**
  - `update\state.json` holds the installed and previous versions, the pending download (version, folder, verified time), the last check (time, outcome), the pre-migration backup, and the switch intent;
  - `update\result.json` holds the last switch's outcome, which the next start reads once and reports through `GET /api/updates`;
  - atomic writes; a file that can't be read is set aside and logged, never trusted.
- **`update/service.py`:**
  - the first check 60 s after start, then every 24 h, and on Check now (refused for 60 s after a check, 429);
  - a found update downloads and verifies in the background;
  - installing only on the owner's request;
  - one install or roll back at a time (409 otherwise);
  - a kept folder is re-checked against its stored manifest before any switch to it;
  - the development service (the default in `create_app`) reports `development: true` and refuses check, install and roll back with 409. It makes no network call, so the suite's no-outbound rule holds.
- **`update/switch.py`** (`python -m shelfsync.update.switch --format 1 --mode install|rollback --from <v> --to <v> --install-root … --data-dir …`), started detached from `versions\<from>\pythonw.exe` (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB`, V43). In order:
  1. The service starts the switcher, then calls `app.state.request_quit()`. If that is missing (the developer entry) or returns False, it ends the switcher and answers 409.
  2. The switcher waits up to 70 s for the old PID to end (the 45 s and 10 s safety exit, plus a margin). If the old copy is still running, it changes nothing, writes the result, and starts nothing.
  3. It takes `default_instance_lock()`, so no other copy can start mid-switch.
  4. It creates a `current.next` junction to the target, renames `current` to `current.old` and `current.next` to `current`, then removes the `current.old` link. At every start, a missing `current` is repaired from `current.next` or `current.old` (V39).
  5. It updates the uninstall key's `DisplayVersion`.
  6. It releases the lock, starts `current\pythonw.exe -m shelfsync.launcher --background`, and checks health within 60 s:
     - `runtime.json`'s PID is the child's;
     - the V33 owner check says the listener is the child, the same user, with an image under `versions\<to>` (V44 decides whether the image path is reported through the junction or its target; the check takes both images explicitly);
     - `GET /api/health` returns `version == <to>`;
     - it is still healthy 5 s later.

     It never sends the install token.
  7. **On success:** it writes the result, runs one plain launcher (a signed-in tab, decision 7), and prunes to the current and previous versions and their manifests, never following links.
  8. **On failure** (no answer, wrong version, exit 2, an untrusted listener, a crash): it ends its own child, restores the pre-migration backup if the schema moved, re-points `current` to `<from>`, starts the old version and checks its health the same way, and writes the result. If the old version also fails, it leaves `current` on `<from>`, writes the result, and stops.
  9. **Roll back app** is the same with `--mode rollback`. If the database changed, the API needs `{"confirm_data_loss": true}` and a recorded backup. Without the backup it's refused (409).
- **`platform/junction.py`, `platform/process.py` and `platform/uninstall_entry.py`:** real Windows adapters and fakes. `uninstall_entry` writes only `DisplayVersion`, and tests use a throwaway key.

**API**
- **`api/updates.py`:**
  - `GET /api/updates` returns: installed, previous, whether roll back is possible, whether the database changed and the backup's time, development, the last check, what's available (version, ready), the token (set, expires_at, notice), and the last result;
  - `POST /api/updates/check` (202 or 429), `POST /api/updates/install` (202 or 409), `POST /api/updates/rollback` (202, 409 or 422).
- **`api/secrets.py`:** `PUT /api/secrets/github-token` (204 or 422) and `DELETE` (204); `GET /api/secrets/github-token` says only whether it's set (decision 8).
- Both sit behind the existing deny-by-default guard (a session, plus Origin and `X-ShelfSync: 1` for writes), are added to the route-walk test, and use typed Pydantic models. The OpenAPI types are regenerated (`npm run schema:check` must pass; m1b.4 uses them).

**Release tools (run by the owner outside Claude)**
- **`tools/release/keygen.py`:** writes the encrypted PKCS#8 PEM to a path the owner gives, never inside the repo. It asks for the passphrase twice with `getpass` (at least 16 characters), prints the public key as 64 hex characters for `release_key.py` (public, safe to paste), and prints the encryption algorithm it used.
- **`tools/release/sign.py`:** reads an unsigned `manifest.json`, shows the version, tag, `source_commit`, `built_at` and the asset hashes, asks y/N, asks for the passphrase with `getpass`, and writes `manifest.json.sig`. It refuses to overwrite a signature.
- **`tools/release/verify_setup.py`:** verifies the signature with the public key in the local checkout's `release_key.py` (never one fetched from GitHub), then compares the SHA-256 of a downloaded `Setup.exe` with the manifest's (06 §6).
- None of them logs, stores or echoes a passphrase or private key.

**Packages:** add `cryptography==50.0.2` (with `cffi` 2.1.1 and `pycparser` 3.11, approved) to the run-time dependencies, re-lock with `UV_PYTHON_DOWNLOADS=never`, and check that pip-audit is clean. Nothing else.

**Strings:** every owner-facing message, with the API outcome codes, is listed in the builder report for 13. This includes "can't verify updates in this build", each check outcome, "<v> didn't start, so <old> is back", and the new Updates empty state (the token is optional). m1b.4 shows them.

### Shared files (m1b.2 §0, amended by decision 6)
- `server.py`: only the two places in decision 6.
- `api/app.py`: own `include_router` lines, the `updates=` keyword argument and the lifespan.
- `tray/launcher.py`: read only. `request_quit` comes from m1b.1; until it's merged, test with a fake app state.
- The lock: call `default_instance_lock()`.
- `platform/secrets.py`: m1b.1 adds the list of ShelfSync's entries for "Remove my data". m1b.2 doesn't edit that file; it declares the name `GITHUB_TOKEN_ENTRY = "github-token"` in `api/secrets.py`, and the lead adds it to the list at integration.
- Don't touch `packaging/`, `release.yml`, `paths.ui_dir`, `platform/autostart.py` or `platform/notify.py`.

### Tests (draft list kept; additions in bold)
- **Signature:** unsigned, wrong key, tampered bytes, any single-bit flip (hypothesis), a valid signature over bad content, no key in the build, no setting can change the key, **a signature that isn't 64 bytes, and a signature checked before parsing (a malformed JSON with a bad signature reports the signature)**.
- **Manifest:** duplicate keys, bad paths, case duplicates, **unknown fields, a downgrade, the same version, and a tag mismatch**.
- **Download:** hash, size, cap, the host allowlist, no token sent to the asset host, nothing secret in the logs, **200 and 302 both handled, more than 3 redirects refused, and a free-space failure**.
- **Unpack:** zip-slip, an extra file, a missing file, a wrong hash, **a leftover `.incoming-*` removed without following a planted junction**.
- **Token outcomes** and the 10-day and 15-day notice; **a missing header gives no notice**.
- **SYS-07:** a backup only when it's needed, a restore after a failed second migration, a fixture of the previous release's schema, **and a restore that leaves no stale `-wal`**.
- **Switch:** the happy path; each health-check failure; roll back with and without a migration; a missing backup; an old copy that won't quit; a fault after each step (including between the two renames, repaired at the next start); a tampered previous folder; the development copy 409; a second install 409; **quit refused, 409, and the switcher ended**; no read of the install token.
- **API guard cases**, and **the token never in any response**.
- **Windows checks (`-m windows`):** a real junction and the rename sequence, a detached child surviving its parent (V43), the image path through a junction (V44), `DisplayVersion` on a throwaway key, and a real Credential Manager round trip for `github-token` under a throwaway service.

### Done means
- **The CI checks pass.** Coverage is at least 90 % on `update/` and on `db/backup.py`: the builder adds both to the coverage loop in `checks.yml`, which is the only change to that file.
- **`-m windows` passes inside Claude**, then outside it (the owner, at integration).
- **A local rehearsal with throwaway roots and keys**, run from the source tree with `SHELFSYNC_INSTALL_DIR` and `SHELFSYNC_DATA_DIR`. The builder makes fake version folders (copies of the source tree plus a manifest) and signs them with a throwaway key made in the test. The sequence:
  1. install 0.0.1;
  2. update to 0.0.2 (with one extra migration);
  3. roll back, with the backup restored;
  4. a tampered 0.0.3 is refused;
  5. a broken 0.0.4 (exits 2) is switched back.

  Report each command and its result.
- **The builder report** lists files, commands, results, the proposed 13 wording, what wasn't verified, and open questions.

### Out of scope (owner)
- NSIS, `packaging/` and `release.yml`: m1b.1. The lead wires `make_manifest` into `release.yml` at integration.
- The Settings App API: m1b.3.
- Screens: m1b.4.
- BAK-01 daily backups: M2.
- M2's secrets.
- Delta updates.
- Automatic install without asking.
- Authenticode signing.
- Reproducible builds.
- The M5 upload quit guard.
- Toasts for updates: M5, decision 9.
- Making the real key, the releases and the signature uploads: the owner and the lead at integration (task 4).

## 2. Early check
_(analyst, once `manifest.py`, `versions.py`, `release_key.py`, `github.py`, `switch.py`, `db/backup.py` and the API routes are committed)_

### Early check (builder, Sonnet 5.5 high, 2026-10-27)
**Branch** `m1b.2-build` (cut from `6588748`). Commits: `2f8c5a5` (code), `d92ff62` (tests, OpenAPI types, coverage gate), and the one that adds this section. Nothing pushed.

**Built and committed with tests** (all under `backend/shelfsync/` unless said):
- `update/versions.py`, `release_key.py` (`PUBLIC_KEY = None`), `manifest.py` (verify then parse, canonical writer, `make_manifest`, a CI command `python -m shelfsync.update.manifest`), `layout.py`, `state.py`, `github.py`, `download.py`, `unpack.py`, `kept.py`, `service.py`, `switch.py`.
- `db/backup.py` (`migrate_with_backup`, `take_backup`, `restore_backup`, `check_backup`).
- `platform/junction.py`, `process.py`, `uninstall_entry.py` (real adapters and fakes).
- `api/updates.py`, `api/secrets.py`; `api/app.py` (the `updates=` keyword, the lifespan, the two routers); `server.py` (only the two places in decision 6).
- Shared files touched beyond the brief's list, each minimally: `secure/headers.py` (12 new `ErrorCode` literals: the 409/422/429 codes), `frontend/src/api/schema.d.ts` (regenerated) and `frontend/src/api/client.ts` (the new codes in `KNOWN_CODES`, because `tsc` fails without them), `tests/support.py` (an `updates=` argument), `tests/test_server.py` (one monkeypatch now names `migrate_with_backup`), `.github/workflows/checks.yml` (the coverage loop).

**Where to look hardest** (the places a mistake would be a security or data-loss bug):
1. `manifest.verify_signature` / `verify_and_parse`: 64 raw bytes, signature before parse, key read only from `release_key.PUBLIC_KEY` at the moment of use. Test file `tests/test_update_manifest.py` (single-bit flips by hypothesis, a validly signed manifest with bad content, no key, a key that isn't 32 bytes, other key channels offered in env, cwd and files).
2. `github.py`: redirects by hand, allowlist, the token only on hop 0 to `api.github.com`, `trust_env=False`. `//evil.example`, `host@evil` and `host.evil` forms are refused (tests).
3. `unpack.py` and `verify_tree`: the tree must equal `manifest.files` exactly; links refused. **Found and fixed during the tests:** my first zip entry check rejected every entry written by Python's `zipfile` (no Unix file-type bits recorded); it now looks at the type bits only when the zip records them.
4. `switch.py`: step order, the lock, `repoint` (3 renames/removals, undone in-process on a fault), `_go_back` (end child, restore backup, re-point, restart, health check) and the rule that **after the old copy has quit every exit starts a copy again**.
5. `db/backup.py`: the record is in `state.json` before the migration runs; a failed migration closes the connection, restores, then raises; `restore_backup` checks the copy, removes `-wal`/`-shm`, `os.replace`.

**Choices the brief left open (please confirm or change):**
- Switch CLI has two flags the brief didn't list: `--old-pid` (it must know whom to wait for) and `--restore-backup` (roll back after a database change).
- `GitHubClient` makes one extra request on a 404 (the repository itself) to tell `no_release` from `not_public`; GitHub answers 404 for both. 
- `logging.getLogger("httpx").setLevel(WARNING)` is set at import in `github.py`: httpx logs every request URL at INFO and a signed asset link carries its signature in the query string (a test caught it). m1b.3's "httpx warning filter" should keep or replace it.
- `junction.py` starts `cmd.exe` by its full path under `%SystemRoot%\System32` (not by PATH).
- After a roll back, `previous` is cleared and the version rolled back from is pruned; the next check can offer it again.
- `result.json` stays until the next switch overwrites it; `GET /api/updates` reads it every time (the new copy starts before the switcher writes it, so "read once at start" couldn't work). The app clears its own "busy" flag when a result newer than its install request appears and it is still running (the old copy never quit: `not_switched`).
- No pre-migration backup is ever deleted by this task.
- Failure handling restores the backup only in `install` mode; in `rollback` mode a failed start re-points to the newer version, which migrates again with a fresh backup.
- `files.txt`: `path<TAB>size<TAB>sha256` per line, as m1b.1 confirmed; no change needed on their side.

**Known limits / what I could not close:**
- **A switch killed between its two renames** leaves no `current`: the shortcuts and the Run value point at a path that doesn't exist, and nothing can start to repair it. The switch repairs it in-process on any fault it can catch, and every later switch (or a version started directly) repairs it, but a hard kill (power loss) in that microsecond window needs the installer to restore `current` from `versions\` (a note for m1b.1/integration). `current.next`/`.old` handling is tested with a fake; the real junction rename sequence is for the `-m windows` test.
- `verify_tree` is strict: any file the manifest doesn't list (a `__pycache__` written at run time) makes `install` and `rollback` refuse that folder. It depends on m1b.1's `compileall --invalidation-mode checked-hash` leaving a running version unchanged (V47).
- The first install by `Setup.exe` has no manifest on disk. The service fetches the running version's own signed manifest at the first successful check; if that fetch fails (rate limit, deleted old release), an update still works but "Roll back app" isn't offered.
- Not yet written: `tools/release/{keygen,sign,verify_setup}.py`, the `-m windows` tests, the local rehearsal, pip-audit, the 13 wording. They follow after your GO.
- Nothing here ran against the real junction, a detached child that outlives its parent (V43), or the registry; the unit tests use fakes (`tests/update_support.py`).

**Run so far** (this PC, Windows 11, Python 3.14.8): `uv run pytest` 1143 passed, 14 skipped, 32 deselected; coverage `update/` 95 %, `db/backup.py` 92 % (both over the 90 % gate; `platform/` adapters are lower on purpose, the Windows tests cover them); `ruff check`, `ruff format --check`, `mypy` (56 files) and `bandit -r backend` clean; `npm run schema:check`, `typecheck`, `lint` and `npm test` (261) pass.

### Analyst verdict on the early check: CHANGE (2026-10-27)
The signature guarantee holds. Eleven items to fix; all are done in commit `00d0b9b` (and `937ddfd` for what the rehearsal found afterwards). Each has a test in `tests/test_update_review_fixes.py` unless said.

| # | Required change | Fix | Test |
|---|---|---|---|
| 1 | The action lock leaked when `_switching` was True | `install` and `rollback` test `_switching` before `acquire` | install, install (409, lock free), `not_switched` result, `status()`, install again accepted |
| 2 | `_go_back` restored the database without the instance lock | `_go_back` ends the child, takes the lock (`LOCK_WAIT_SECONDS`), then restores and re-points; a busy lock changes nothing and finishes `failed` with `+lock_busy` | a lock lost after the first take: no `restore_backup` call, one spawn only |
| 3 | "Database changed" from schema numbers, not times | `database_schema()` reads the database's highest migration; roll back restores only when it is above the previous manifest's `schema_version`, and the recorded backup must have `from_schema` equal to that and `to_schema` equal to the database's. Same rule in `service.status`/`rollback` and the switcher (`_check_rollback_database`); a mismatch is `backup_mismatch`, a confirmation that disagrees with the database is `database_changed`; `_revert_state` also restores `backup` and `pending` | v1 to v2 (schema change), a failed v3 install after its migration, then roll back to v1 restores B1 and not B2; times ignored |
| 4 | Roll back safety | before the restore `take_snapshot` writes a checked `backups\pre-rollback-<from>-<UTC>.db` (a failure refuses the roll back); every failure path after the restore puts the snapshot back under the lock before `<from>` is restarted; `restore_backup` moves the database, `-wal` and `-shm` aside first and moves them back if the replace fails | snapshot taken and checked; snapshot failure refuses; failed re-point and a target that exits 2 both end `kept_old` with the snapshot's data; a snapshot that can't be put back is reported; the aside and put-back steps |
| 5 | A roll back deleted the folder the switcher runs from | `prune_versions` keeps `{to, from}` in both modes | `versions\<from>` and its manifest are still there |
| 6 | A stream failing part-way | `open_asset` turns `httpx.HTTPError` raised in the caller's body into `DownloadRefused("unreachable")`; `_ensure_own_manifest` also catches `httpx.HTTPError` | `update_failed` / `unreachable`, no traceback, no `.part` left; the own-manifest case survives |
| 7 | The 404 follow-up | `_classify_not_found` uses `_classify_status` for anything but 200 and 404 | 403 or 429 there is `rate_limited` |
| 8 | `start()` tidy-up | `Exception` caught around the tidy-up and `_reconcile_state`, the type only is logged, the schedule starts anyway | `start` survives a failing `clear_downloads` and a failing reconcile; the lifespan test (`tests/test_update_api.py`) already proves `create_app` calls `start` and `stop` |
| 9 | Registry only for an installed copy | `default_env(paths)` uses the real adapter only when `installed_root()` is not None, otherwise a no-op | both cases |
| 10 | One handle on the old PID | `Processes.watch(pid)` opens one SYNCHRONIZE handle (image by `QueryFullProcessImageNameW`); the switcher opens it first thing, checks the image is `versions\<from>\pythonw.exe` or `python.exe`, and waits on that handle (`old_process_mismatch` otherwise). **Rehearsal finding:** a copy already shutting down can't be asked its image, so an unreadable image gets 5 s of grace: if the process ends it is let go, if it stays up with no readable image it is refused | mismatch, either program accepted, handle released, already-gone, unreadable and staying up refused, unreadable and exiting accepted; the real handle on this PC |
| 11 | Missing `current` | `repoint` repairs on any `BaseException`; `main()` ends with a best-effort `repair_current`; the docstrings (junction, switch, service) now say repair happens in every switcher run and by Setup.exe, and the app's start only clears leftovers; `api/secrets.py` no longer claims `OWNED_SECRET_NAMES` is on this branch | `KeyboardInterrupt` at each of the four steps; `main()` repairs after a crash and survives a repair that fails |

Also done: `default_instance_lock` is called with `paths=` when the function accepts it (checked with `inspect.signature`), without when it doesn't (tested both ways); `github-token` equals m1b.1's `OWNED_SECRET_NAMES` entry.

**Stated exceptions (exits that start nothing after the old copy has quit):** `failed` with `+lock_busy` (the lock couldn't be taken to put things back) and `failed` with `+junction_error` (the link couldn't be put back). Both say so in `result.json`; the owner then starts ShelfSync from the shortcut or Setup.exe. Every other exit starts a copy again.

## 3. Builder report
_(builder: Sonnet 5.5 at high, 2026-10-27; branch `m1b.2-build` from `6588748`; nothing pushed)_

**Skills and tools.** Context7 loaded for `/pyca/cryptography`, httpx 0.28.1 (`/encode/httpx`), FastAPI lifespan (`/websites/fastapi_tiangolo`) and Python's `sqlite3` backup (`/websites/python_library`). The `security-review` skill was loaded once before the lead's correction (it reviewed the docs-only diff and gave no checklist) and not again; I applied its ideas by hand (validate every input, no secrets in logs or responses, no path traversal, no links followed, refuse by default). Not applicable: `aws-sdk-python-usage`, `aws-iam` (no S3 or IAM here), `frontend-design`, `dataviz` (no screens). The AWS MCP failed to connect at the start; nothing needed it.

**Commits** (conventional, cite SYS-06, SYS-07, SET-04): `2f8c5a5` code; `d92ff62` tests, OpenAPI types, coverage gate; `6b26074` early check; `00d0b9b` the analyst's 11 items; `98ecfd9` release tools, Windows tests; `937ddfd` rehearsal driver and the old-process grace; the last commit adds this report.

**Files changed**
- New, `backend/shelfsync/update/`: `versions.py`, `release_key.py`, `manifest.py`, `layout.py`, `state.py`, `github.py`, `download.py`, `unpack.py`, `kept.py`, `service.py`, `switch.py`.
- New elsewhere in the backend: `db/backup.py`, `platform/junction.py`, `platform/process.py`, `platform/uninstall_entry.py`, `api/updates.py`, `api/secrets.py`.
- Changed: `api/app.py` (the `updates=` keyword, the lifespan, the two routers), `server.py` (the two places in decision 6 only), `secure/headers.py` (12 new `ErrorCode` literals), `pyproject.toml` and `uv.lock` (`cryptography==50.0.2`, `cffi` 2.1.1, `pycparser` 3.11), `.github/workflows/checks.yml` (coverage loop), `frontend/src/api/schema.d.ts` (regenerated) and `frontend/src/api/client.ts` (the new codes in `KNOWN_CODES`, which `tsc` demands), `tests/support.py`, `tests/test_server.py` (one monkeypatch name).
- Tools: `tools/release/keygen.py`, `sign.py`, `verify_setup.py`, `keyfile.py`, `rehearse.py`.
- Tests: `tests/test_update_{manifest,github,unpack,state,service,api,switch,review_fixes}.py`, `test_db_backup.py`, `test_db_backup_more.py`, `test_platform_updater.py`, `test_release_tools.py`, `test_updater_windows.py`, helpers in `tests/update_support.py`.
- Not touched: `packaging/`, `release.yml`, `paths.py`, `tray/launcher.py`, `platform/{autostart,notify,secrets}.py`.

**Results** (this PC, Windows 11, Python 3.14.8, inside the Claude app)
- `uv run pytest`: 1203 passed, 14 skipped, 42 deselected. Coverage: `update/` 95 %, `db/backup.py` 97 %, `secure/` 100 % (all over the 90 % gate).
- `uv run pytest -m windows --no-cov`: 41 passed, 1 skipped (the V31 Defender check, owner present). This includes the new `tests/test_updater_windows.py`: a real junction and the rename sequence, a missing `current` repaired, a detached child that outlives the process that started it (V43), the image path through a junction (V44), the real health probe against a stub, `DisplayVersion` on a throwaway registry key, and the `github-token` round trip through a throwaway Credential Manager service.
- `ruff check`, `ruff format --check`, `mypy` (56 files), `bandit -r backend` (no issues), `pip-audit` ("No known vulnerabilities found"), `npm run schema:check`, `typecheck`, `lint` and `npm test` (261): all pass.
- **The local rehearsal, 27 of 27 checks** (`PYTHONPATH=backend uv run python tools/release/rehearse.py --base <m1b.1's build\ShelfSync-0.1.0> --work C:\Users\r4rup\AppData\Local\Temp\sr1`, through `tools/heavy.sh --log rehearsal`; the work folder is removed at the end). It uses m1b.1's embedded build as a read-only base, copied for each version, with this branch's code overlaid, real embedded `pythonw.exe` processes, a real junction, a throwaway Ed25519 key made in memory and a throwaway Credential Manager service, and never contacts GitHub (the first check is pushed out in the copies):
  1. **Install 0.0.1:** starts, answers `/api/health` as 0.0.1, database at schema 1, `GET /api/updates` says installed 0.0.1, a key in the build.
  2. **Update to 0.0.2** (one extra migration): `POST /api/updates/install` 202; the result is `updated`; a new process answers as 0.0.2; `current` points at 0.0.2; the database is at schema 2; `pre-migration-0001-to-0002-*.db` was taken first; the picture reports previous 0.0.1, roll back possible, database changed, backup available.
  3. **Roll back:** without confirmation 422 `confirm_required`; confirmed, 202; `rolled_back`; 0.0.1 answers again in a new process; the database is back at schema 1 (the backup restored); a `pre-rollback-0.0.2-*.db` snapshot exists; both version folders are still there.
  4. **Tampered 0.0.3 refused:** signed by another key: 409 `manifest_invalid`; correctly signed but one file changed afterwards: 409 `files_changed`; the running process and `current` are unchanged.
  5. **Broken 0.0.4** (its second migration fails and the app exits 2): `kept_old` with `migration_failed`; 0.0.1 answers again; `current` is back on 0.0.1; the database is unchanged (schema 1, no half-done table).

  Findings from the rehearsal: (a) m1b.1's built folder cannot start its tray: `tray/icons.py` looks for the icons at `<versions>\brand\assets\tray` and the build ships none (`FileNotFoundError`); the rehearsal copies carry them inside the version folder. **For m1b.1 or the lead.** (b) The switcher's old-process check failed on a copy already shutting down: fixed (item 10). (c) A switch ends with one plain launcher, a second launch, which opens a signed-in browser tab: the rehearsal copies patch the shell so no tab opens. (d) The base build was made before `cryptography` joined the lock, so the rehearsal copies add `cryptography`, `cffi` and `pycparser` from this checkout's environment; a normal build from the new lock includes them. (e) V47 held in this run: roll back re-verified a version folder that had run, and every file still matched its manifest, because the rehearsal compiled with `--invalidation-mode checked-hash` as m1b.1 does. (f) The tampered-0.0.3 step is the install-time refusal; the download-time refusals (bad signature, hash mismatch, replayed old manifest) are covered by the unit tests with a fake GitHub, since the app can only talk to GitHub's three hosts.

**What Windows reported (04-A rows):** V43, a detached child survived the exit of its parent (inside the Claude app, whose job object may differ from a normal session: the owner repeats it outside). V44, Windows reports the image of a program started through `current\python.exe` as the target folder (`versions\<v>\python.exe`), not through the junction; the health check accepts either. V39, `mklink /J` needs no admin and the rename sequence works; a `current` left missing is repaired.

**Virtualization (V36, V42).** Everything here ran inside the Claude app, whose processes see a private copy of new `%LOCALAPPDATA%` and `%APPDATA%` folders and may see a private HKCU. The Windows tests and the rehearsal use throwaway folders, a throwaway registry key and a throwaway Credential Manager service, so the results show that the code works, not what the real `%LOCALAPPDATA%`, Run key, uninstall key or Credential Manager look like to Windows. Those need the owner, outside the Claude app: `pytest -m windows`, a `reg query` of the uninstall key after an update, and the rehearsal or a real update on the real install.

**Choices and deviations** (the early-check list above, plus): the two extra switch flags `--old-pid` and `--restore-backup`; one extra GitHub request after a 404; `httpx` logging turned down at import in `github.py` (m1b.3's filter should keep it); `cmd.exe` by full path; `result.json` stays until the next switch; a roll back leaves the version rolled back from on disk (the switcher runs from it) and clears `previous`; no backup is ever deleted by this task (BAK-01 must keep the one `state.json` names and the `pre-rollback-*` snapshots); `files.txt` is `path<TAB>size<TAB>sha256`, as m1b.1 confirmed; `python -m shelfsync.update.manifest --version … --source-commit … --built-at … --files-txt … --setup … --zip … --out …` writes the unsigned manifest for `release.yml`; the release tools run as `PYTHONPATH=backend uv run python tools/release/<tool>.py` (they import this package's manifest code and read the key from the local `release_key.py`).

**For the integration (lead)**
- Merge `server.py` and `api/app.py` with m1b.1's: `tools/release/rehearse.py` (`build_version`) shows exactly how the two edits sit on top of m1b.1's versions, and that the combination starts and updates.
- `GITHUB_TOKEN_ENTRY = "github-token"` equals `OWNED_SECRET_NAMES`'s entry; `default_instance_lock(paths)` is handled both ways.
- Setup.exe should restore `current` from `versions\` if it is missing (the only repair for a hard kill between the two renames).
- The tray icons and the build's lock (`cryptography`) as above.
- 06 §10 residual risks to add (from the brief): freeze, local malware, the owner signs what CI built. 04-A: V26 (the expiry header's form, to verify with the owner's real token), V39, V43, V44, V46 (the algorithm `keygen.py` wrote is printed at run time and read from the file, and a test proves `sign.py` loads it), V47.
- `PUBLIC_KEY` is `None` until the owner's key exists; with None the app checks and refuses to install (`key_available: false` in the API).

**Not verified**
- Anything outside the Claude app (V36, V42, V43 for real; Start with Windows; the real uninstall key, Run key and Credential Manager).
- GitHub itself: the 302 to `release-assets.githubusercontent.com` and the 200/302 cases are tested with `httpx.MockTransport` and the documented behaviour (V45), not against GitHub; the expiry header's form (V26) is unknown, so `parse_expiry` accepts the forms I know and gives no notice for any other.
- A real signed release, `Setup.exe` through SmartScreen or Defender, an NSIS install of this code, the clean-account test.
- `keygen.py` and `sign.py` with the owner's real key and a real `getpass` prompt (the tests replace the prompts); `verify_setup.py` against a real downloaded `Setup.exe`.
- Two switchers at once, a power cut between the two renames, a real network failure part-way through a 300 MB download.
- The 70 s wait and 60 s health window use a fake clock in the tests; the rehearsal ran them in real time, but only on healthy and fast-failing paths.

**Open questions for the lead or owner**
1. `verify_tree` is strict (any file the manifest doesn't list refuses install and roll back). Fine with `checked-hash` pycs (V47 held); say if a `__pycache__` tolerance is wanted.
2. After a roll back the newer version's folder stays until the next update prunes it. Say if it should be removed later by a cleanup run.
3. Should "update ready" ever toast (decision 9 says M5)?

**Proposed owner-facing wording for docs/13** (m1b.4 shows it; the lead approves). `{v}`, `{old}`, `{new}` are versions; `{date}` is a local date and time with the zone name.

*Updates screen*
- Development copy: "This copy of ShelfSync runs from source, so updates are turned off."
- No key in the build: "This build can't verify updates, so it won't install any."
- Empty state (the token is optional): "ShelfSync checks for updates by itself. A GitHub token is optional: add one only if GitHub refuses the check or the project is private."
- Up to date: "ShelfSync {v} is up to date." Update found, not ready: "Version {v} is being downloaded and checked." Ready: "Version {v} is ready to install."
- Buttons and dialogs: "Check now", "Install {v} and restart", "Roll back app". Install confirmation: "ShelfSync will close and open again. This takes about a minute." Roll back, files only: "Roll back to {v}? ShelfSync will close and open again. Your data stays as it is." Roll back with a database change: "Roll back to {v}? The database goes back to how it was on {date}, so changes made since the update are lost. A copy of the current data is kept in the backups folder." Buttons "Roll back" and "Cancel".
- Check results (`last_check.outcome`): `ok` "Checked {date}."; `no_release` "No release has been published yet."; `token_refused` "GitHub refused the token. Check it, or remove it to check without one."; `rate_limited` "GitHub says there were too many checks. Try again later."; `not_public` "GitHub can't find the project. If it is private, add a read-only token."; `unreachable` "Couldn't reach GitHub. Check your connection."; `update_refused` "Version {v} was found but refused: it isn't signed by TecHaust or its files don't match. Nothing was installed."; `update_failed` "Version {v} couldn't be downloaded. It will be tried again at the next check." Detail `no_space`: "There isn't enough free space on the drive ShelfSync is installed on."
- Last switch (`last_result`): `updated` "Updated to {v}."; `rolled_back` "Rolled back to {v}."; `kept_old` "{new} didn't start, so {old} is back." with the reason `no_answer` "It didn't answer in time.", `wrong_version` "It reported the wrong version.", `untrusted_listener` "Something else was answering on ShelfSync's address.", `exited` "It stopped while starting.", `migration_failed` "Its database update failed and was undone."; `not_switched` "Nothing was changed." with `old_copy_still_running` "ShelfSync didn't close in time.", `old_process_mismatch` "The program that was running wasn't this version of ShelfSync.", `lock_busy` "Another copy of ShelfSync was starting.", `files_changed` "The files of {v} no longer match what was signed.", `manifest_missing` and `manifest_invalid` "The signature of {v} can't be checked.", `backup_failed` "A copy of the current data couldn't be made, so the roll back was refused.", `backup_missing` and `backup_mismatch` "The backup needed to roll back isn't there.", `database_changed` "The database changed since you confirmed. Try again."; `failed` "Neither version started. Open ShelfSync from the Start menu; the log has the reason."
- GitHub token: "Token saved." / "That isn't a fine-grained GitHub token (it starts with github_pat_)." / expiry notice "Your GitHub token expires on {date}. Make a new one before then." / "Token removed."

*API error codes* (`{"error": "<code>"}`): 409 `development_build` "Updates are turned off in this copy."; `busy` "An update is already under way."; `no_key` "This build can't verify updates."; `nothing_to_install` "There's no downloaded update to install."; `no_previous` "There's no earlier version to roll back to."; `no_backup` "The backup needed to roll back isn't there, so the roll back was refused."; `files_changed` "The files of that version changed on disk, so it was refused."; `manifest_invalid` and `manifest_missing` "That version's signature can't be checked, so it was refused."; `cannot_restart` "ShelfSync couldn't close itself to restart, so nothing was changed." 429 `too_soon` "A check ran a moment ago. Try again in a minute." 422 `confirm_required` (the roll back dialog above) and `invalid_request`.

## 4. Designer report
_(screens are m1b.4)_

## 5. Review
_(reviewer: Opus high, 2026-10-27)_ **APPROVED**: no critical or high findings. Seven follow-ups, fixed by the builder (Sonnet 5.5 high) in the commit that adds this table; each has a test in `tests/test_update_followups.py` unless said.

| # | Level | Finding | Fix | Test |
|---|---|---|---|---|
| 1 | Medium | The rehearsal's fake versions count as installed, so `default_env` used the real `HKCU\...\Uninstall\ShelfSync` key | `build_version` patches each copy's `UNINSTALL_KEY` to a throwaway `Software\ShelfSyncRehearsal-<id>\Uninstall`; the driver creates that key first, checks `DisplayVersion` after the update (0.0.2), the roll back (0.0.1) and the failed 0.0.4 (back to 0.0.1), and deletes the key (children first) in its `finally`. I did not take the key from the plan: a registry path on the switcher's command line would be one more input to validate for no gain, because only an installed copy writes at all. See the answers below | the rehearsal (30 of 30 checks); `test_display_version_is_written_to_a_throwaway_key_and_never_created` (Windows) |
| 2 | Medium | Early `not_switched` exits left nothing running after the old copy quit | `run()` now waits for the old copy first (bounded), then takes the lock, then starts what `current` names (`_restart_old`, touched False) for `junction_error`, a bad target and `old_process_mismatch`. A readable wrong image is not waited for on the handle (the lock waits up to 70 s instead); an unreadable image is waited for on the handle for the full 70 s and the lock decides: held means a copy is running (`old_copy_still_running`, nothing to start), free means the old copy is gone (restart, `old_process_mismatch`). The lock wait after a refused target is the normal one, no longer 0 s. The docstring lists exactly the exits that start nothing | `tests/test_update_review_fixes.py` and `test_update_switch.py`: wrong image with the lock free (restart) and held (`lock_busy`, nothing); unreadable image up with the lock held and free, and ending while waited for; a refused target with the lock busy for a moment; a junction error on the first repair |
| 3 | Medium | A roll back pruned a pending download's folder and manifest but kept `pending` | the pending version joins the keep set in rollback mode; `_reconcile_state` drops a `pending` whose folder, manifest or signature is missing | a roll back keeps `0.0.3` and still offers it; an install still prunes to two; a pending update with each of the three missing is dropped at start |
| 4 | Low | `sign.py` read the manifest twice | `main` reads the bytes once and passes them to `describe` and `sign` | the file is swapped while the y/N prompt is open: the signature is over the bytes that were shown |
| 5 | Low | A `last_check` with an unknown outcome could make `GET /api/updates` fail | `state_from_json` drops a `last_check` whose outcome is not in `CHECK_OUTCOMES` (or malformed); the rest of the file is trusted as before | six bad outcomes dropped without setting the file aside; every known outcome survives; `GET /api/updates` answers 200 |
| 6 | Low | An installed copy was recognised by `...\versions\<anything>\` alone | `installed_root` also requires the folder name to equal `__version__`. **No marker file**, so m1b.1 has nothing to write; `build.py` already names the folder for the version | a copy in `versions\9.9.9` is not installed (`SHELFSYNC_INSTALL_DIR` is honoured, otherwise updates are off); the right name is |
| 7 | Low | The rehearsal pushed the first check out by `1e9` s, above `threading.TIMEOUT_MAX` | `3.0e6` | the rehearsal |

Also: `ruff check`, `ruff format --check` and `mypy` were run explicitly on `tools/release/*.py` (ruff excludes `tools/`; the configuration is unchanged). Findings fixed: long lines, unused `noqa` markers, `try/except/pass` (now `contextlib.suppress`), an untyped result in `rehearse.py`. Run as `uv run ruff check tools/release/<each>.py` and, in PowerShell, `$env:MYPYPATH="backend;tools\release"; uv run mypy --explicit-package-bases tools/release/<each>.py`.

**Answers to the reviewer's questions on item 1**
- *Could the earlier 27/27 run have written the real key?* The switcher of an "installed" copy used `RegistryUninstallEntry` on the real path, which opens the key with `KEY_SET_VALUE` and writes `DisplayVersion` only if the key already exists. So a write was possible in the runs after the first switch succeeded (about 15:35 to 16:05 on 2026-10-27, six runs), but only if the key existed in the registry view those processes had. From inside the Claude app `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\ShelfSync` does not exist (checked with `reg query` before and after this run), so nothing was written in that view. Whether the real, unvirtualized hive has the key (an owner's earlier install) and whether the Claude package's HKCU writes reach it is exactly V42: not knowable from here. If the owner has a real ShelfSync install, `reg query` of that key outside Claude shows `DisplayVersion`; a value of 0.0.1, 0.0.2 or 0.0.4 that doesn't match the installed version would mean a rehearsal reached it.
- *Does `RegistryUninstallEntry` create the key when it is missing?* No. It calls `winreg.OpenKey(HKEY_CURRENT_USER, path, 0, KEY_SET_VALUE)` and returns False on `OSError`; it never calls `CreateKey`. The Windows test proves it: on a throwaway path it returns False and the key still does not exist; after the test creates the key it updates only `DisplayVersion` and leaves `DisplayName` alone.

**Re-check round 2: APPROVED** (2026-10-27). A last small pass by the builder, each with a test in `tests/test_update_round2.py`:

| # | Change | Test |
|---|---|---|
| 1 | The image matched but the old copy is still up after 70 s and the lock is free: the reason is `old_copy_hung` (an image that couldn't be read still gives `old_process_mismatch`); one restart, no switch | image matches, never ends, lock free: `not_switched` / `old_copy_hung`, no link call, one restart and the tab |
| 2 | With nothing touched, a `current` that is a real folder, points outside `versions` or is gone: `failed` with `+junction_error`, nothing spawned, lock released | both cases |
| 3 | The child exits as a second launch (the owner's shortcut started a copy in the gap) and `runtime.json` names a healthy, trusted copy of the expected version (the same probe and images): that copy counts as the success, and the switcher never ends it, even if it fails later. An exit 2 is never counted | success with nothing ended; an unhealthy other copy is a failure; exit 2 stays a failure; an adopted copy that fails later is not terminated |
| 4 | `CHECK_OUTCOMES` and the API's `CheckOutcome` can't drift | `set(CHECK_OUTCOMES) == set(get_args(CheckOutcome))` |
| 5 | The unreachable `watch is None` branch of `_wait_for_old_copy` is gone (the method takes a handle) | the existing switch tests |
| 6 | `verify_setup.py`'s docstring re-wrapped | ruff and mypy on `tools/release/*.py` |

**Run after round 2** (port 47615 free before and after; no `pythonw.exe`, rehearsal folder or throwaway entries left): `uv run pytest` 1230 passed, 14 skipped, 42 deselected (coverage `update/` 95 %, `db/backup.py` 97 %, `secure/` 100 %); `uv run pytest -m windows --no-cov` 41 passed, 1 skipped; `ruff check`, `ruff format --check`, `mypy` (56 files) and `bandit` clean, and ruff and mypy clean on `tools/release/*.py`; `pip-audit` no known vulnerabilities; `npm run schema:check`, `typecheck`, `lint` and `npm test` (261) pass; the rehearsal 30 of 30 against m1b.1's current build.

**Run after the fixes** (this PC, Windows 11, Python 3.14.8; port 47615 was free before and after, no `pythonw.exe` left, the work folder and the throwaway Credential Manager and registry entries removed)
- `uv run pytest`: 1222 passed, 14 skipped, 42 deselected; coverage `update/` 95 %, `db/backup.py` 97 %, `secure/` 100 %.
- `uv run pytest -m windows --no-cov`: 41 passed, 1 skipped (V31).
- `ruff check`, `ruff format --check`, `mypy` (56 files), `bandit -r backend` (no issues), `pip-audit` (no known vulnerabilities), `npm run schema:check`, `typecheck`, `lint`, `npm test` (261).
- The rehearsal: **30 of 30 checks** (the 27 plus three `DisplayVersion` checks on the throwaway key), against m1b.1's current build as the base. That build ships the tray icons now (`paths.tray_icon_dir()`), so the rehearsal's icon workaround is gone and finding (a) of §3 is closed. The install request hashes the whole version folder before it answers 202, which took more than 10 s on this busy PC: m1b.4 should expect a slow "Install" call (the rehearsal client waits 120 s).

## 6. Integration notes
_(lead)_

Suggestions from the builder (for the lead; none blocks the PR):
- **m1b.4, a "preparing" state for Install.** `POST /api/updates/install` hashes the whole version folder (about 2,000 files, 70 MB) before it answers 202: more than 10 s on a busy PC. The screen should show a busy "preparing" state while the request runs, and `check_now` should be refused (or its button disabled) meanwhile. The call stays synchronous for now by decision; if it is ever made asynchronous, `status()` needs a `preparing` flag and the 202 comes first.
- **Two "installed copy" tests to settle at integration.** `platform/autostart.is_installed_copy` (m1b.1) says a copy is installed when its path, not resolved, is inside `%LOCALAPPDATA%\Programs\ShelfSync\current\`. `update/layout.installed_root` (m1b.2) says it is installed when its resolved path is `<root>\versions\<v>\...` and `<v>` equals `__version__`, for any root (the rehearsal's roots included). They answer differently for a copy started from `versions\<v>\` directly (a switcher, a rehearsal) and for a copy under another root. Decide whether one function should serve both: the update layout is the more precise for the updater, while the Run key needs the path that never changes.
- The release tools and the rehearsal run as `PYTHONPATH=backend uv run python tools/release/<tool>.py`. `tools/` is excluded from the ruff and mypy configuration, so each file is checked by naming it (commands in section 5).


_(lead, 2026-10-27, integration)_
- **How it was joined:** m1b.1 was squash-merged as #15 (`075a0f8`). This branch's 10 commits were applied as one change on top of it (`git merge --squash` onto `origin/main`), because each commit would have met the same doc conflicts and the PR is squash-merged anyway. The pre-integration branch is kept locally as `m1b.2-prerebase`.
- **Conflicts resolved:**
  - `server.py`: one `create_app(port, install_token, ui_dir=ui, updates=build_update_service(paths, secrets))`, plus `migrate_with_backup`.
  - `api/app.py`: the imports.
  - 04-A: V40, V47 and V49 from main; V45 and V46 from this branch.
  - 11: rows from both sides.
  - `runs/m1b.1-packaging.md`: main's.
- **Lock shim removed:** with m1b.1 in, `switch._make_lock` always calls `default_instance_lock(paths=paths)`. The no-argument fallback and its `type: ignore` are gone, and the test is updated.
- **`release.yml`:**
  - The manifest placeholder is now a real step. The built folder's own `python.exe -I -B -m shelfsync.update.manifest` writes `build/manifest.json` from `files.txt`, the Setup and the zip.
  - That file is uploaded with the build and attached to the draft release.
  - The draft note says the signature is added by the owner. Nothing is signed in CI.
- **First `release.yml` run** ([40556444583](https://github.com/techaust/shelf_sync/actions/runs/40556444583), on main after #15): it failed at "Build the folder". `build.py`'s signature check exited 1 with no message.
  - The likely cause, not proven: on `shell: pwsh` steps Windows PowerShell 5.1 inherits PowerShell 7's `PSModulePath`, so `Get-AuthenticodeSignature`'s module doesn't load. This PC has no PowerShell 7, so it couldn't be reproduced here.
  - The fix: the child starts without `PSModulePath`, and a failure now carries PowerShell's own error text. Tested by a fake run, and the real check still runs on this PC.
  - The next run decides.
- **The two "installed copy" tests are kept, for now:**
  - `autostart.is_installed_copy`, unresolved under `%LOCALAPPDATA%\Programs\ShelfSync\current\`, decides only whether the Run value is written.
  - `layout.installed_root`, resolved to `versions\<__version__>`, decides whether updates and the registry entry are live.
  - They differ for a custom `/D=` folder and for the switcher run from `versions\<from>\`. Both fail safe, by treating the copy as not installed.
  - Unify them in m1b.3 (11 row).
- **Checks on the joined code (this PC, inside Claude):**
  - port 47615 free;
  - ruff, format, mypy (58 files) and bandit clean;
  - pytest: 1,353 passed, 16 skipped;
  - coverage: `secure/` 100 %, `update/` 95 %, `db/backup.py` 97 %;
  - `-m windows`: 48 passed, 1 skipped;
  - pip-audit clean;
  - `npm run schema:check`, typecheck, lint and test (261) pass.
- **Not re-run after the join:** the rehearsal (30/30 was on m1b.1's build before the join) and the installer rehearsal.

## 7. Handover
_(lead, 2026-10-27, earlier)_ The analyst's M1b plan and updater draft were saved, the owner answered every question (§0), and the M1b package list was approved. m1b.0 (Python 3.14) is merged (#13).

_(lead, 2026-10-27, later)_ The final brief (§1) is written at Opus high on branch `feat/m1b.2-updater`, cut from the m1b.1 brief commit `b46d73c`. Once m1b.1 squash-merges, move this branch with `git rebase --onto main b46d73c`. The m1b.1 builder is running. Next:
1. The owner approves this brief.
2. The m1b.2 builder starts (Sonnet high, its own worktree), as the second of two agents.
3. The owner switches the lead back to medium.

_(lead, 2026-10-27, integration)_ m1b.2 is joined with main on local branch `m1b.2-integrate`, one squashed change. Next:
1. The owner's yes to push it and open its PR.
2. CI on the PR.
3. Squash-merge on green, with the owner's yes.
4. A second `release.yml` run on main, to check the signature fix and the manifest step.
5. Then m1b.3 (Settings App API) and m1b.4 (screens).
