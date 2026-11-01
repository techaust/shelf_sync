Status: open
Tier: B
Usage: lead claude-opus-5-5/high: 5-h 32 % at the start (2026-11-02)

# T6: a `-Suffix` build uses suffixed names for the Run value and the AUMID

Closes the follow-up from m1b.3 review finding 7 ([11](../11-decisions.md), 2026-10-28): a rehearsal build
(`packaging/release-build.ps1 … -Suffix -rehearsal`) still writes the real `ShelfSync` Run value, and sends toasts as
the real `TecHaust.ShelfSync` AUMID, if it is installed interactively and started. The installer already suffixes
both (`packaging/ShelfSync.nsi`: `RUN_VALUE`, `AUMID`); the app doesn't know its build's suffix. Started by the
orchestrator session on 2026-11-02 as one of its parallel tasks (T4, T5, P0, T6, T7).

## 1. Brief
_(lead, 2026-11-02)_

**PRD IDs:** SYS-04 (Start with Windows, the Run value), SYS-05 and SYS-01 (the toast AUMID the installer registers).

**Design (Lead decision):** the build stamps the suffix into the app, as the 11 row asked.
1. A new module `backend/shelfsync/platform/names.py` is the one place the app's Windows names come from:
   - the build suffix: read once from a plain text file `build-suffix.txt` next to `names.py`, which only a suffixed
     build writes. No file means `""` (a normal build, a development run, every test). It is data, never code: no
     generated Python;
   - the suffix rule: empty, or `-` followed by 1 to 32 of `A-Z a-z 0-9 . _ -`. A file that is present but breaks
     the rule (or can't be read) must never fall back to the real names. The app then skips the Run value (logged)
     and sends toasts with no AUMID (windows-toasts' default), the safe side;
   - `RUN_VALUE_NAME = "ShelfSync" + suffix` and `AUMID = "TecHaust.ShelfSync" + suffix` (or functions; the builder
     chooses, keeping them easy to test with a given suffix).
2. `platform/autostart.py` (`VALUE_NAME`, the default `name`), `platform/aumid.py` (`AUMID`, `is_registered`'s
   default) and `platform/notify.py` (`toast_aumid`) take their names from `names.py`. The Windows tests' throwaway
   names keep working.
3. `packaging/build.py` takes `--suffix` (validated with the same rule; default none) and, when it isn't empty, writes
   `shelfsync/platform/build-suffix.txt` into the built folder before precompiling. A normal build writes no file, so
   its folder, zip and `files.txt` are unchanged.
4. `packaging/release-build.ps1` checks `-Suffix` against the same rule at the start and passes `--suffix` to
   `build.py`. `release.yml` passes no suffix and is not changed.
5. **Proof on the real build:**
   - `packaging/smoke.py` takes `--suffix` and checks that the built folder's own Python reports the expected Run
     value name and AUMID;
   - `packaging/test-installer.ps1`, after the install, asks the installed Python for both names and checks they
     equal `ShelfSync$Suffix` and `TecHaust.ShelfSync$Suffix`: the same names the NSIS script wrote and its
     uninstaller removes.
6. `packaging/ShelfSync.nsi`: check that every Run value and AUMID write and delete uses `${RUN_VALUE}` and
   `${AUMID}`; change only what doesn't. Its header comment says the app now carries the suffix too.

**Files:** backend: `backend/shelfsync/platform/{names,autostart,aumid,notify}.py`, the launcher only if it names the
Run value or the AUMID itself, `packaging/{build.py,smoke.py,release-build.ps1,test-installer.ps1,ShelfSync.nsi}`,
and their tests (`tests/test_autostart.py`, `tests/test_m1b1_launcher.py`, `tests/test_notify_toast.py`,
`tests/test_packaging_build.py`, `tests/test_release_files.py`, or a new `tests/test_build_suffix.py`). No screens.

**Skills:** Context7 for any library touched (NSIS has none: the official NSIS docs); the reviewer runs `code-review`
and `security-review` (`platform/` and the installer).

**Done when:**
- a test proves a suffixed build's Run value name and AUMID carry the suffix, and a normal build's are `ShelfSync` and
  `TecHaust.ShelfSync`;
- a test proves an invalid `build-suffix.txt` never yields the real names, and `build.py` refuses an invalid
  `--suffix`;
- `uv run ruff check`, `ruff format --check`, `mypy`, `mypy --platform linux`, `pytest` and `bandit -r backend` pass;
- the release build (CLAUDE.md, `-Suffix -rehearsal`, a new empty work folder of at most 60 characters) passes here,
  including the new smoke and installer checks.

**Out of scope (follow-ups, not this task):** a rehearsal build installed interactively still uses the real data
folder (`%LOCALAPPDATA%\ShelfSync`, so its uninstaller's "Remove my data" would act on the real data folder), the real
Credential Manager service at run time, the real single-instance name, and the real default install folder
(`InstallDir`). Rehearsal Setups stay silent-only until those are suffixed too. `frontend/**`, `pyproject.toml` and
`uv.lock` are P0's; `docs/10-status.md` and `CHANGELOG.md` are the orchestrator's.

## 2. Early check

## 3. Builder report

## 5. Review

## 6. Integration notes

## 7. Handover
_(lead, 2026-11-02)_ Brief written; builder next.
