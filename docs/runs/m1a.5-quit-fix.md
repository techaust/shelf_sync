Status: open
Tier: B ([12 §2](../12-models-and-usage.md): tray, launcher); the `reviewer` also runs `security-review`, because the stall report is a new output path ([06 §3](../06-security.md))
Usage: `analyst claude-opus-5-5/high` (no 09 §3 skill fits a read-only diagnosis): 5-h 40 → 49 %

# M1a.5: Quit always exits

## 1. Brief
_(lead, Opus 5.5 medium, 2026-10-27)_

**Roadmap:** M1a, a fix before the exit test can pass ([08](../08-roadmap.md) M1a row). The owner asked for it before M1a closes.

**PRD IDs** ([03](../03-prd.md)): **UI-TRAY / SYS-02** (Quit ends ShelfSync), **SYS-03** (the single-instance lock is freed when it ends).

### What happened
In the M1a exit test (2026-10-27, ShelfSync started by the owner from Windows PowerShell, outside the Claude app), one Quit stopped the server cleanly (the log shows "Shutting down" … "Finished server process" at 09:26:11 UTC). But the tray icon stayed visible, its menu still opened, and the process stayed alive for 4+ minutes. It ended about a minute after a second Quit click. Before the Quit, that run had used View logs, a second launch, and about 4 minutes of running. Four other runs closed on one Quit, including start → Quit, start → View logs → Quit, and start → second launch → Quit. Not reproduced.

