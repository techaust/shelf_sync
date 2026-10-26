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
_(builder)_

## 4. Review
_(reviewer reply, copied in by the lead)_

## 5. Integration notes
_(lead)_

## 6. Handover
_(lead, 2026-10-26)_ Brief written on `docs/m1a-plan-and-pins`, not yet pushed. Next: the owner's yes to push that branch and open a PR; merge on the owner's yes; then start the builder from `main`.
