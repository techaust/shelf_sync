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
- `backend/shelfsync/server.py`, `__main__.py`, `paths.py`, `db/` (only the M1a.1 carry-overs below)
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
9. **V31 (Defender real-time protection), prepared only:** write the Windows check that writes the EICAR test string into a temp folder and records whether the file is removed or locked and for how long, marked `windows` **and** `defender`, deselected by default. **Do not run it**: it raises a Defender alert, so the lead runs it with the owner present.

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
_(empty)_

## 4. Designer report
_(none: native tray menu)_

## 5. Review
_(empty)_

## 6. Integration notes
_(empty)_

## 7. Handover
_(lead, 2026-10-27)_ Brief written at Opus 5.5 medium. Starts after M1a.2 and M1a.3 are ready, from the branch head the lead names.