### Analysis (analyst, Opus high, read-only; summary)
The exact field cause is unproven. Two real defects are confirmed by reading the source:
- **D1, tray.** `Tray.stop()` can return while pystray's message loop is still running, and it says nothing. `tray.py:168-169` joins for 2 s and ignores the result; pystray's `PostMessage` has no errcheck; there is no retry and nothing removes the icon. pystray runs menu actions synchronously inside its WM_NOTIFY handler on the loop thread (`_win32.py:193-224`), so our `os.startfile` (Open, View logs) runs there too. A nested wait in the shell is one way the stop message could be delayed (not verified). The `tray-theme` thread also rebuilds the menu off the loop thread, racing `stop()` (`tray.py:153` clears `_icon` without the lock). The existing check `tests/test_tray.py:517` (`not icon._running`) passes even if the loop never ends, because `stop()` clears that flag itself.
- **D2, process.** Once `run_application` returns, nothing limits how long the process takes to end. `threading._shutdown` joins non-daemon threads with no timeout, and atexit callbacks (`logging.shutdown`, concurrent.futures' `_python_exit`) can wait without a limit. The uvicorn thread's 15 s join also times out without saying so (`launcher.py:127`). Nothing is logged after `server.py:209` removes the handler.

### What to build
1. **Menu actions off the loop thread** (`tray/tray.py`). Open and View logs each run in a short daemon thread named `tray-action-<name>`, still wrapped in `_guarded`, so the WM_NOTIFY handler returns at once. **Quit stays inline:** it only sets two events, and a hung Open must not queue ahead of it. Add a one-line note to `add_quit_guard`'s docstring: a guard must never wait on the loop thread (M5).
2. **`Tray.stop()` that checks its work.** Set `self._icon = None` under `self._lock`, so `refresh()` after `stop()` does nothing. After `icon.stop()`, join the loop for 2 s. If it's still alive:
   1. log a WARNING ("The tray icon's message loop didn't end in 2 seconds");
   2. post the stop once more through `icon._stop()` (private API of the pinned pystray 0.19.5; same precedent as keyring's private methods in [11](../11-decisions.md); re-run `-m windows` on every pystray upgrade);
   3. set `icon.visible = False`, so the icon leaves the tray even if the loop never ends;
   4. join for 1 more second.
   Log INFO "Tray stopped in N.N s", or the warning. In `refresh()`, rebuild the menu only when the paused flag changed.
3. **Exit diagnostics** (`tray/launcher.py`). In `TrayServe.__call__`'s `finally`, before `tray.stop()`: log INFO "Stopping (Quit: yes/no)". After the uvicorn join: log a WARNING if the uvicorn thread is still alive. Before returning: log INFO with the live threads, as names and daemon flags only (`threading.enumerate()`). Both must happen while the log handler is still attached.
4. **Safety exit with a stall report**, a new `backend/shelfsync/tray/exit_guard.py` using only the standard library's `faulthandler`:
   - `ExitGuard.arm(seconds)` opens `paths.tmp / "shutdown-stall.txt"` in binary mode (keep the file object alive) and calls `faulthandler.dump_traceback_later(seconds, repeat=False, file=..., exit=True)`. `rearm(seconds)` re-schedules it. If the deadline passes, the stacks of every thread are written to the file and the process ends with exit code 1.
   - **Stage 1:** armed with **45 s** in `TrayServe.__call__`'s `finally`, before `tray.stop()` (on Quit, a server crash and Ctrl+C alike). 45 s is more than the worst bounded path (about 34 s).
   - **Stage 2:** in `tray/launcher.py` `main()`, after `run_application` returns, if armed: `rearm(5)`, then return normally.
   - The guard is **never cancelled**. A clean exit leaves an empty file, which the next start removes.
   - **Injected, never real in tests:** `main(..., exit_guard=None)` and `TrayServe(..., exit_guard=None)`. Only `backend/shelfsync/launcher.py`'s `__main__` builds the real one, because a real armed guard would end pytest.
   - **At the next start**, in `server._start` before `empty_tmp`: if `shutdown-stall.txt` is non-empty, log one WARNING ("The last exit stalled and was ended by the safety exit") with its content, capped at 64 KB, through the normal redacting handler. `empty_tmp` then removes it. That keeps [06 §3](../06-security.md): everything that is kept passes `redact`.
5. **Docs inside the code:** update the `tray.py` docstring (lines 6-11: the loop may outlive `stop()`; actions run off the loop thread) and the `launcher.py` docstring (the safety exit).

### Decisions taken (lead; rows go into [11](../11-decisions.md) at integration)
- Exit code **1** also means "the exit stalled and the safety exit ended it", because `faulthandler` can only end the process with 1. The next start's WARNING says which one it was. (1 already means "all ports in use", 11, 2026-10-26.)
- The raw dump in `tmp\` is the one output that doesn't pass `redact` while it sits there. It holds only thread ids, file paths, line numbers and function names, never values. It is read back through `redact` at the next start, then removed.
- No early check: Tier B, a small change. The reviewer runs `security-review` for the new output path.
- No new packages.

### Files (backend only; no screens)
**Writes only to:** `backend/shelfsync/tray/tray.py`, `backend/shelfsync/tray/launcher.py`, `backend/shelfsync/tray/exit_guard.py` (new), `backend/shelfsync/launcher.py` (`__main__` builds the real guard), `backend/shelfsync/server.py` (only the stall import before `empty_tmp`), `tests/`, and §3 of this file. The lead owns `docs/` (apart from §3), `CLAUDE.md` and `CHANGELOG.md`: suggest changes in §3.

### Skills and docs
- Context7 for pystray (`/moses-palmer/pystray`) and Python's `faulthandler` and `threading` docs before writing. Read the installed pystray 0.19.5 source (`.venv/Lib/site-packages/pystray/_win32.py`, `_base.py`) and say what you confirmed.
- No 09 §3 skill fits the builder: `code-review` and `security-review` are the reviewer's. Say so in §3.

### Tests
**Default selection (fakes or subprocess):**
- `test_stop_warns_and_returns_when_the_loop_never_ends`: the FakeIcon's loop never ends; one WARNING is logged; `stop()` returns within about 3.5 s; it re-posts once and hides the icon.
- `test_menu_actions_run_off_the_loop_thread`: checked by thread name; a hung action doesn't block the loop.
- `test_quit_runs_inline_even_while_open_is_hung`.
- `test_refresh_after_stop_does_nothing`: covers the lock race.
- `test_trayserve_logs_threads_and_a_stuck_server_thread`.
- `test_exit_guard_arms_on_quit_crash_and_ctrl_c_and_rearms_after_run_application`: with a fake guard.
- `test_in_process_main_never_arms_a_real_guard`.
- `test_stalled_exit_is_ended_and_dumped` (subprocess): the child arms the guard with 1 s and blocks in an atexit callback. It must end within about 3 s with code 1, and the stall file must contain `Thread 0x`. A value held in a local of the stuck frame (for example `ck_live_test`) must **not** appear. Control: the same child without the guard is still alive at 3 s (then killed).
- `test_clean_exit_leaves_an_empty_stall_file_and_code_0` (subprocess).
- `test_stall_report_is_imported_redacted_at_next_start_then_removed`.

**`windows` marker (real pystray):**
- `test_real_stop_ends_the_loop_thread`: replaces the weak `not icon._running` check at `tests/test_tray.py:517` with `not tray._loop.is_alive()`.
- `test_real_stop_while_an_action_is_blocked_still_ends_the_loop`: post `WM_USER+11` with `lParam=0x0202` (WM_LBUTTONUP) to `icon._hwnd` to run the default item on the loop thread, with no mouse.
- `test_real_nested_loop_that_eats_wm_quit_cannot_keep_the_icon`.
- `test_real_hide_from_another_thread_removes_the_icon` (this result becomes a 04-A row).
- `test_exit_guard_under_pythonw_writes_the_file` (no stderr under `pythonw`).

### Done means (through `bash tools/heavy.sh --log m1a.5-<name> …`, results in §3)
- `uv sync --locked`, `ruff check`, `ruff format --check`, `mypy`, `pytest` (default selection), `bandit -r backend`, and pip-audit as CI runs it, all pass.
- `pytest -m windows --no-cov` passes. Note that it runs inside the Claude app's package (see the M1a.4 run file and the status page); the lead repeats it outside Claude with the owner.
- A hand check with `PYTHONPATH=backend uv run pythonw -m shelfsync.launcher` from the worktree: Quit ends the process, and the log shows "Stopping (Quit: yes)", "Tray stopped in …" and the thread list. Say what you couldn't check (you can't click the tray: post the WM_NOTIFY message instead, or say so).
- CI: "not run on GitHub yet".

**Who:** the `builder` (Sonnet 5.5, **medium**), in its own git worktree on `fix/m1a.5-quit`, cut from the commit the lead names. Commit there; **never push**.

**Out of scope:** Pause everything and upload guards (M5); the installer and updater (M1b); a separate exit code for a stalled exit; any change to the server's own shutdown.

## 2. Early check
_(Tier B: none.)_

## 3. Builder report
_(builder, Sonnet 5.5, 2026-10-27; branch `fix/m1a.5-quit-build` cut from `e4e9ac5`)_

**Skills.** No 09 §3 skill fits a builder on this task: `code-review` and `security-review` are the reviewer's; `run` was not needed (the hand check below is a driver script, not a skill use). Context7 was loaded and used for pystray (`/moses-palmer/pystray`).

**What Context7 and the source confirmed.**
- Context7 (pystray): `Icon.stop()` "has no effect if the icon is not running", calls the backend `_stop()`, then joins the setup thread (5 s timeout); `run_detached` on Windows just spawns `run()` in a thread. Nothing in it says `stop()` waits for the loop to end.
- Installed pystray 0.19.5 source (`_win32.py`, `_base.py`): `_stop()` is a bare `PostMessage(hwnd, WM_STOP)` (`_win32.py:133`); `_on_stop` calls `PostQuitMessage` on the loop thread; `_on_notify` runs the default item (`self()`) and menu items (`descriptors[index-1](self)`) synchronously on the loop thread; `Icon.stop()` sets `_running = False` itself (`_base.py:259`), so the old `not icon._running` check proved nothing; `visible = False` calls `_hide()` (NIM_DELETE) on whichever thread sets it. Handlers live in `icon._message_handlers` (used by the nested-loop test).
- Python `faulthandler.dump_traceback_later(timeout, repeat, file, exit)`: `exit=True` calls `_exit(1)` (confirmed from the function's docstring in this interpreter; and by the subprocess test).

**Files changed** (all on `fix/m1a.5-quit-build`):
- `backend/shelfsync/tray/tray.py`: Open and View logs run in `tray-action-open` / `tray-action-view-logs` daemon threads (inside `_guarded`); Quit inline. `stop()` clears `_icon` under the lock, joins the loop 2 s, and if still alive `_force_stop`: WARNING, `icon._stop()`, `icon.visible = False`, 1 s join; INFO "Tray stopped in N.N s" on the clean path. `refresh()` rebuilds the menu only when the paused flag changed. Docstring updated.
- `backend/shelfsync/tray/exit_guard.py` (new): `ExitGuard.arm/rearm`, `STALL_FILE_NAME`; stdlib `faulthandler` only.
- `backend/shelfsync/tray/launcher.py`: `exit_guard` injected into `TrayServe` and `main`; stage 1 (45 s) armed in the `finally` before `tray.stop()`; INFO "Stopping (Quit: yes/no)"; WARNING if the uvicorn thread is still alive after its join; INFO "Threads at exit: name (daemon=…)"; stage 2 (`rearm(5)`) in `main()` after `run_application` if armed; `add_quit_guard` docstring note; module docstring.
- `backend/shelfsync/launcher.py`: `real_exit_guard()` and `__main__` builds the only real guard (no data folder: no guard).
- `backend/shelfsync/server.py`: `_report_stalled_exit` before `empty_tmp` (WARNING with the file, capped at 64 KB, decoded with `errors="replace"`, empty file ignored).
- Tests: `tests/test_tray.py` (FakeIcon gained `_stop`, `reposts`, `loop_never_ends`; two existing tests now wait for the action threads; the weak `not icon._running` check at the old line 517 now checks `not tray._loop.is_alive()`), `tests/test_tray_quit.py` (new), `tests/test_exit_guard.py` (new).
- This file (§3).

**Commands and results** (worktree, through `bash tools/heavy.sh --log m1a.5-<name>` where heavy):
- `uv sync --locked`: ok.
- `uv run pytest` (default selection): **686 passed, 7 skipped, 32 deselected** (the 1 warning is starlette's httpx deprecation, not ours). Log `.logs/m1a.5-pytest.log`.
- `uv run mypy`: Success, no issues in 38 source files.
- `uv run ruff check` and `uv run ruff format --check`: pass (80 files formatted).
- `uv run bandit -q -r backend`: first run failed on B101 (`assert` in `exit_guard.py`); fixed by passing the file object instead; re-run exit 0.
- pip-audit as CI runs it (`uv export --locked --no-emit-project …`, then `pip-audit --require-hashes --disable-pip`): "No known vulnerabilities found".
- `uv run pytest -m windows --no-cov`: **31 passed, 1 skipped** (the V31 Defender check), run inside the Claude app's package; includes `test_real_stop_while_an_action_is_blocked_still_ends_the_loop`, `test_real_nested_loop_that_eats_wm_quit_cannot_keep_the_icon`, `test_real_hide_from_another_thread_removes_the_icon` (it passes: hiding the icon from a non-loop thread works with pystray 0.19.5; this is the 04-A row), and `test_exit_guard_under_pythonw_writes_the_file`.
- CI: not run on GitHub yet.

**Hand check** (the real launcher under `pythonw`, throwaway data folder in `.logs/handcheck-data`, removed afterwards; no browser tab, in-memory secrets). I could not click the tray menu, so a driver script (`scratchpad\handcheck.py`, not in the repo) runs the real `main()` with real pystray, real uvicorn and the real armed `ExitGuard`, and calls `request_quit` from a timer after 8 s. Result: the process ended by itself, **exit code 0, 11.1 s** after start; the log shows "Stopping (Quit: yes)", "Tray stopped in 0.0 s", uvicorn's shutdown lines, then "Threads at exit: MainThread (daemon=False)"; `runtime.json` removed; `shutdown-stall.txt` was left **empty** (0 bytes), as designed.

**Decisions inside the brief.**
- New tray tests live in `tests/test_tray_quit.py` (importing the fakes from `test_tray.py`) rather than growing that 690-line file; the exit-guard and next-start tests are in `tests/test_exit_guard.py`.
- The "nested loop eats WM_QUIT" test swaps `icon._message_handlers[WM_STOP]` for a no-op (a swallowed stop), because a real nested loop on pystray's thread can't be started without patching pystray; it restores the handler and re-posts so the loop thread ends.
- `real_exit_guard()` returns `None` if the data folder can't be resolved (start-up reports that itself). The guard's file is opened at `arm()`, not at construction, so building it creates nothing.
- The "worst bounded path" 45 s is as the brief says; I didn't re-derive 34 s.
- The "Threads at exit" line shows `MainThread (daemon=False)` only after a normal Quit, as expected.

**Not verified.**
- An actual tray click on Quit, View logs and Open (driver replaced the click); the original field stall was not reproduced, so the fix for D1 is checked only by the injected failures (never-ending loop, swallowed stop).
- `-m windows` ran inside the Claude app's package; the lead repeats it outside with the owner.
- The `faulthandler` watchdog under a real stall of the whole launcher (only the child-process model of it, with atexit blocking, and the Windows `pythonw` variant).
- The old `Tray.stop()` semantic "stop returns while `_icon` is already None" for a second call: a second `stop()` does nothing and logs nothing; not separately tested.

**Open questions / suggestions for the lead.**
- 11 rows as in the brief (exit code 1 also means a stalled exit; the raw dump in `tmp\` is the one un-redacted output while it sits there). Also add a 04-A row: pystray 0.19.5 `icon.visible = False` from a non-loop thread removes the icon (windows test above), and `icon._stop()` is a private API to re-check on every pystray upgrade.
- 06 §3 should name `tmp\shutdown-stall.txt` as a kept output that is read back through `redact`.

## 4. Designer report
_(no screens)_

## 5. Review
_(reviewer)_

## 6. Integration notes
_(lead)_

## 7. Handover
_(lead)_
