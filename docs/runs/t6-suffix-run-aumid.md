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
(`InstallDir`); and an update installed into a rehearsal copy drops the suffix (its zip has no stamp; not reachable
while `release_key.PUBLIC_KEY` is None; early check finding 1). Rehearsal Setups stay silent-only until those are suffixed too. `frontend/**`, `pyproject.toml` and
`uv.lock` are P0's; `docs/10-status.md` and `CHANGELOG.md` are the orchestrator's.

## 2. Early check
_(analyst: Opus 5.5 high, 2026-11-02, on 405e566..48a45ac)_ **GO.** No path in a suffixed build writes or uses the real
Run value or AUMID; `names.py`'s fail-safe holds (missing file → real names; empty, BOM, UTF-16, oversized, invalid,
a directory or a PermissionError → None); a normal build adds no file; the updater's unpack and kept-file checks follow
the manifest from `files.txt`, which lists the stamp. Agrees with "failed" for an invalid stamp. Targeted tests: 150
passed, 3 skipped. Findings, all low:
1. An update drops the suffix: once `release_key.PUBLIC_KEY` is set, a rehearsal copy could install a real release
   whose zip has no stamp. Not reachable today (`PUBLIC_KEY` is None). **Follow-up**, added to the brief's out-of-scope
   list: the update service could refuse to check or install when the build suffix isn't empty.
2. `names.py`'s docstring shows `--suffix -rehearsal`; argparse needs `--suffix=-rehearsal`. → fix.
3. A dangling link named `build-suffix.txt` reads as "no file" (real names). Not reachable (unpack refuses reparse
   points), but a gap in the stated guarantee. → fix (`os.path.lexists`).
4. The smoke and installer probes don't prove `shelfsync` came from the built folder. → fix (assert in the probe).

The lead accepted the builder's choice that an invalid stamp makes `apply_start_with_windows_safely` return "failed",
not "skipped" (which would show the owner "not installed").

## 3. Builder report
_(builder, claude-opus-5-5/high, 2026-11-02; worktree `.claude/worktrees/agent-a261d20e7ef7604ba`, branch
`worktree-agent-a261d20e7ef7604ba`, from 5883279)_

