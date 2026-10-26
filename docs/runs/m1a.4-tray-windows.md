Status: open
Tier: B ([12 §2](../12-models-and-usage.md): tray, launcher, notifications); the `reviewer` also runs `security-review` because it touches `platform/` and sends the install token (09 §3)
Usage: (filled from node tools/model-audit.mjs)

# M1a.4: Tray, launcher and Windows

## 1. Brief
_(lead, Opus 5.5 medium, 2026-10-27)_

**Roadmap:** M1a, the last build step ([08](../08-roadmap.md) M1a row). Exit test of M1a: **the empty app runs from the tray**; the security checks for M1a pass; axe clean. It builds on M1a.1, M1a.2 (security base) and M1a.3 (the built UI the launcher opens).

**PRD IDs** ([03](../03-prd.md)):
- **UI-TRAY / SYS-02:** tray icon (pystray) with the menu Open ShelfSync (default, bold), Pause everything / Resume, View logs, separator, Quit ([05 §6](../05-design-system.md)); the three icon states (normal, paused, needs attention) correct on light and dark taskbars.
- **SYS-03**, the launcher part: single instance; a second launch never starts a second server and opens a signed-in tab.
- **SYS-04:** Start with Windows through `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, default on; turning it off removes the value.
- **SYS-05** (notifications on by default) as far as the real toast adapter goes; toast wording [13 §4](../13-content.md).
- **04-A V29** (windows-toasts only on Windows) and **V33** (who owns a listening socket); **V31** is prepared but run with the owner (below).

**Who:** the `builder` (Sonnet 5.5, **medium**; Tier B, [12 §3](../12-models-and-usage.md)), in its own git worktree on `feat/m1a.4-tray`, cut from the branch head the lead names when starting the task (after M1a.2 and M1a.3). Commit there; **never push**. No screens: the tray menu is Windows' native menu.

**Writes only to:**
- `backend/shelfsync/tray/` (new): icon, menu, launcher, single instance
- `backend/shelfsync/platform/`: `notify.py` (the real toast adapter beside the fake), `autostart.py` (Run value), `sockets.py` (socket owner, V33), `shell.py` (open a URL or folder)
- `backend/shelfsync/server.py`, `__main__.py`, `paths.py`, `db/` (only the M1a.1 carry-overs below), `logs.py` and `platform/secrets.py` (only the M1a.2 carry-overs in item 10)
- `pyproject.toml` and `uv.lock` (pystray, Pillow, windows-toasts)
- `tests/`
- §3 of this file

The lead owns `docs/`, `CLAUDE.md`, `CHANGELOG.md`, `brand/`, `.gitignore` and `.github/workflows/`: suggest changes in §3.

**Skills and tools** ([09 §3](../09-tooling.md)):
- No 09 §3 skill fits the builder; say so in §3.
- **Context7** before writing code that uses pystray 0.19.5 (`/moses-palmer/pystray`), Pillow 12.3, windows-toasts 1.3.1, uvicorn 0.54 (running it in a thread, shutdown), and keyring 25.7. Microsoft Learn for the Win32 calls (`GetExtendedTcpTable`, `OpenProcess`, `OpenProcessToken`/`GetTokenInformation`, `QueryFullProcessImageNameW`, the Run key, named mutexes). List what you looked up.
- Heavy commands through `bash tools/heavy.sh --log m1a.4-<name> …`.
- The `run` skill (09 §3, "checking a change in the running app") for the hand checks at the end.

**Owner decisions that bind this task** ([11](../11-decisions.md)):
- **Packages:** pystray 0.19.5, Pillow 12.3.0 and windows-toasts 1.3.1, already approved in [04 §2.1](../04-architecture.md); windows-toasts (and anything only it needs) with `sys_platform == "win32"` in ShelfSync's own list (V29: confirm in the lock). Nothing else. Pillow and pystray: check whether pystray pulls `six` or others, report them; stop if anything outside the cutoff appears.
- The M1a.2 sign-in contract ([runs/m1a.2-security.md](m1a.2-security.md) item 11 and §3): the launcher uses `issue_ticket()` in-process or the ticket route from a second process, then `sign_in_url()`; the URL is always on `127.0.0.1`, never `localhost`.
- **Port squatting** (11, 2026-10-27; [06 §10](../06-security.md)): before sending the install token to a running copy, the launcher asks Windows which process owns the listening socket on `127.0.0.1:<port>` and sends the token only if that process runs as **the same Windows user** and its image path is the expected ShelfSync Python (`sys.executable` of the launcher, compared case-insensitively after resolving the `current` junction). Otherwise it refuses, logs why (no token) and shows one notification (propose its wording; the lead adds it to 13).
- Never change Windows security settings (CLAUDE.md rule 12).

**Work:**
1. **Process model:** one process runs the server (uvicorn on its bound socket, in a worker thread) and the tray (pystray; verify which thread it must run on under win32). `python -m shelfsync` stays the developer entry; `python -m shelfsync.launcher` is the installed entry (04 §8). Quit stops the tray, then shuts uvicorn down cleanly, removes `runtime.json`, exits 0. Ctrl+C gives exit 0 (M1a.1 carry-over).
2. **Single instance (SYS-03):** a per-user named mutex (`Local\ShelfSync-<user SID>` or similar; verify the namespace) taken **before** anything touches `tmp\` or the database (M1a.1 re-check, medium). A second launch:
   - reads `runtime.json`, checks `GET /api/health` returns ShelfSync's identity, runs the V33 owner check, asks for a ticket from the ticket route, opens `sign_in_url()` and exits 0
   - if the first copy doesn't answer within a few seconds, shows one notification and exits non-zero; never starts a second server
   - `runtime.json` is removed on clean exit and treated as stale when its PID isn't the mutex owner (M1a.1 #12)
   - covers the first-run token race (M1a.2 review #6): only the mutex holder may create the install token
3. **Launcher, first copy:** load the token, bind, start the server and tray, then open the browser with `issue_ticket()` + `sign_in_url()` in-process (no HTTP round trip with the token). Opening the default browser goes through `platform/shell.py` (`os.startfile` or `webbrowser`; verify neither passes the URL through a shell that logs it).
4. **Tray (UI-TRAY, SYS-02):** icons from `brand/assets/tray/` (`tray-{normal,paused,attention}-{light,dark}.ico`), chosen by the taskbar theme (`HKCU\…\Themes\Personalize\SystemUsesLightTheme`; re-read on a theme change if pystray allows, else at start: say which). Menu: **Open ShelfSync** (default item, bold; also the primary click, V13) → a fresh ticket and tab; **Pause everything / Resume** shown but disabled until M5 (as in M1a.3); **View logs** → opens the `logs\` folder in Explorer; separator; **Quit** (waits for a running upload: none exist yet, so it quits at once; leave the hook for M5). Tooltip "ShelfSync". The attention state is driven by a small in-process state object (nothing sets it yet besides tests).
5. **Notifications (SYS-05):** the real windows-toasts adapter behind the M1a.1 `Notifier` interface; AppUserModelID handling is M1b (V14), so in development use what windows-toasts allows without registering one and say what you used. The ERR-06 and start-up notices from M1a.1 now reach real toasts. Linux CI keeps the fake. Under pythonw `sys.stderr` is None: confirm nothing breaks (M1a.2's guards already handle it).
6. **Start with Windows (SYS-04):** `platform/autostart.py` sets or removes the HKCU Run value `ShelfSync` = `"<…>\pythonw.exe" -m shelfsync.launcher` (quoted path), from the `start_with_windows` setting (default true). In development (not running from `%LOCALAPPDATA%\Programs\ShelfSync\current\`), **don't write the Run value**; log that it was skipped. Windows checks use a throwaway value name (`ShelfSync-test-<random>`), removed in `finally`.
7. **V33 socket owner** (`platform/sockets.py`): `GetExtendedTcpTable` (IPv4, listening, owner PID) via `ctypes`, then the process's user SID and image path. Windows checks: a socket this test opens is reported with this process's PID, SID and image; a closed port gives "nobody". Unit tests with a fake for the launcher's decision table (same user + same image → send; other user, other image, no owner, error → refuse).
8. **M1a.1 carry-overs** ([runs/m1a.1-backbone.md](m1a.1-backbone.md) §5, re-check list): single-instance before `tmp\`/database (item 2); "all in use" wording when the port setting isn't 47615 (keep the setting inside 47615–47624 and say so); `resolve_data_paths()` inside the start-up `try`; Ctrl+C exit 0; `UnicodeDecodeError` counts as a migration error; the notice when the data folder can't be created doesn't point to a missing log; a migration ending in a `/* … */` comment after its last `;` is accepted again; the Windows rebind test's docstring; remove `prepare_data_folder`.
9. **M1a.2 carry-overs** ([runs/m1a.2-security.md](m1a.2-security.md) §5, re-check R1, R2, R6):
    - `KeyringSecretStore.set` writes first, then deletes only the `<name>@<service>` leftover keyring makes (so a failed write never leaves no token); Windows test: after two sets there's one entry with the second value
    - Ctrl+C prints one fixed line through the redacting stderr handler, never `sys.__excepthook__`'s traceback, and exits 0
    - under pythonw, a log write or rollover that fails is reported once (a toast through the Notifier, or the attention state: propose which) instead of losing every later line silently; reuse one stderr handler instead of building one per failure
10. **V31 (Defender real-time protection), prepared only:** write the Windows check that writes the EICAR test string into a temp folder and records whether the file is removed or locked and for how long, marked `windows` **and** `defender`, deselected by default. **Do not run it**: it raises a Defender alert, so the lead runs it with the owner present.

**Done means** (through `tools/heavy.sh`, results in §3):
- `uv sync --locked`, `ruff check`, `ruff format --check`, `mypy`, `pytest` (default selection), the `secure/` coverage step, `bandit`, `uv export` + `pip-audit` all pass
- `pytest -m windows` passes (Run value, socket owner, toast adapter smoke test, mutex), leaving no test value in the Run key or Credential Manager (show the `reg query` and `cmdkey` checks)
- a hand check with the `run` skill: start `pythonw -m shelfsync.launcher` from the worktree, see the tray icon, Open ShelfSync gives a signed-in tab (or the signed-out page if M1a.3's build isn't present: say which), a second launch opens a second signed-in tab without a second server, View logs opens the folder, Quit exits and removes `runtime.json`. Screenshot the tray menu and the tab with the built-in browser where possible; say what you couldn't capture
- the brand tests still pass (221)
- CI: "not run on GitHub yet"

**Out of scope:** the installer, shortcuts, AppUserModelID and updates (M1b); Pause everything and live attention state (M5); the toast click opening Review (M5); Settings › App (M1b); running the V31 EICAR check (lead with the owner).

**Report in §3:** files changed, every command and result, resolved lock versions for pystray, Pillow, windows-toasts and their dependencies, what Context7 and Microsoft Learn said (with V29 and V33 results for 04-A), the proposed notification wording, anything not verified, open questions.

## 2. Early check
_(Tier B: none.)_

## 3. Builder report
_(builder, Sonnet 5.5 medium, branch `feat/m1a.4-tray` cut from `6dca164`, not pushed; last commit is in the final message)_

**Skills:** none of the 09 §3 skills fits the builder (`security-review` and `code-review` are the reviewer's; `aws-*` no S3 or IAM code; `frontend-design`, `dataviz`, `artifact-design` no screens). The `run` skill's job (checking the running app) was done by hand, see "Hand check".

**Looked up:** Context7 `/moses-palmer/pystray` (`run`, `run_detached`, `stop`, `MenuItem`, `icon`), `/websites/windows-toasts_readthedocs_io_en` (toasters, default AUMID), `/kludex/uvicorn` (`Server.serve` in a thread, `should_exit`, `capture_signals`), and Microsoft Learn through `/websites/learn_microsoft_en-us_windows_win32_api` (`GetExtendedTcpTable`, `TCP_TABLE_CLASS`, `OpenProcess` + `OpenProcessToken` with `PROCESS_QUERY_LIMITED_INFORMATION` / `TOKEN_QUERY`, `ConvertSidToStringSidW`, Local/Global names). Things I confirmed by reading the installed source or running them: pystray's win32 `_run_detached` is a plain thread and `_assert_icon_handle` saves the PIL image as an .ico and loads it at the system's default size; `windows_toasts.WindowsToaster` makes its notifier from the unregistered text (its own source says `.create_toast_notifier()` fails), `InteractableWindowsToaster` with no AUMID uses Command Prompt's. Not found in the docs I could reach: the keyring `<name>@<service>` leftover rule (read from keyring's `Windows.py`).

### Files changed
- **New:** `backend/shelfsync/launcher.py` (a 6-line entry, see decision 1), `tray/` (`instance.py`, `second_launch.py`, `launcher.py`, `tray.py`, `icons.py`, `state.py`), `platform/sockets.py`, `platform/shell.py`, `platform/autostart.py`.
- **Changed:** `server.py` (`run_application`, `run(on_settings)`, runtime.json clean-up), `platform/notify.py` (real toast adapter), `platform/secrets.py`, `logs.py`, `messages.py`, `paths.py`, `ports.py`, `db/settings.py`, `db/migrate.py`, `api/app.py` (one line, decision 2), `pyproject.toml`, `uv.lock`.
- **Tests:** new `test_sockets.py`, `test_autostart.py`, `test_notify_toast.py`, `test_instance.py`, `test_run_application.py`, `test_second_launch.py`, `test_tray.py`, `test_launcher.py`, `test_defender_v31.py`; edited `test_db.py`, `test_server.py`, `test_paths.py`, `test_output_guards.py`, `test_startup_security.py`, `test_windows_keyring.py`.

### What was built (by brief item)
1. **Process model.** `TrayServe` (the `serve` callable): uvicorn in a worker thread on the bound socket, the tray in pystray's own thread (`run_detached`, a thread on win32), and the main thread waits on an event in 0.5 s steps so Ctrl+C can interrupt it. Quit (and a crashed server) stop the tray, set `should_exit`, join, and return; start-up's own `finally` closes the socket and removes `runtime.json`; exit 0. `python -m shelfsync` stays the developer entry (uvicorn on the main thread, no tray).
2. **Single instance.** `tray/instance.py`: mutex `Local\ShelfSync-<user SID>`, taken in `run_application` before `run()` touches `tmp\`, the database or the token (tests prove a second launch leaves `tmp\`, database, logs and the token store alone). `Local\` chosen over `Global\`: no other user can see or squat it; the cost is that a second logon session of the same user isn't seen (the port check still stops a second server). `runtime.json` is removed on any exit and a leftover one is deleted before the bind. A second launch reads it, checks `/api/health`, runs the V33 check (the socket owner's PID must equal the PID in `runtime.json`, which also catches a stale file), reads the token (read only, never creates it), POSTs to the ticket route and opens `sign_in_url()`; no answer in 5 s: one notification, exit 4; refused by the owner check: exit 5; no ticket: exit 6. The client ignores proxy variables and redirects.
3. **First copy** opens its tab with `issue_ticket()` + `sign_in_url()` in-process through `platform/shell.py` (`os.startfile`, which calls `ShellExecuteW` directly: no shell, nothing logs the address; it only accepts `http://127.0.0.1:`).
4. **Tray.** Menu as 05 §6 (Open default and bold, Pause everything / Resume disabled, View logs, separator, Quit), tooltip "ShelfSync", icons from `brand/assets/tray/` by state and taskbar theme (`SystemUsesLightTheme`, False when unreadable). **Theme change: pystray has no callback, so a small thread re-reads the setting every 5 s** and swaps the icon. Icon frame: the one nearest the system's small-icon size (16/20/24/32). `TrayState` (normal, paused, attention; attention wins) is driven by tests only. Quit has a hook (`add_quit_guard`) for M5.
5. **Toasts.** `ToastNotifier` behind `Notifier`; also logs every message; never raises. windows-toasts needs an AppUserModelID for the toast to show: **in development I used `InteractableWindowsToaster("ShelfSync")` with no AUMID, i.e. Windows' own Command Prompt AUMID**, with "ShelfSync" in the attribution line (so the toast carries Command Prompt's icon until M1b registers ShelfSync's). `sys.stderr is None` under pythonw: confirmed nothing breaks (the hand check ran under `pythonw`).
6. **Start with Windows.** `platform/autostart.py`: `ShelfSync` = `"<dir>\pythonw.exe" -m shelfsync.launcher`; set or removed from `start_with_windows` (default true) by the launcher's `on_settings` hook; **not written unless running from `%LOCALAPPDATA%\Programs\ShelfSync\current\`** (logged as skipped). Verified real registry only through `ShelfSync-test-<random>` values.
7. **V33.** `platform/sockets.py` (`GetExtendedTcpTable` IPv4 listener table, `OpenProcess`, `OpenProcessToken`, `QueryFullProcessImageNameW`, `ConvertSidToStringSidW`). `judge()` is the decision table (same user SID, expected image, runtime.json PID; every process that could receive the connection must pass; any lookup error refuses). IPv6 listeners aren't looked at (a dual-stack `[::]` listener can't take 127.0.0.1 from our exclusive one).
8. **M1a.1 carry-overs:** single instance before `tmp\`/database; the port setting is now **47615–47624 only** (`settings._check` and `candidate_ports` raise outside it; `MIN_PORT`/`MAX_PORT` are gone, so "all in use" is always true); `resolve_data_paths()` inside the try (plain exit 3 and a notice); Ctrl+C exit 0; `UnicodeDecodeError` is a `MigrationError`; data folder or log file that can't be made gets its own notice (no pointer to a missing log); a trailing `/* … */` after the last `;` is accepted again (and text that isn't a comment is still an error); the Windows rebind test docstring was already accurate, so unchanged; `prepare_data_folder` removed.
9. **M1a.2 carry-overs:** `KeyringSecretStore.set` writes first, then removes only the `<name>@<service>` leftover (a failure there is logged, never raised, so a reset can't end half done); Ctrl+C prints `Stopped with Ctrl+C.` through the redacting handler and never `sys.__excepthook__`; one shared stderr handler; **a failed log write or a rollover Windows refuses is reported by one toast through the Notifier (once, chosen over the attention state, which is M5's and means "needs you")** plus the fixed stderr line each time; a refused rollover now reopens the file and tries again at the next rollover time, so later lines aren't lost.
10. **V31.** `tests/test_defender_v31.py`, markers `windows` + `defender`, and skipped unless `SHELFSYNC_RUN_V31=1`; `addopts` now deselects `defender` too. **Not run.** Command for the lead: `$env:SHELFSYNC_RUN_V31 = "1"; uv run pytest tests/test_defender_v31.py -m defender --no-cov -s`.

### Decisions I took inside the brief (for the lead to confirm or change)
1. **`backend/shelfsync/launcher.py`** is a new top-level 6-line file, not in the "writes only to" list: `python -m shelfsync.launcher` (04 §8) needs a module of that name.
2. **`api/app.py`, one line:** `app.state.sessions = sessions`, so the launcher can call `issue_ticket()` in-process (the brief says in-process; `create_app` built the store privately). Nothing in a request handler reads it.
3. **Image check is wider than `sys.executable`.** Observed on this PC: a venv's `python.exe` is a launcher that starts the **base** Python as a child, and the child owns the socket (`Start-Process …\.venv\Scripts\pythonw.exe` gave PID 6340, the listener was PID 4316 at `…\Python312\pythonw.exe`). So the accepted images are `sys.executable`, `sys._base_executable` and the `python.exe`/`pythonw.exe` pair beside each (the launcher and the developer entry differ). In an installed copy these are one folder, as the brief intends. Same user + PID in `runtime.json` are still required.
4. **`httpx` moved from the dev group to the main list**, same pin (0.28.1): the second launch uses it at run time. No new package. The tests use `httpx.MockTransport`, not respx (respx isn't in the lock).
5. **mypy:** `[[tool.mypy.overrides]]` for `pystray` (no type hints) and `windows_toasts` (not installed on Linux); no other change.
6. **Windows run line is unchanged** (`pytest -m windows --no-cov`), because the V31 test also skips on an env variable.

### Packages (lock, after `uv lock`)
Approved and pinned: `pystray 0.19.5`, `Pillow 12.3.0`, `windows-toasts 1.3.1` (`sys_platform == 'win32'` in ShelfSync's own list).
**Pulled in with them (report, nothing outside the 14-day cutoff):**
- by pystray: `six 1.17.0` (all platforms), `python-xlib 0.33` (Linux only), `pyobjc-core`, `pyobjc-framework-cocoa`, `pyobjc-framework-quartz` `12.2.2` (macOS only)
- by windows-toasts, **Windows only** (confirmed in `uv export`: each has `; sys_platform == 'win32'`): `winrt-runtime 3.2.1`, `winrt-windows-data-xml-dom 3.2.1`, `winrt-windows-foundation 3.2.1`, `winrt-windows-foundation-collections 3.2.1`, `winrt-windows-ui-notifications 3.2.1`
**V29 (04-A): confirmed.** windows-toasts and its five WinRT packages are Windows-only in the lock and in `uv export`; it imports and builds a `Toast` on this PC; on Linux `show_toast` raises ImportError. Tests: `test_notify_toast.py::test_v29_*`.
**V33 (04-A): confirmed on this PC.** `GetExtendedTcpTable` (AF_INET, `TCP_TABLE_OWNER_PID_LISTENER`) with the owning PID, then `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `OpenProcessToken(TOKEN_QUERY)` for the user SID and `QueryFullProcessImageNameW` for the image: a socket the test opens is reported with this process's PID, SID and image; a closed port gives nobody; the System process (PID 4, the owner of port 445) can't be opened by an ordinary user, which is an error and therefore "refuse". Port numbers are network byte order in the low 16 bits. A second user's process wasn't tried (there is no second user here).

