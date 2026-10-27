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
_(builder, Sonnet 5.5 medium, 2026-10-27)_

**Skills:** no 09 section 3 skill fits this task (pure runtime move, no AWS/boto3 code touched). Context7 (`/websites/python_zh-cn_3_14`, the 3.14 docs) used for the "What's new" check.

**Files changed:** `pyproject.toml` (requires-python `==3.14.*`, ruff `py314`, mypy `3.14`; `exclude-newer*` untouched), `.python-version` (3.14.8), `uv.lock`, `backend/shelfsync/logs.py`, `paths.py`, `tray/icons.py`, `tray/second_launch.py`, `tests/test_exit_guard.py`, `test_launcher.py`, `test_tray.py`, `test_windows_keyring.py`, this file. Commit: `chore(python): move to Python 3.14 [NFR-7]`.

**Commands (all with `UV_PYTHON_DOWNLOADS=never`; heavy ones via `tools/heavy.sh`):**
- `uv lock --python 3.14.8`: resolved 79 packages. Lock diff: `requires-python` line only, plus wheel lists (more entries for 3.14 wheels: +277/-140 `url` lines). **No `name`/`version` line changed.** uv noted "fork markers disjoint with requires-python" (expected, the old 3.12 fork was replaced).
- `uv sync --locked`: ok; `.venv\Scripts\python.exe --version` = Python 3.14.8.
- `ruff check`: 6 errors, all UP037 (quoted annotations, now unneeded on 3.14), fixed with `--fix`. `ruff format`: 3 files reformatted: py314 target rewrites `except (A, B):` to `except A, B:` (PEP 758, valid in 3.14 when there is no `as`). Applied as the brief says; 5 sites in `paths.py`, `second_launch.py`, `test_exit_guard.py`. Both now clean.
- `mypy` (38 files): no issues.
- `pytest` (default, `-W default` first run): 694 passed, 10 skipped, 32 deselected; final run 1 warning only (see below). Coverage total 88 %.
- `coverage report --include=backend/shelfsync/secure/* --fail-under=90`: 100 %. inspect/, match/, apply/ do not exist yet (CI skips them too).
- `bandit -r backend`: 0 issues.
- `uv export --locked ...` + `pip-audit --require-hashes --disable-pip`: "No known vulnerabilities found".
- `pytest -m windows --no-cov -W default`: 31 passed, 1 skipped (V31 Defender, owner present only).
- `brand/`: `npm ci` (locked, 53 packages) then `npm test`: 221 passed.
- Hand check: real launcher code (real server, real tray, `pythonw.exe` of the 3.14.8 venv) with throwaway `SHELFSYNC_DATA_DIR`, driven by a scratch script that skips the browser tab and calls `TrayServe.request_quit()` (the tray menu can't be clicked from here): `/api/health` answered 200 `{"app":"shelfsync","version":"0.1.0"}`, exit code 0, log shows "Tray stopped in 0.1 s" and "Threads at exit: MainThread (daemon=False)". Throwaway folder removed. Not the literal `uv run pythonw -m shelfsync.launcher` command, and Quit was not clicked in the real tray menu.

**What's new 3.13/3.14 checked (Context7, 3.14 docs, plus a grep of `backend/`):** asyncio `get_event_loop()` now raises without a loop, `pathlib.PurePath.as_uri()` deprecated, `ctypes.ARRAY` soft-deprecated, `email.utils.localtime(isdst)` removed. Grep of `backend/` for get_event_loop, as_uri, ctypes.ARRAY, utcnow, utcfromtimestamp, `.warn(`, set_event_loop_policy, iscoroutinefunction: no hits. I did not read the full what's-new pages for sqlite3, zipfile, threading, faulthandler (only the grep and the green tests back that).

**Warnings seen:**
- Ours, fixed: `ResourceWarning: unclosed file` (4 warnings) from `tests/test_exit_guard.py` (child process stdout pipes never closed); now closed. Not new to 3.14 necessarily, shown because of `-W default`.
- Third-party, left: `StarletteDeprecationWarning: Using httpx with starlette.testclient` (m1b.3's). pip-audit prints `cachecontrol: Cache entry deserialization failed, entry ignored` (stale cache entries, harmless, tool's own).

**Not verified:** CI on GitHub (not run); the literal tray Quit click; Windows checks outside Claude (the lead repeats them); full what's-new pages for sqlite3/zipfile/threading/faulthandler.

**Suggestions for the lead:** `.github/workflows/checks.yml` has no hardcoded 3.12 (no `python-version` line; it relies on `.python-version`/setup-uv): no change needed, though confirm setup-uv can find 3.14.8 on the runner (m1b.1 should pin it). Docs still naming 3.12: `docs/09-tooling.md:16` (Python 3.12.10 row), `docs/04-architecture.md:95` (local tools), `docs/02-plan.md:137` and `docs/02-plan-appendix/plan-page.src.html:200` (then republish the plan page), `docs/04-architecture-appendix/A-stack-verification.md:22` (V11 cites `python312._pth` / 3.12 docs; re-verify for 3.14), `docs/11-decisions.md:24` (historical, leave), `CLAUDE.md:58` ("moving from 3.12" can say 3.14 now). Note the unparenthesised `except A, B:` style may surprise readers; it is the py314 formatter's output.

### Fix round 1
Low finding: in `tests/test_exit_guard.py` the stall and clean tests now run each child as `with run_child(...) as child:` with a `try/finally: child.kill()` inside, so the stdout pipe closes and the child is reaped on every path (failed `readline` assert, timed-out `wait`); `Popen.__exit__` only waits, hence the explicit kill. Same assertions. `pytest tests/test_exit_guard.py -W default --no-cov` (16 passed, 3 skipped, no warnings), `ruff check`, `ruff format --check`, `mypy`: clean. `.github/` untouched.

## 4. Designer report
_(no screens)_

## 5. Review
_(reviewer)_

## 6. Integration notes
_(lead)_

## 7. Handover
_(lead)_