**Skills and tools loaded:** Context7 for windows-toasts (`/websites/windows-toasts_readthedocs_io_en`): confirmed
that `InteractableWindowsToaster(applicationText, notifierAUMID=None)` falls back to Command Prompt's AUMID and uses
`applicationText` as the attribution line, so "no AUMID" for an invalid suffix file is the M1a default. No other
library is touched (argparse, re and pathlib are the standard library; the NSIS change is a comment, so the NSIS docs
weren't needed). `security-review` and `code-review` are the reviewer's (09 §3). Not loaded: `frontend-design`,
`dataviz`, `aws-*`, `artifact-design`, `run` (no screen, S3, page or running-app check in this task).

**What was built (brief points 1 to 6):**
1. `backend/shelfsync/platform/names.py` (new): `SUFFIX_FILE` (`build-suffix.txt` next to it), `SUFFIX_PATTERN`
   (`-[A-Za-z0-9._-]{1,32}`), `is_valid_suffix`, `read_build_suffix(path)` (`""` with no file; the suffix for a valid
   non-empty one, one trailing `\n` or `\r\n` allowed; None for an empty file, a broken rule, non-ASCII, more than 64
   bytes or an unreadable file), `run_value_name(suffix)` and `aumid_for(suffix)` (None for None or an invalid suffix),
   and the module values `BUILD_SUFFIX`, `RUN_VALUE_NAME`, `AUMID`, read once at import.
2. `autostart.VALUE_NAME` and `aumid.AUMID` come from `names` (`str | None`). `apply_start_with_windows(name=None)`
   resolves the name at call time (a given throwaway `name` still wins); with no name it raises `AutostartError`
   ("This build's suffix file is invalid, so the Run value was left alone") after the installed-copy check, so it
   writes and removes nothing. `aumid.is_registered(aumid=None)` defaults to this build's AUMID and is False when there
   is none, so `notify.toast_aumid` gives None. `notify.py` only had its docstrings updated.
3. `packaging/build.py --suffix` (written `--suffix=-x`: argparse takes a separate value that starts with `-` for an
   option; checked here): `check_suffix` runs first in `build()`, before any slow step; `write_build_suffix` writes the
   file after the copies and before `precompile`, so files.txt and the zip list it; `copy_tree` never copies a
   `build-suffix.txt` left in the source tree, so a normal build can't ship a stale one.
4. `release-build.ps1` checks `-Suffix` first (`-cnotmatch '^-[A-Za-z0-9._-]{1,32}\z'`; `\z` because PowerShell's `$`
   also matches before a final line end) and passes `"--suffix=$Suffix"` to build.py and smoke.py only when it isn't
   empty, through argument arrays. `release.yml` is unchanged (no suffix).
5. `smoke.py --suffix` runs `NAMES_PROBE` with the folder's own Python and requires `expected_names(suffix)`;
   `test-installer.ps1` runs the same probe with the installed `current\python.exe` and compares, case included, with
   `ShelfSync$Suffix` and `TecHaust.ShelfSync$Suffix`.
6. `ShelfSync.nsi`: every Run value and AUMID write and delete already used `${RUN_VALUE}` / `${AUMID_KEY}` (built from
   `${AUMID}`); only the header comment changed. A test now holds that.

**Decision the brief left to me (Lead to confirm):** an invalid suffix file makes `apply_start_with_windows_safely`
return **"failed"** (logged as a warning), not "skipped". "skipped" maps to the API's `not_installed`, which would tell
the owner this is a development copy, which is false; "failed" says Start with Windows wasn't applied, which is true,
and touches nothing. `ApplyOutcome` and `start_with_windows_result` keep their values; the settings API retries at the
next save, which again touches nothing. The launcher already goes through the safe apply, so start-up logs the warning
and carries on. Smaller choices: an empty `build-suffix.txt` counts as invalid (a suffixed build always writes a
non-empty one, so an empty file is a broken build, never the real names); build.py keeps its own copy of the rule
(it runs with `python -I` and doesn't import the package) and a test compares it with `names.py`'s.

**Files changed:** `backend/shelfsync/platform/names.py` (new), `backend/shelfsync/platform/autostart.py`,
`backend/shelfsync/platform/aumid.py`, `backend/shelfsync/platform/notify.py` (docstrings),
`backend/shelfsync/api/app_settings.py` (docstring only: "failed" also covers an invalid suffix file),
`packaging/build.py`, `packaging/smoke.py`, `packaging/release-build.ps1`, `packaging/test-installer.ps1`,
`packaging/ShelfSync.nsi` (header comment), `tests/test_build_suffix.py` (new), `tests/test_packaging_build.py`,
`tests/test_release_files.py`. The launcher needed no change (it names neither the Run value nor the AUMID).

**Tests added (Done when):** suffixed vs normal names (`test_a_suffixed_build_carries_the_suffix_in_both_names`,
`test_a_normal_build_or_a_development_run_uses_the_real_names`, and a throwaway copy of the package run in its own
Python process with no file, `-rehearsal` and an invalid file); an invalid file never yields the real names (14
parametrized contents, an unreadable file, and a hypothesis property over any bytes); the Run value, settings API
("failed", Run key untouched), launcher and toast paths with an invalid file; build.py refuses an invalid `--suffix`
(`check_suffix`, and `main` exits 1 before making anything) and writes the file only for a non-empty one (a stubbed
`build()` shows it in the folder, files.txt and the zip, present at precompile, and a stale source copy not shipped);
release-build/test-installer/NSIS text checks in `test_release_files.py`.

**Commands and results:**
- per-file while working: `uv run ruff check` / `ruff format --check` on the changed files: clean; the touched test
  files (`test_packaging_build`, `test_build_suffix`, `test_autostart`, `test_m1b1_launcher`, `test_notify_toast`,
  `test_app_settings`, `test_launcher`, `test_release_files`, `test_backup_misc`): 268 passed, 4 skipped (platform or
  symlink skips that were there before), 9 deselected (Windows marks).
- `uv run mypy`: Success, no issues in 74 source files. `uv run mypy --platform linux`: Success, 74 files.
- `uv run bandit -r backend`: exit 0, no issues (only the existing "nosec encountered" and comment warnings).
- PowerShell 5.1 by hand (no release build): the `-Suffix` rule refuses `rehearsal`, `-`, `-a b`, `-ok<LF>`, 33
  characters and accepts empty, `-rehearsal`, 32 characters, `-A.b_c-1`; `& $Python @buildArgs` passes
  `--suffix=-rehearsal` as one argument; both .ps1 files parse with no errors.
- full suite through the queue, `bash tools/heavy.sh --log t6-pytest uv run pytest`: 2456 passed, 17 skipped, 52
  deselected, exit 0, total coverage 93 % (`names.py` fully covered; the `aumid.py` lines still uncovered are the
  existing registry-read lines only the Windows checks reach).
- full lint once, through the queue: `uv run ruff check` "All checks passed!" (exit 0, `.logs/t6-ruff-check.log`);
  `uv run ruff format --check` "167 files already formatted" (exit 0, `.logs/t6-ruff-format.log`).

**Not verified:** the release build (`release-build.ps1 -Suffix -rehearsal`) was not run, as instructed: the lead runs
it, and only it exercises the new smoke probe on the real built folder, the installed-Python check in
test-installer.ps1, and makensis on the edited header. The Windows-marked tests (`-m windows`) weren't run: no code
they cover changed behaviour for a given throwaway name.

**Open questions:** none blocking. For the lead: the decision above ("failed"), and the `docs/11-decisions.md`
2026-10-28 follow-up row, which this task closes for the Run value and AUMID only (the brief's out-of-scope list stays
open).

## 5. Review

## 6. Integration notes

## 7. Handover
_(lead, 2026-11-02)_ Brief written; builder next.
