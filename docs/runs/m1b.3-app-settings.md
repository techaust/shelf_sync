Status: open (brief written 2026-10-28; the owner's standing instruction of 2026-10-28 covers build, review and merge)
Tier: B ([12 §2](../12-models-and-usage.md)); `platform/` and the API middleware rows of 09 §3 add `security-review`
Usage: lead `claude-opus-5-5/high` wrote this brief (the effort was left at high overnight; see 10)

# M1b.3: Settings › App API, log pruning, one "installed copy" test

The M1b plan is in [runs/m1b.2-updater.md](m1b.2-updater.md) §0. m1b.1 (#15), m1b.2 (#16) and the release-script fix (#17) are merged.

## 1. Brief

### PRD IDs
- SET-06: port, theme, Start with Windows, notifications, log retention, "Reset access token".
- LOG-01: logs kept for N days.
- UI-SET App: the API only. The screen is m1b.4.

### Agent and skills
- **`builder`:** Sonnet 5.5 at medium, in its own worktree. It never pushes.
- **Before writing code:** Context7 for FastAPI and Pydantic.
- **The reviewer** runs `code-review` and `security-review` (the API middleware and `platform/` rows of 09 §3).

### What to build
1. **`api/app_settings.py`**:
   - `GET /api/settings/app` returns `{port, theme, start_with_windows, notifications, log_retention_days, installed}`.
   - `PUT /api/settings/app` takes the same fields (except `installed`), all required:
     - typed with Pydantic, unknown fields refused;
     - `port` 47615–47624;
     - `theme` one of system, light or dark;
     - `log_retention_days` 1–365.
   - It saves through `db/settings.py` (`set_setting`, one transaction) and returns what was saved, plus `restart_needed: bool` (true when the port changed).
   - What a save does at once:
     - **Start with Windows:** applies `apply_start_with_windows` now. An installed copy writes or removes the Run value. An `AutostartError` is reported as a 200 with `start_with_windows_applied: false`, never a 500.
     - **Log retention:** updates the running handler's `backupCount` and prunes at once (item 2).
     - **Port:** takes effect at the next start.
     - **Notifications:** saved only. SYS-05 is M5; the notifier doesn't read it yet, so don't wire it.
   - Behind the existing guard: a session, and for PUT also Origin and `X-ShelfSync: 1`. Add both routes to the route-walk test. Use `ErrorCode` literals for every 4xx.
   - The routes are added with `include_router` in `create_app`. Plumb what the router needs (a connection factory, the log handler, the Run-key adapter) through a keyword-only argument to `create_app`, like `updates=`. The default is a no-op service for tests.
2. **Logs pruned by age (LOG-01):** files older than the retention setting are deleted from `logs\` at start and after each rotation, whatever their count. TimedRotatingFileHandler's `backupCount` counts files, not days. Rules:
   - only `shelfsync.log.*` names the handler writes;
   - never follow a link (reuse `paths.remove_entry`);
   - never the current file;
   - errors are logged and skipped.
3. **One "installed copy" test:** `platform/autostart.is_installed_copy` and `update/layout.installed_root` disagree today ([11](../11-decisions.md), 2026-10-27).
   - Make `layout.installed_root()` the single source.
   - `is_installed_copy()` becomes `installed_root() is not None`, and the Run value's path stays `current\pythonw.exe`.
   - Keep both names, so callers don't change.
   - Tests must cover a copy started from `versions\<v>\`, from `current\`, from the source tree, and under `SHELFSYNC_INSTALL_DIR` (not installed).
4. **The `httpx` deprecation warning** from `starlette.testclient`: filter that one warning by message and module in `pyproject.toml`'s pytest `filterwarnings`. Don't hide any other warning.
5. **Strings:** list any new owner-facing string with its proposed 13 wording in the report.

### Done means
- **The CI checks pass:** ruff, format, mypy **and `mypy --platform linux`**, pytest, bandit, pip-audit.
- **The new tests** cover:
  - every field's limits;
  - unknown fields refused;
  - the guard cases;
  - a Start with Windows failure reported, not raised;
  - pruning by age (an old file pruned, a link not followed, the current file kept, a foreign name kept);
  - the installed-copy cases.
- `npm run schema:check` passes. Regenerate `frontend/src/api/schema.d.ts`, and add new error codes to `client.ts`'s `KNOWN_CODES` if any.
- `-m windows` passes.
- The builder report lists files, commands, results, what wasn't verified, and the 13 wording.

### Out of scope
- The screen: m1b.4.
- The notifier reading the notifications setting: M5.
- Changing the port live.
- Rules settings: M5.
- Stores, Storage and Backup settings: M2.

## 2. Early check
_(Tier B: none)_

## 3. Builder report
Builder: Sonnet 5.5, worktree branch `worktree-agent-a7fa3226c665c0518` (the worktree started on `main`; it was fast-forwarded to `62ec6e1`, the tip of `feat/m1b.3-app-settings`, because that branch is checked out in another worktree).

**Skills and tools:** Context7 (FastAPI and Pydantic): `StrictInt`/`StrictBool` refuse `true` and `"30"` for numbers, `ConfigDict(extra="forbid")` refuses unknown fields, `response_model` on a PUT. No skill was loaded through the Skill tool: the lead said not to load `security-review` or `code-review`, and no other skill in the row applies to this task (not stated otherwise in the brief).

**Files changed**
- `backend/shelfsync/api/app_settings.py` (new): `AppSettingsService`, `make_app_settings_router`, the models. `GET`/`PUT /api/settings/app`. Strict types; `port` 47615-47624; `theme` system/light/dark; `log_retention_days` 1-365; all required; unknown fields (`installed` included) refused as the fixed 422 `invalid_request`. A save is one `BEGIN IMMEDIATE` transaction through `set_setting`. Answers the five values + `restart_needed` (port differs from the stored one) + `start_with_windows_applied`.
- `backend/shelfsync/api/app.py`: keyword-only `app_settings=` on `create_app`, like `updates=`; the default is `AppSettingsService.development()` (settings in a shared in-memory SQLite, no log handler, a `FakeRunKey`, never installed).
- `backend/shelfsync/server.py`: start-up calls `set_log_retention` (was a bare `backupCount =`) and passes the real service (`connect(paths.database)`, the log handler).
- `backend/shelfsync/logs.py`: `prune_logs`, `set_log_retention`; `RedactingFileHandler.doRollover` prunes after a successful rollover. `configure_logging` deliberately doesn't prune (the retention is still the default there; pruning with 30 could delete files the owner's 365 keeps).
- `backend/shelfsync/platform/autostart.py`: `is_installed_copy()` is `installed_root() is not None`; `install_folder` and `INSTALL_SUBFOLDER` removed (no other user); `launcher_command()` with no executable names `<root>\current\pythonw.exe` for an installed copy.
- `pyproject.toml`: one `filterwarnings` entry (message + `StarletteDeprecationWarning` + module `fastapi|starlette.testclient`).
- Tests: `tests/test_app_settings.py` (new, 51 cases), `tests/test_log_prune.py` (new), `tests/test_autostart.py` (installed-copy tests rewritten: from `versions\<v>`, from `current` junction, source tree, other version folder, `SHELFSYNC_INSTALL_DIR`, Run command names `current`), `tests/test_guard.py` (route walk asserts both routes), `tests/support.py` (`make_harness(app_settings=)`), `tests/test_logs.py` and `tests/test_output_guards.py` (two existing rotation tests used fixed or 3-day-old dates and now meet the age pruning; they use dates relative to today / a retention of 10 days).
- `frontend/src/api/schema.d.ts`: regenerated. No new error codes (every refusal is `invalid_request`), so `client.ts` is unchanged.

**Decisions made (routine)**
- Age rule: a rotated file named for day D is kept while `today(UTC) - D <= N days` (N rotated files at most, equal to `backupCount`); the date is taken from the name, not the mtime.
- `start_with_windows_applied` is false only on `AutostartError`; for a copy that isn't installed ("skipped") it is true (nothing to apply).
- A real folder with a rotated name is skipped; a link with one is removed itself.

**Commands and results** (all with `UV_PYTHON_DOWNLOADS=never`)
- `uv run ruff check`: pass. `uv run ruff format --check`: 127 files formatted.
- `uv run mypy`: no issues, 59 files. `uv run mypy --platform linux`: no issues.
- `uv run bandit -r backend`: 0 issues (exit 0).
- pip-audit as in CLAUDE.md (`uv export` then `--require-hashes --disable-pip`): no known vulnerabilities.
- `bash tools/heavy.sh --log pytest-full2 uv run pytest`: 1421 passed, 16 skipped, 49 deselected, no warnings (the first full run had one failure, fixed above, and ResourceWarnings from the development service's open in-memory connection, fixed with `weakref.finalize`).
- `pytest -m windows --no-cov`: 48 passed, 1 skipped (the V31 Defender check, which needs the owner).
- `npm run schema` then `npm run schema:check`: current. `npm run typecheck`: pass. (`npm ci` was run in the worktree's `frontend/`.)

**Not verified**
- `-m windows` ran inside the Claude app, which the CLAUDE.md says doesn't count for the registry and Credential Manager; the owner's run in Windows PowerShell is the one that counts. The new code adds no Windows-only test.
- `PUT` with a real Run key on an installed copy was not tried (tests use `FakeRunKey`); no installer or release build was run (nothing in `packaging/` changed).
- Not run: frontend lint, `npm test`, `npm run build` (only the schema file changed).
- Concurrency: the PUT is a sync route (thread pool); two PUTs at once are serialized by `BEGIN IMMEDIATE`, but the Run key and handler updates after the commit aren't under that lock (last writer wins on each).
- The `PUT` of `start_with_windows` re-applies the Run value even if unchanged (idempotent: "unchanged" when it already matches).

**Proposed 13 wording** (no string is shown by the backend; these are for m1b.4's screen)
- Notice when `start_with_windows_applied` is false: "Your settings were saved, but Windows wouldn't let ShelfSync change its start-up entry. Start with Windows is unchanged."
- Notice when `restart_needed` is true: "The new port is used the next time ShelfSync starts."
- Hint for a development copy (`installed` false): "This copy isn't installed, so Start with Windows is saved but not applied."
- Field limits to show in the form: port 47615 to 47624; log retention 1 to 365 days.

## 5. Review
_(reviewer)_

## 6. Integration notes
_(lead)_

## 7. Handover
_(lead, 2026-10-28)_ Brief written; builder next.

**Overnight run (owner's instruction, 2026-10-28):** "complete everything till M2: build, review, fix, re-review; push and merge once satisfied; update CLAUDE.md and all the docs; then end the day." It is standing approval for pushes and merges of reviewed, CI-green PRs tonight. These limits still hold (CLAUDE.md hard rules):
- no writes to the live stores or the S3 bucket;
- no new package without the owner's yes;
- no Windows security settings;
- the M1b and M2 exit tests and milestone approvals stay the owner's.

State at the time of writing:
- `main` is at `1358dc0` (#15, #16, #17 merged).
- `release.yml` run [40575157342](https://github.com/techaust/shelf_sync/actions/runs/40575157342) on main is in progress: its first run after the one-script fix.
- This branch is `feat/m1b.3-app-settings`, with the brief at `b070f6e`.

Order:
1. The m1b.3 builder, then the reviewer, then fixes, then merge.
2. m1b.4: the screens, by the `designer` at Opus high, then the visual review, then merge.
3. M1b record: the exit-test steps for the owner.
4. M2: only the parts needing no new packages and no live system. Store settings use httpx against fakes. Credential Manager secrets. Backup export with scrypt and AES-GCM (cryptography is approved). BAK-01. The screens. S3 needs boto3 and moto, not approved, so it's left for the owner, and so is LocalWP.
5. `end-session`.

Before every push:
- `packaging/release-build.ps1` (when packaging or what the build ships changed);
- `uv run mypy --platform linux`.

Clean up afterwards: the merged worktrees `agent-a1e0d53eff589f5c5` and `agent-ac2f65217273a2b24` (branches `m1b.1-build`, `m1b.2-build`, `m1b.2-integrate`, `m1b.2-prerebase`), and `build/`.

For the owner: one `reg query` on the Uninstall\ShelfSync key outside Claude. The lead's effort was left at high (owner asleep).
