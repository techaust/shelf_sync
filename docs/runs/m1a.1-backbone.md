Status: open
Tier: B
Usage: _(filled in by the lead from `node tools/model-audit.mjs` after each agent run)_

# M1a.1: Backbone

## 1. Brief
_(lead, Opus 5.5 medium, 2026-10-26)_

**Roadmap:** M1a, step 4 of the approved M1a plan ([08](../08-roadmap.md)). This task lays the Python base that M1a.2 (security), M1a.3 (screens) and M1a.4 (tray) build on.
**PRD IDs:** SET-06 (port part only), ERR-06, LOG-01 (without redaction), NFR-5, NFR-8 (storage side) ([03](../03-prd.md)).

**Who:** the `builder` (Sonnet 5.5, medium; Tier B, [12 §3](../12-models-and-usage.md)), in its own git worktree on the branch `feat/m1a.1-backbone`, cut from `main` once the docs PR (`docs/m1a-plan-and-pins`) has merged. Commit there; **never push**. The lead integrates.

**Writes only to:**
- `pyproject.toml`, `uv.lock`, `.python-version` (repo root)
- `backend/shelfsync/` (the packages named below)
- `tests/` (unit tests for this task)
- `.github/workflows/checks.yml`
- §3 of this file

The lead owns everything in `docs/` (except §3 here), `CLAUDE.md`, `CHANGELOG.md` and `.gitignore`: suggest changes in your report instead of editing them.

**Skills and tools** ([09 §3](../09-tooling.md)):
- Context7 for the current docs of **FastAPI, uvicorn, uv, pytest, pytest-cov, ruff, mypy, bandit and pip-audit** before writing code or config that uses them. Say in §3 which you looked up.
- Heavy commands only through `bash tools/heavy.sh --log m1a.1-<name> <command>`; read the log with grep, not in full.
- No browser is needed.

**Owner decisions that bind this task** ([11](../11-decisions.md)):
- **Packages:** only these, at exactly these versions ([04 §2.1](../04-architecture.md)). Nothing else may be installed. If you find one is missing, stop and report it.
  - run time: `fastapi==0.143.0`, `uvicorn==0.54.0`
  - dev (a uv dependency group): `httpx==0.28.1`, `pytest==9.1.1`, `pytest-cov==7.1.0`, `hypothesis==6.169.0`, `ruff==0.17.0`, `mypy==2.4.0`, `bandit==1.9.4`, `pip-audit==2.10.1`
  - pystray, Pillow and windows-toasts are **not** added here. M1a.4 adds them with their Windows markers (V29).
- **The 14-day cutoff covers what these pull in:** set uv's `exclude-newer = "2026-10-13T00:00:00Z"` in `pyproject.toml` (that is, releases on or before 2026-10-12). `uv.lock` is committed and holds hashes. Report the resolved versions of the main transitive packages (starlette, pydantic, pydantic-core, anyio, h11, click).
- **Python 3.12 only:** `requires-python = "==3.12.*"`. Use the Python 3.12.10 on this PC through uv.
- **No telemetry, no outbound calls** (NFR-5).
- **CI on Linux only** (GitHub Actions minutes; Windows only on release tags, later).
- **Actions pinned by commit SHA**, exactly the four in 04 §2.1, with the version in a comment.