### Commands and results (logs in `.logs/m1a.4-*.log`)
- `uv sync --locked`: ok. `uv run ruff check`: all passed. `uv run ruff format --check`: 73 files formatted.
- `bash tools/heavy.sh --log m1a.4-mypy uv run mypy`: no issues, 37 files (strict); also `mypy --platform linux`: no issues.
- `bash tools/heavy.sh --log m1a.4-pytest-final uv run pytest`: **565 passed, 7 skipped, 26 deselected.**
- `uv run coverage report --include="backend/shelfsync/secure/*" --fail-under=90`: 100 %, exit 0 (`secure/` untouched).
- `bash tools/heavy.sh --log m1a.4-bandit uv run bandit -r backend`: no issues; three `# nosec` (B606 twice on `os.startfile`, B104 on the `0.0.0.0` constant that is compared, not bound), each with its reason on the line.
- `bash tools/heavy.sh --log m1a.4-windows uv run pytest -m windows --no-cov`: **25 passed, 1 skipped** (the V31 test). It ran the real Run key (throwaway value), mutex (throwaway name), socket owner, toast smoke test (one toast appeared), a real tray icon for about a second, and Credential Manager.
- After it: `reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run"` filtered for ShelfSync: **no line** (no `ShelfSync` and no `ShelfSync-test-*`). `cmdkey /list:ShelfSync-test-*`, `/list:*@ShelfSync-test-*`, `/list:ShelfSync` and `/list:*@ShelfSync`: all `* NONE *`.
- **`uv export --locked --no-emit-project --format requirements-txt` then `bash tools/heavy.sh --log m1a.4-pipaudit uv run pip-audit --require-hashes --disable-pip -r .logs/locked.txt`: FAILS, exit 1: 37 known vulnerabilities, all in `pillow 12.3.0`, all fixed only in `13.0.0`** (CVE-2026-96636, -96638, -96640, -96641, -96778, -112390 to -112406, -112891 to -112901, -114501, GHSA-78g4-xqwv-q3g8, and more; full list in `.logs/m1a.4-pipaudit.log`). Nothing else is flagged. **This needs the owner's decision (open question 1); I changed nothing.** ShelfSync only opens its own six .ico files with Pillow, but CI's pip-audit step will fail on this.
- Brand tests (221): **not run**: this worktree has no `brand/node_modules`, the branch changes nothing under `brand/`. CI: not run on GitHub yet.

