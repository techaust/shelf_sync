Status: open
Tier: B ([12 §2](../12-models-and-usage.md): the runtime move touches every backend part, but no Tier A logic changes)
Usage: (lead fills from `node tools/model-audit.mjs`)

# M1b.0: Move to Python 3.14

## 1. Brief
_(lead, Opus 5.5 medium, 2026-10-27)_

**Roadmap:** M1b, the first task ([08](../08-roadmap.md); plan in [runs/m1b.2-updater.md](m1b.2-updater.md) §0). **Why:** 3.12.10 (April 2025) is 3.12's last release with Windows builds, so an embedded 3.12 could never take a security fix. The owner moved ShelfSync to **Python 3.14** ([11](../11-decisions.md) and the [ADR 0001](../adr/0001-python-fastapi-sqlite-react.md) amendment, 2026-10-27). **PRD:** NFR-7 (plain, maintainable parts); no behaviour changes.

**Facts already checked (lead, 2026-10-27):**
- Python 3.14.8 (python.org, 30 Sep 2026, the newest 3.14 at least 14 days old) is installed on this PC by the owner at `C:\Users\r4rup\AppData\Local\Programs\Python\Python314\python.exe`, PSF Authenticode signature valid; `uv python find 3.14.8` finds it.
- Every locked package has Python 3.14 wheels **at its locked version** (PyPI JSON, 2026-10-27). The `winrt-*` packages have Windows wheels only, which is correct (they carry `sys_platform` markers). So the re-lock should change no package version. If it changes any, stop and report it: no package changes without the owner's yes.

### What to change
1. `pyproject.toml`: `requires-python = "==3.14.*"`; ruff `target-version = "py314"`; mypy `python_version = "3.14"`. Keep `exclude-newer` and `exclude-newer-package` exactly as they are.
2. `.python-version`: `3.14.8`.
3. `uv.lock`: re-lock with **`UV_PYTHON_DOWNLOADS=never`** set for every uv command (uv must never download an interpreter; see the memory note and the owner's rule 8). Show the lock diff summary: it should change only the Python requirement and the wheel lists, no versions.
4. `.venv`: recreate on 3.14.8 (`uv sync --locked`).
5. Fix whatever 3.14 breaks or warns about in `backend/` and `tests/`, without loosening any check:
   - new deprecation warnings (pytest runs with warnings shown; fix ours, and list third-party ones in §3 rather than silencing them);
   - ruff rules that change with `py314` (`UP` rewrites): apply them;
   - mypy findings under 3.14.
   Known: the `httpx` deprecation from `starlette.testclient` is m1b.3's, so leave it.
6. CI: check `.github/workflows/*.yml` take Python from `.python-version` (setup-uv) and need no change; if one hardcodes 3.12, propose the change in §3 (the lead owns workflows).

**Writes only to:** `pyproject.toml`, `uv.lock`, `.python-version`, `backend/`, `tests/`, and §3 of this file. The lead owns `docs/`, `CLAUDE.md` and `.github/`: suggest changes in §3, including the 3.12 lines in [04 §2](../04-architecture.md) (local tools) and [09 §1](../09-tooling.md).

**Skills and docs:** Context7 or docs.python.org for "What's new in Python 3.13" and "3.14" (removals and deprecations that touch `sqlite3`, `asyncio`, `ctypes`, `pathlib`, `logging`, `threading`, `faulthandler`, `zipfile`, `datetime`); say what you checked. No 09 §3 skill fits the builder; say so.

### Done means (through `bash tools/heavy.sh --log m1b.0-<name> …`, results in §3)
- `uv sync --locked`, `ruff check`, `ruff format --check`, `mypy`, `pytest` (default selection) with **no new warnings from our code**, the `secure/` coverage step as CI runs it, `bandit -r backend`, and pip-audit as CI runs it, all pass on 3.14.8; `python --version` from `.venv` shows 3.14.8.
- `pytest -m windows --no-cov` passes (inside Claude; the lead repeats it outside Claude with the owner).
- A hand check: `PYTHONPATH=backend uv run pythonw -m shelfsync.launcher` with a throwaway `SHELFSYNC_DATA_DIR` starts, answers `/api/health`, and quits with exit 0 (the launcher log shows "Tray stopped" and the thread list). Remove the throwaway folder after.
- The brand tests still pass (`brand/`, `npm test`): no change expected.
- CI: "not run on GitHub yet".

**Who:** the `builder` (Sonnet 5.5, **medium**), in its own git worktree on `chore/m1b.0-python-3.14`, cut from the commit the lead names. Commit there (`chore(python): move to Python 3.14 [NFR-7]`); **never push**.

**Out of scope:** the embedded Python and installer (m1b.1); any package version change; the updater (m1b.2).

## 2. Early check
_(Tier B: none.)_

## 3. Builder report
_(builder)_

## 4. Designer report
_(no screens)_

## 5. Review
_(reviewer)_

## 6. Integration notes
_(lead)_

## 7. Handover
_(lead)_