**Work:**
1. **Project:** `pyproject.toml` for the `shelfsync` package, sourced from `backend/shelfsync/` (src-style layout: `backend/` is the import root). uv as the only tool. Ruff (lint and format) and mypy configured in `pyproject.toml`; mypy `strict = true` for the whole package for now.
2. **App factory** in `backend/shelfsync/api/app.py`: `create_app()` returns the FastAPI app. One route for now: `GET /api/health`, no session, returning exactly `{"app": "shelfsync", "version": <package version>}` (04 §5). Turn off the interactive docs routes (`/docs`, `/redoc`, `/openapi.json` served publicly). Keep the OpenAPI schema available in code (for openapi-typescript in M1a.3), just not as a route.
3. **Data folder** in `backend/shelfsync/paths.py`: `%LOCALAPPDATA%\ShelfSync\` with `logs\`, `tmp\`, `backups\` and `runtime.json` (04 §8). For tests and Linux CI, the env var `SHELFSYNC_DATA_DIR` overrides the root; nothing else does. At start-up, empty `tmp\` (crash leftovers, 06 §4).
4. **Database** in `backend/shelfsync/db/`:
   - the standard `sqlite3` module, no ORM; on every connection: WAL mode, `foreign_keys=ON`, a busy timeout (pick a value and say why)
   - a small migration runner: files `db/migrations/NNNN_name.sql`, applied in order inside a transaction each, recorded in `schema_migration (version, applied_at)`; already-applied versions are skipped; a failing migration rolls back and stops start-up with a clear error
   - **`0001_base.sql` creates only `schema_migration` and `setting (key, value_json)`** (04 §4). Every other table arrives with its milestone as a new numbered file.
   - setting defaults in code (not rows) for: `port` 47615, `theme` "system", `start_with_windows` true, `notifications` true, `log_retention_days` 30 ([11](../11-decisions.md) rows of 2026-10-25). Read and write helpers that store JSON.
5. **Port (SET-06, ERR-06)** in `backend/shelfsync/server.py`:
   - **bind to `127.0.0.1` only.** Try the `port` setting first, then each next port up to 47624. Bind the socket yourself and hand the open socket to uvicorn, so no other program can take the port between the check and the start (confirm the uvicorn API for this in Context7).
   - write the port in use and the PID to `runtime.json` (only those two fields, 04 §8)
   - notifications go through a small `Notifier` interface in `backend/shelfsync/platform/notify.py` with a **fake** that records messages; the real Windows toast adapter is M1a.4
   - when a fallback port is used, send ERR-06's first message with the port filled in, plus its second line; when all ten are taken, send the "all in use" message and exit with a non-zero code. The text is exactly [13 §3 and §6](../13-content.md) (ERR-06 rows). Keep the strings in one module so M1a.3 can share them.
   - `python -m shelfsync` starts the server this way (a development entry point; the launcher is M1a.4).
6. **Logs (LOG-01)** in `backend/shelfsync/logs.py`:
   - JSON lines to `logs\shelfsync.log`: `time` (UTC, ISO 8601 with `Z`), `level`, `job_id`, `step`, `message` (missing fields as `null`)
   - rotated daily at UTC midnight, keeping `log_retention_days` files
   - uvicorn's own loggers routed into the same file; **no access log of headers, cookies or query strings**
   - leave **one named place** where M1a.2 plugs in the redaction filter (a function that every record passes through, a no-op for now) and say where it is. The redaction itself and its test belong to M1a.2.
7. **Time (NFR-8)** in `backend/shelfsync/clock.py`: `utc_now()` and `to_iso(dt)` giving `YYYY-MM-DDTHH:MM:SS.ffffffZ` (or without microseconds; your call, say why) and refusing naive datetimes. Showing local time with the zone name is the UI's job (M1a.3).
8. **No outbound calls (NFR-5):** a pytest fixture, on for the whole suite, that makes any socket connection to a non-loopback address fail the test.
9. **CI** in `.github/workflows/checks.yml`, on pull requests and pushes to `main`:
   - `permissions: contents: read`; a concurrency group that cancels older runs of the same PR
   - **python** job (ubuntu-latest): `setup-uv` → `uv sync --locked` → `ruff check` → `ruff format --check` → `mypy` → `pytest` with coverage → `bandit -r backend` → `pip-audit` against the locked packages
   - **brand** job: `setup-node` (Node 24) → `npm ci` and `npm test` in `brand/` (the existing 221 tests), so the brand files are guarded too
   - no secrets used, no artifacts uploaded yet. Name the job steps plainly; the owner reads them on GitHub.
10. **Coverage:** report the total. The ≥ 90 % gate on `secure/`, `inspect/`, `match/` and `apply/` starts when those folders get code (M1a.2 for `secure/`); add the config hook for it now if it's simple, and say how.

**Done means** (all run through `tools/heavy.sh`, results pasted in §3):
- `uv sync --locked`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run pytest`, `uv run bandit -r backend`, `uv run pip-audit` all pass on this PC.
- Tests prove at least:
  - `GET /api/health` returns exactly the two fields, and `/docs`, `/redoc` and `/openapi.json` give 404
  - migrations: a fresh database gets `0001`; a second run applies nothing; a broken migration rolls back and leaves the version table unchanged
  - port: default free → 47615; 47615 held by a test socket → 47616 and the ERR-06 message in the fake notifier; all ten held → the "all in use" message and a non-zero exit; the socket is bound to `127.0.0.1`, never `0.0.0.0`
  - `runtime.json` holds only `port` and `pid`
  - a log line is valid JSON with the five fields and a `Z` time; the rotation keeps the set number of files
  - `clock` refuses naive datetimes
  - the no-outbound fixture fails a test that tries `example.com`
  - start-up empties `tmp\`
- `cd brand && npm test` still passes (221 tests) with the new `.gitattributes` line endings.
- The workflow file is valid YAML and uses only the four pinned actions. It can't run until the lead pushes, so say "not run on GitHub yet".

**Out of scope** (owned elsewhere):
- install token, ticket, session, Host/Origin/CSRF, CSP, log redaction: **M1a.2** (Tier A)
- the React app, tokens, fonts, Playwright and axe, the UI job in CI: **M1a.3**
- tray, launcher, single instance (SYS-03), start with Windows, the real toast adapter, Windows checks, pystray/Pillow/windows-toasts: **M1a.4**
- the settings screen (M1b), backups (BAK-01, M2), migration upgrade tests (M1b)

**Report in §3:** files changed, every command and its result, the resolved transitive versions, what Context7 told you that changed your approach, anything not verified, and open questions. Suggested lines for `CLAUDE.md` § Commands go there too.

## 2. Early check
_(Tier B: none.)_

## 3. Builder report
_(builder, Sonnet 5.5, 2026-10-26; branch `feat/m1a.1-backbone`)_

**Result:** everything in "Done means" passes except one: **`uv run pip-audit` fails** on dev-only packages (see "Needs the owner"). Every heavy command ran through `tools/heavy.sh` on this PC. The workflow has **not been run on GitHub yet**.

**Skills and tools:** Context7 for FastAPI, uvicorn, uv, pytest, pytest-cov, ruff, mypy, bandit and pip-audit. No other skill in 09 §3 fits this task (the AWS skills are for boto3 code, which comes later; no screens, so no browser or design skill).

**What Context7 changed:**
- uvicorn: `Server.serve(sockets=[sock])` takes an open, already-listening socket and skips its own binding, so the port is bound by us and never released. `Config(log_config=None)` leaves logging alone, so our handler on the root logger gets uvicorn's records.
- FastAPI: `docs_url=None, redoc_url=None, openapi_url=None` removes the routes; `app.openapi()` still builds the schema in code (tested).
- uv: a project can be `package = false` (virtual), which needs no build backend. A backend (hatchling) would be one more package outside the owner's list, so I used this. Consequence: `backend/` is on the path through `pytest pythonpath` and `mypy_path`, and `python -m shelfsync` needs `PYTHONPATH=backend` (see commands below).
- pip-audit: `--require-hashes --disable-pip -r <file>` audits a hashed requirements file with no resolution; `uv export` produces that file from `uv.lock`.
- pytest 9.1.1 accepts `[tool.pytest.ini_options]` (used). bandit needs no config. Coverage has no per-folder threshold (see "Decisions").

**Files changed** (all new): `pyproject.toml`, `uv.lock`, `.python-version` (3.12.10), `.github/workflows/checks.yml`; `backend/shelfsync/`: `__init__.py`, `__main__.py`, `clock.py`, `paths.py`, `messages.py`, `logs.py`, `server.py`, `api/app.py`, `db/{connection,migrate,settings}.py`, `db/migrations/0001_base.sql`, `platform/notify.py`; `tests/`: `conftest.py`, `test_api_health.py`, `test_clock.py`, `test_db.py`, `test_logs.py`, `test_no_outbound.py`, `test_paths.py`, `test_server.py`. Nothing outside the allowed list was touched (`.gitattributes` was already in place).

**Commands and results** (logs in `.logs/`, git-ignored):
| Command | Result |
|---|---|
| `uv sync` (m1a.1-sync), then `uv sync --locked` (m1a.1-sync-locked) | exit 0; 59 packages, lock holds hashes |
| `uv run ruff check` and `uv run ruff format --check` (whole repo) | pass; 26 files formatted |
| `uv run mypy` (m1a.1-mypy) | pass, strict, 16 source files |
| `uv run pytest` (m1a.1-pytest) | **44 passed**, coverage **97 %** total (branch on); 1 warning (below) |
| `uv run bandit -r backend` (m1a.1-bandit) | pass, 0 issues in 386 lines |
| `uv export --locked --no-emit-project ...` then `uv run pip-audit --require-hashes --disable-pip -r .logs/locked.txt` (m1a.1-pipaudit) | **FAIL, exit 1**: 7 known vulnerabilities in 2 packages: certifi 2026.7.22 (PYSEC-2026-4320, fix 2026.10.19) and filelock 4.1.1 (six CVEs, fix 4.2.1). Both are dev-only today (pulled in by pip-audit and httpx). The same audit with `--no-dev` (m1a.1-pipaudit-nodev) finds **nothing**. |
| `npm --prefix brand ci` then `npm --prefix brand test` | pass, **221 tests** (5 files) |
| `checks.yml` loaded with PyYAML | valid; jobs `python` and `brand`; uses only `actions/checkout`, `astral-sh/setup-uv`, `actions/setup-node` at the 04 §2.1 SHAs (upload-artifact not needed yet) |

**Resolved versions** (cutoff 2026-10-12): starlette 1.7.0, pydantic 2.14.1, pydantic-core 2.50.1, anyio 4.15.1, h11 0.16.0, click 8.5.0; also certifi 2026.7.22 and filelock 4.1.1 (the two flagged).

**Tests for "Done means"** (in `tests/`): health returns exactly the two fields and `/docs`, `/redoc`, `/openapi.json` give 404 (`test_api_health.py`); migrations: fresh, idempotent, broken one rolls back with the version table unchanged, plus trigger splitting, bad names, newer-database refusal (`test_db.py`); port: default 47615, 47615 held gives 47616 and the exact ERR-06 text, all ten held gives the "all in use" text and a non-zero exit, socket on `127.0.0.1`, `runtime.json` has only `port` and `pid`, start-up empties `tmp\`, and one test runs real uvicorn on a handed-over socket and calls `/api/health` (`test_server.py`); log line is JSON with the five fields and a `Z` time, rotation keeps the set count (`test_logs.py`); naive datetimes refused (`test_clock.py`); a connection to example.com fails the test (`test_no_outbound.py`).

**Decisions I took** (record in 11 if you agree):
- Busy timeout 5000 ms (a wait only happens while a backup or checkpoint runs; a real deadlock shows within seconds).
- Time format `YYYY-MM-DDTHH:MM:SS.ffffffZ`, always six digits: fixed width, so the text sorts like the time.
- ERR-06 is sent as **one** notification of two lines (first message, newline, second line).
- A port setting outside 47615-47624 gets no fallback (only that port is tried). The settings screen (M1b) should validate the port.
- Exit codes: 0 ok, 1 all ports in use, 2 migration failed (message on stderr).
- Access log is **off** (uvicorn's access line carries the query string); `proxy_headers` and the `Server` header are off.
- Redaction plugs in at **`shelfsync.logs.redact(text) -> str`** (`backend/shelfsync/logs.py`), called by `JsonFormatter.format` on every final message including tracebacks; a test proves the hook is called. M1a.2 replaces its body and adds its own test.
- On Windows the listener sets `SO_EXCLUSIVEADDRUSE`; on Linux `SO_REUSEADDR` (so a restart can rebind).
- Log retention is read once at start-up (a changed setting applies after a restart).
- Ruff: line length 120, rules E F W I B UP SIM RUF, `RUF001` ignored (the en dash in ERR-06 is the owner's wording), and `docs`, `tools`, `brand`, `.claude` excluded so a bare `ruff check` covers app code only (the research and doc scripts there would fail it).
- Coverage hook: `[tool.coverage]` measures `backend/shelfsync` with branches. coverage.py has no per-folder threshold, so CI has a step that runs `coverage report --include=<folders with code besides __init__.py> --fail-under=90`; it does nothing until `secure/`, `inspect/`, `match/` or `apply/` gets a `.py` file. That shell step is untested on GitHub.

**Needs the owner (stopped, not guessed):**
1. **pip-audit fails on the 14-day cutoff.** The fixed releases (certifi 2026.10.19, filelock 4.2.1) are newer than 2026-10-12. Options: (a) accept, and add `--ignore-vuln` for those seven IDs for the dev tools until the next pin refresh; (b) raise the cutoff or exempt certifi and filelock (uv has a per-package exclude-newer setting); (c) audit only run-time packages in CI (passes today). httpx becomes a run-time package in M2 and needs certifi then, so (c) alone won't hold.
2. **Starlette warns** "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead." (FastAPI's TestClient). httpx 0.28.1 is the owner's pin, so I installed nothing; harmless today. Flag for the next pin refresh.

**Not verified:** the workflow on GitHub (the coverage step script, `uv export` and pip-audit there, setup-uv's `version` input); anything on Linux (tests ran only on this Windows PC); `SO_EXCLUSIVEADDRUSE` against a program that holds the port with `SO_REUSEADDR`; `python -m shelfsync` was not started by hand (the tests start the real server instead).

**Suggested lines for `CLAUDE.md` § Commands** (repo root; heavy ones via `bash tools/heavy.sh --log <name> ...`):
- Install: `uv sync --locked`
- Python checks: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run pytest` (coverage is on by default), `uv run bandit -r backend`
- Audit: `uv export --locked --no-emit-project --format requirements-txt --output-file .logs/locked.txt` then `uv run pip-audit --require-hashes --disable-pip -r .logs/locked.txt`
- Dev server: PowerShell `$env:PYTHONPATH = "backend"` then `uv run python -m shelfsync` (data goes to `%LOCALAPPDATA%\ShelfSync`, or to `SHELFSYNC_DATA_DIR`)
- Brand, as CI runs it: `npm --prefix brand ci` and `npm --prefix brand test`
- `.gitignore` needs nothing new (`.venv/`, `.logs/` and the caches are already covered).