### Hand check (`pythonw -m shelfsync.launcher`, no browser used by me)
Run from the worktree with `SHELFSYNC_DATA_DIR` pointing at a temp folder (the real `%LOCALAPPDATA%\ShelfSync` untouched), then everything removed.
- **Server and runtime.json:** listening on `127.0.0.1:47615` only (`netstat`), `runtime.json` = `{"port": 47615, "pid": 4316}`, the PID of the real (base) pythonw, not the venv launcher's. Log shows "Start with Windows: skipped, this isn't the installed copy" (development, no Run value) and the server start-up lines.
- **Tray icon:** found with UI Automation, named "ShelfSync" (the tooltip), in the overflow flyout of the Windows 11 tray. Two hidden pystray windows of class `ShelfSync…SystemTrayIcon` belong to the process.
- **Second launch:** exit code 0 after 3.2 s; no second listener, same PID in `runtime.json`; the log shows its `GET /api/health` and `POST /api/session/ticket` both 200; `tmp\` untouched. (A tab in the default browser opened for the first launch; the second launch's tab I could not see.)
- **Crash recovery:** after a hard kill of the process, `runtime.json` stayed (stale) and a new launch became the first copy (mutex freed) and replaced it.
- **Not verified:** the tray menu itself (right-click) and Quit and View logs on the real process: this session has no interactive input (`CopyFromScreen` fails with "handle invalid", simulated clicks and keys opened no menu), so **I have no screenshot of the tray menu or the tab**. I posted the left-click message to the tray window and saw no observable change (can't tell if a tab opened). Quit, View logs and Open are proven only by the unit tests (`TrayServe` on a real uvicorn: Quit stops the tray then the server, port closed, runtime.json removed by start-up; View logs asks the shell for `logs\`; Open gives a fresh ticket per click) and the menu structure by a Windows test with the real pystray objects. The UI build isn't on this branch, so opening ShelfSync shows a 404 or the bare API.
- Left behind: the first launch created the real `install-token` entry under the real `ShelfSync` Credential Manager service (that is the app's first run); **I deleted it** (`cmdkey /delete:ShelfSync`, then `/list` shows NONE). No Run value was written.

### Proposed wording (for 13 §3/§4; in `messages.py`)
- Second launch, first copy not answering: "ShelfSync is already running but isn't answering. Wait a moment, then open it from the tray icon."
- Second launch, port owner not trusted (port squatting): "ShelfSync didn't open a tab: the program answering on its port isn't your copy of ShelfSync. Details are in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log"
- Second launch or tray, no signed-in tab: "ShelfSync is running but couldn't open a signed-in tab. Open it from the tray icon."
- Log file not writable (once): "ShelfSync can't write to its log file, so some events may be missing from it. Check that %LOCALAPPDATA%\ShelfSync\logs isn't locked by another program."
- Data folder or log file can't be used at start-up: "ShelfSync couldn't use its data folder, so it didn't start. Check that %LOCALAPPDATA%\ShelfSync exists and that you can write to it."
Also: the port setting is now limited to 47615–47624 (03/04 text for SET-06 may want that).

### Not verified
Linux CI and GitHub (nothing run there; `mypy --platform linux` passes here, the Linux-only branches ran only through that and the skips); the real tray menu, Quit, View logs, Open and a screenshot (above); the theme-change swap on a real taskbar (tested with a fake pystray and a poll); a second Windows user for V33; an IPv6 listener; Ctrl+C in a real console (simulated by raising `KeyboardInterrupt` in `serve` and the wait loop); the brand tests; V31 (not run, by instruction); the toast's appearance (the smoke test calls the API; whether it was seen depends on Focus Assist).

### Open questions
1. **Pillow 12.3.0 fails pip-audit (37 findings, fixed only in 13.0.0).** Options: (a) the owner approves 13.0.0 as a security exception, as for certifi and filelock (a major version and a new pin in 04 §2.1; I did not try the upgrade), (b) ignore the findings in pip-audit because ShelfSync never opens untrusted images, (c) leave it red. pystray needs a Pillow image, so it can't be dropped.
2. Is the wider image check (decision 3) fine, or should the launcher insist on `sys.executable` only (then a development launch through a venv would always be refused)?
3. Toasts use Command Prompt's AUMID until M1b. Fine for now?
4. `Local\` versus `Global\` for the mutex (above): confirm `Local\`.

### Fix round 1
_(builder, Sonnet 5.5 medium; the "Fix now" rows of the §5 triage; rows 3 and 10 are not mine)_

| # | What changed | Test that proves it |
|---|---|---|
| 1 | `Tray.start()` passes pystray a `setup` callback that sets `visible` and a ready Event; `stop()` waits for it (5 s, `ready_timeout`), then stops; if the loop never comes up it logs, stops anyway and returns | `test_tray.py`: `test_stop_before_pystray_is_ready_waits_for_it_then_stops` (fails if stop ran before setup), `..._never_gets_ready_still_returns_and_stops`, `test_the_setup_callback_shows_the_icon`, `test_an_icon_that_cant_be_stopped_is_logged_not_raised`; Windows: `test_the_real_icon_stopped_straight_after_start_really_stops` (the real loop ends) |
| 2 | New `logs.RedactingAppendHandler` / `configure_append_logging` (never rotates or prunes; same redaction and `handleError`); the second launch uses it | `test_output_guards.py`: `test_the_second_launchs_handler_never_rotates_or_prunes_the_running_copys_log` (log file aged 3 days, rotate refused: nothing renamed, no toast), its control `test_the_rotating_handler_on_the_same_old_file_would_have_rotated_it`, the failed-write report test; `test_launcher.py::test_main_second_launch...` sees only the append handler |
| 4 | `default_instance_lock()` moved inside the start-up `try` | `test_run_application.py::test_a_failing_default_lock_is_a_plain_exit_code_not_a_traceback` |
| 5 | Comment in `tray/instance.py` corrected (a second logon session can start a second server on the next port; a data-folder lock file is M1b) | comment only |
| 6 | `server.ServerStoppedError`, raised by `TrayServe` when the server dies after it came up; `run()` gives it `messages.SERVER_STOPPED` ("ShelfSync stopped unexpectedly. The reason is in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log") and exit code 7; a server that never starts stays "couldn't start" | `test_run_application.py::test_a_server_that_stops_by_itself_has_its_own_notice_and_exit_code`; `test_launcher.py::test_a_server_that_dies_ends_the_launcher_with_an_error` and `test_a_server_that_never_starts_is_still_a_start_failure` |
| 7 | The token goes through a new client made after the owner check (the probe client is closed first) | `test_second_launch.py::test_the_token_goes_over_a_fresh_connection_not_the_one_probed_before_the_owner_check` |
| 8 | `open_url` parses with `urlsplit`: scheme http, host exactly 127.0.0.1, whole port, no user info, authority equals `127.0.0.1:<port>`, no whitespace or control characters | new `tests/test_shell.py` (3 good, 24 bad addresses incl. `http://127.0.0.1:1@evil.example/`, on the fake and the real shell; error text never repeats the address) |
| 9 | The "icon couldn't be changed" warning is once per (state, theme) icon, not every poll | `test_tray.py::test_a_missing_icon_file_is_warned_once_per_icon_not_every_poll` |
| 11 | Quit test records the order (tray stopped while the server still answers 200, then the port closes) and asserts no `uvicorn` thread is left; `make_on_settings(run_key, installed)` takes a `FakeRunKey` and a forced `installed`, so no test calls the real `apply_start_with_windows` on the real key; the real-key Windows test forces "development" by patching `is_installed_copy`; the Windows tray test now also stops straight after start | `test_launcher.py::test_quit_stops_the_tray_then_the_server_and_returns`, `test_the_settings_hook_*`; `test_autostart.py::test_the_real_run_key_is_not_written_by_a_development_apply` |
| 12 | `run_application(make_serve, ...)` builds `serve` from the one resolved `DataPaths`; the launcher no longer calls `resolve_data_paths()` again | `test_run_application.py::test_the_data_folder_found_once_is_the_one_serve_is_built_for` |

**Commands** (logs `.logs/m1a.4-fix-*.log`): `ruff check` and `ruff format --check` clean (74 files); `mypy` and `mypy --platform linux`: no issues; `pytest`: **608 passed, 7 skipped, 27 deselected**; `pytest -m windows --no-cov`: **26 passed, 1 skipped** (V31, not run; `-m defender` not used); `secure/` coverage 100 %, exit 0; `bandit -r backend`: clean. After the Windows run: `reg query ...\Run` filtered for ShelfSync shows no line; `cmdkey /list:ShelfSync-test-*`, `/list:*@ShelfSync-test-*` and `/list:ShelfSync` all `* NONE *`. Not run: pip-audit (Pillow, the owner's), brand tests, Linux, GitHub.

### Fix round 2
_(builder, Sonnet 5.5 medium; the re-check's M1 and L1, L2, L3, L5, L6; L4 is the M1b brief's)_

| Item | What changed | Test that proves it |
|---|---|---|
| M1 | The icon runs on our own daemon thread `tray-loop` calling `Icon.run(setup)`; pystray starts its setup thread from that thread, so it is daemon too (read in `pystray/_base.py` `_start_setup`; its win32 `_run` is what `run_detached` already runs on a worker thread, and Context7 says Windows-only targets may call `run()` off the main thread). Comment rewritten | `test_tray.py::test_the_loop_thread_and_pystrays_setup_thread_are_daemon`, `test_a_loop_that_comes_up_after_stop_gave_up_does_not_keep_the_process_alive`; Windows: `test_the_real_icons_loop_and_setup_threads_are_daemon` (real loop and real `_setup_thread` daemon, loop ends after stop) |
| L1 | `raise ServerStoppedError(...) from crashed[0]` | `test_launcher.py::test_the_stopped_error_keeps_the_crash_as_its_cause` |
| L2 | A separate `_quit_requested` flag (set only by `request_quit`); the wait loop ending without it is "stopped unexpectedly", crash or plain return | `test_a_server_that_returns_by_itself_without_a_quit_is_reported_as_stopped`, `test_a_quit_that_ends_the_server_is_not_reported_as_stopped` |
| L3 | `RedactingAppendHandler` opens lazily (`delay=True`) and its `emit` catches the open error (the stdlib raises it out of the logging call when delayed: found by the test) and reports it like a failed write; `_append_logging` returns None if the handler can't even be built, so the second launch carries on | `test_a_log_file_that_cant_be_opened_doesnt_stop_the_second_launch` (a folder where the log file should be), `test_a_handler_that_cant_even_be_built_means_no_file_log_not_a_failed_start`, `test_the_append_handler_makes_no_file_until_the_first_line` |
| L5 | Comment in `second_launch.py` says the fresh client narrows the gap, doesn't close it | comment only |
| L6 | `refresh()` rebuilds the menu before trying the image; `_watch_theme` uses `self._key()` and skips a key that already failed (retried on a state or theme change or an explicit `refresh()`) | `test_the_menu_follows_the_state_even_when_the_icon_file_is_missing`, `test_an_icon_that_failed_to_load_is_not_read_again_every_poll` |

**Commands** (logs `.logs/m1a.4-fix2-*.log`): ruff check and format check clean (74 files); `mypy` and `mypy --platform linux` no issues; `pytest` **618 passed, 7 skipped, 28 deselected**; `pytest -m windows --no-cov` **27 passed, 1 skipped** (V31; no `-m defender`); `bandit -r backend` clean. Afterwards `reg query ...\Run` filtered for ShelfSync: no line; `cmdkey /list:ShelfSync-test-*`, `/list:*@ShelfSync-test-*`, `/list:ShelfSync`: `* NONE *`. Not run: pip-audit (Pillow, the owner's), brand tests, Linux, GitHub.

## 4. Designer report
_(none: native tray menu)_

## 5. Review
**Review** _(reviewer, Opus 5.5 high, `code-review` + `security-review` by hand on `6dca164..00d3c79`, 2026-10-27)_ **APPROVE**: nothing critical or high. Security verdict: no other Windows user's program and no non-ShelfSync process can receive the install token (exclusive bind, mutex, SID check, PID check, token read only after a trusted verdict, `trust_env=False`, no redirects). Ran: `pytest` 565 passed, 7 skipped, 26 deselected; `mypy --platform linux`, ruff, format, `uv lock --check` clean. Not run: `-m windows`, `-m defender`, Linux, brand tests.

**Triage** _(lead, Opus 5.5 medium, 2026-10-27; Tier B)_

| # | Sev | Finding | Decision |
|---|---|---|---|
| 1 | M | `stop()` before pystray is ready does nothing; the process hangs holding the mutex | **Fix now:** a `setup` callback sets a ready Event (and `visible`); `stop()` waits on it with a timeout; a fake-pystray test with stop before ready; if pystray's thread fails before ready, the process still exits |
| 2 | M | A second launch's rotating handler can fire a false "can't write its log" toast and prune with 30 | **Fix now:** the second launch logs through a handler that never rotates (same redacting formatter and `handleError`); test with an old file time |
| 3 | M | pip-audit fails on Pillow 12.3.0 | **Owner's decision** (package); lead recommends Pillow 13.0.0 as a security exception, then rerun the tray tests and `-m windows` |
| 4 | L | `default_instance_lock()` outside the `try` | **Fix now** |
| 5 | L | Wrong comment: the port check doesn't stop a second session's server | **Fix now** (comment); a lock file in the data folder covering every session → **M1b brief** |
| 6 | L | A server that dies mid-session is reported as "didn't start" | **Fix now:** its own exception and message, proposed for 13: "ShelfSync stopped unexpectedly. The reason is in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log" |
| 7 | L | The token POST may reuse a connection opened before the owner check | **Fix now:** a fresh client for the POST |
| 8 | L | `open_url` prefix check accepts `http://127.0.0.1:1@evil.example/` | **Fix now:** `urlsplit` (scheme http, hostname 127.0.0.1, no user info, integer port) with tests |
| 9 | L | A missing `.ico` warns every 5 s | **Fix now:** warn once per key |
| 10 | L | Private keyring methods `_read_credential`, `_delete_password` | **Keep**, with a note: rerun `-m windows` on every keyring upgrade (lead adds it to 09) |
| 11 | L | Quit-order test proves neither order nor shutdown; two tests call the real `apply_start_with_windows`; the Windows tray test hides #1 | **Fix now:** record call order and assert the uvicorn thread ended; inject `FakeRunKey` / patch `is_installed_copy` |
| 12 | L | `serve` resolves data paths a second time | **Fix now:** pass the resolved paths in |
| Q | — | Image check widening; `Local\` mutex; Command Prompt AUMID | **Accept** the widening (the SID is the boundary, 06 §10) and `Local\`. Optional tightening to the install folder for installed copies and ShelfSync's own AUMID → **M1b brief** |

Fixes by the `builder` at medium, then a re-check by the `reviewer` at medium.

## 6. Integration notes
_(empty)_

## 7. Handover
_(lead, 2026-10-27)_ Brief written at Opus 5.5 medium. Starts after M1a.2 and M1a.3 are ready, from the branch head the lead names.