## 4. Review
_(reviewer, Opus 5.5 high, `code-review` + `security-review`, 2026-10-26)_ **APPROVE**: no critical or high findings; 3 medium, 9 low. Checks re-run by the reviewer: all pass, pip-audit clean after 00ed866. Not verified: anything on Linux or GitHub, `python -m shelfsync` by hand.

**Lead triage** (Tier B, at medium):
| # | Sev | Finding | Decision |
|---|---|---|---|
| 1 | M | Restart within ~2 min may fall back to 47616 (Windows TIME_WAIT with `SO_EXCLUSIVEADDRUSE`) | **Fix now:** retry the preferred port for ~3 s before falling back; Windows-only test |
| 2 | M | Start-up failures before logging is set up leave no log and no notification | **Fix now:** logging first; any start-up exception logged + notified + distinct exit code; close the connection if a PRAGMA fails |
| 3 | M | No CI timeouts; non-daemon test thread | **Fix now:** `timeout-minutes: 15`; `daemon=True` |
| 4 | L | Port setting not range-checked | **Fix now:** 1024–65535 |
| 5 | L | Unconditional `ROLLBACK` can hide the real cause | **Fix now** |
| 6 | L | Two statements on one line rejected | **Fix now:** split with `sqlite3.complete_statement` |
| 7 | L | "All in use" text drifts; default port defined twice; duplicate busy-timeout PRAGMA | **Fix now** |
| 8 | L | One bad `tmp\` entry stops start-up | **Fix now:** junction check; log and skip |
| 9 | L | Coverage gate combined; Node `"24"` | **Fix now:** per-folder gate; Node `24.19.0` |
| 10 | L | Logs kept by count, not age | **Follow-up M1b** (with the retention setting) |
| 11 | L | Output before logging skips `redact` | **Into the M1a.2 brief**; the bare `print` goes with #2 |
| 12 | L | Run file says pip-audit fails; `runtime.json` not removed; `held()` skips silently | **Fix now:** `held()` fails instead of skipping; §3 note by the lead in §5. `runtime.json`: **into the M1a.4 brief** (the launcher checks `/api/health` identity, never the PID) |

## 5. Integration notes
_(lead)_

## 6. Handover
_(lead, 2026-10-26)_ Brief written on `docs/m1a-plan-and-pins`, not yet pushed. Next: the owner's yes to push that branch and open a PR; merge on the owner's yes; then start the builder from `main`.
