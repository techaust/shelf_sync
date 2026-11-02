Status: closed (merged as #40, 2026-11-02)
Tier: B
Usage: lead claude-opus-5-5/high [none]: 5-h 32 % at the start · builder claude-opus-5-5/high [none; Context7 windows-toasts]: 5-h 35 → 61 % · analyst claude-opus-5-5/high [none]: 5-h 61 → 75 % · reviewer claude-opus-5-5/high [code-review, security-review] (+ its general-purpose helper, Opus 5.5 high): 5-h 75 % → window reset → 16 % · builder (fixes) claude-opus-5-5/high [none]: 5-h 16 → 23 % · reviewer (re-check) claude-opus-5-5/high [code-review, security-review] (+ helper, Opus 5.5 high): 5-h 23 → 30 % (all 2026-11-02, from `node tools/model-audit.mjs 2026-11-01`; its "no skill loaded" flags on the builders and the analyst are expected: no skill in 09 §3 applies to their part, and Context7 is a tool, not a skill)

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

### Review fixes
_(builder, claude-opus-5-5/high, 2026-11-02; worktree `.claude/worktrees/agent-a9fe4ae75ffb82596`, branch
`worktree-agent-a9fe4ae75ffb82596`, from aab5186; commit 468b636)_ No skill loaded: the fixes touch only the standard
library (argparse, os, re) and PowerShell, so Context7 has nothing to add; `code-review` and `security-review` are the
reviewer's.

| Finding | Fix | Test |
|---|---|---|
| E2: `names.py`'s docstring shows `--suffix -rehearsal` | Now `--suffix=-rehearsal` | (docstring) |
| E3: a dangling link named `build-suffix.txt` reads as "no file" (real names) | `read_build_suffix`: a FileNotFoundError on a path that `os.path.lexists` sees reads as None, never `""` | `test_a_dangling_link_named_like_the_suffix_file_never_yields_the_real_names` (a real symlink; skipped here, this account can't make them), `test_a_suffix_file_that_is_there_but_not_found_on_open_…` (the same branch on any account), `test_a_dangling_junction_…` (Windows; on this PC opening a dangling junction raised PermissionError, already None) |
| E4: the names probe doesn't prove `shelfsync` came from the built or installed folder | `smoke.NAMES_PROBE` exits 1, printing no names, unless `aumid`, `autostart` and `names` sit under `sys.prefix` (realpath and normcase on both sides); the identical copy in `test-installer.ps1` now also requires `$LASTEXITCODE -eq 0`. Single quotes only, no `$` or backtick | `test_the_smoke_probe_fails_when_shelfsync_isnt_the_folders_own`, `test_the_smoke_probe_can_be_passed_inside_a_double_quoted_powershell_string`, the existing probe test (now with `sys.prefix` set to the copy's folder); `test_release_files` keeps both copies identical and checks the exit-code test |
| R1: `-Tag`/`--tag` with `-Suffix`/`--suffix` makes a release-shaped zip with a stamp | `release-build.ps1` throws before anything else; `build.py` calls `parser.error` (exit 2) before `build()` | `test_build_py_refuses_a_tagged_build_with_a_suffix` (and a tag alone still builds), `test_a_tagged_release_build_with_a_suffix_is_refused_before_anything_is_made` (text, before `$repo =`) |
| R2a: argparse's handling of `--suffix -rehearsal` stated as fact | Pinned: `build.main([..., "--suffix", "-rehearsal"])` raises SystemExit 2 before `build()`; build.py's docstring, the `release-build.ps1` comment and a test docstring now point at that test | `test_build_py_refuses_the_suffix_as_a_separate_argument`, `test_build_py_takes_the_suffix_in_one_argument` |
| R2b: the PowerShell `$` vs `\z` comment asserts .NET behaviour | Reworded to intent: "ends in `\z` so that nothing may follow the suffix, not even a line end" (and the same in `test_release_files`' docstring); 04-A untouched | (comments) |
| R3: `aumid.AUMID` and `autostart.VALUE_NAME` copy `names.*` at import | One comment at each: the module copy is what callers and tests use (patch it, not `names.*`) | (comments) |

**Checks:** full `uv run ruff check` ("All checks passed!") and `ruff format --check` ("167 files already
formatted"), once, through the queue (`.logs/t6fix-ruff-check.log`, `.logs/t6fix-ruff-format.log`); `uv run mypy` and `uv run mypy --platform linux`: Success, 74 files
(`.logs/t6fix-mypy.log`, `.logs/t6fix-mypy-linux.log`); full `uv run pytest` through the queue: 2464 passed, 18
skipped, 52 deselected, exit 0, coverage 93 % (`.logs/t6fix-pytest.log`); `uv run bandit -r backend`: exit 0, no
issues. Windows PowerShell 5.1: both .ps1 files parse with no errors; `release-build.ps1 -Tag v0.1.0 -Suffix
-rehearsal` stops with the new message (exit 1) and makes no work folder; the probe line, run by 5.1 against the
existing `build\ShelfSync-0.1.0` (an older build without `names.py`, so the probe minus `names`), prints `ShelfSync`
and `TecHaust.ShelfSync` (exit 0), and the same probe run from the system Python with that folder on `sys.path` exits
1 with the "imported from outside" message. That built folder's `sys.prefix` is the folder itself.

**Not verified:** the release build (the lead runs it): only it runs the new probe against a folder that has
`names.py`, and against the installed `current\python.exe` (which may sit behind the `current` junction; realpath on
both sides is meant to cover that). PowerShell 7 isn't installed here, so the probe quoting was checked on 5.1 only.
The real-symlink test of E3 is skipped on this account (it runs where symlinks can be made, e.g. CI on Linux).

## 5. Review
_(reviewer: Opus 5.5 high, `code-review` + `security-review`, 2026-11-02, on 5883279..aab5186)_ **APPROVE**, 8.5/10. No
critical, high or medium findings. The fail-safe holds (no stamp → real names; invalid or unreadable → None, which
stops before the Run key is opened and sends toasts with no AUMID); a normal build is unchanged; the tests prove
suffixed versus normal names on a real copy of the package; the NSIS writes and deletes all use `${RUN_VALUE}` and
`${AUMID_KEY}`; the PowerShell behaves the same on 5.1 and pwsh. `security-review`: nothing at confidence 8 or above
(the suffix is checked before it reaches makensis, the registry names or the uninstaller's `--service`; the stamp is
plain ASCII, never run). Findings, all low:
1. `-Tag` and `-Suffix` (and `build.py --tag --suffix=`) could be combined into a release-shaped zip carrying a stamp:
   every real install that updated to it would add a second Run value. → fixed (refused in both).
2. Library behaviour stated as fact without a 04-A row (argparse and a separate `-rehearsal` value; PowerShell `$`
   versus `\z`). → fixed (a test pins argparse; the PowerShell comment states intent).
3. `aumid.AUMID` and `autostart.VALUE_NAME` copy `names.*` at import. → fixed (a comment at each names the copy to
   patch).

The reviewer agreed with the early check's E2–E4 as low, and noted that E1 (an update drops the suffix) would make a
rehearsal copy write the **real** Run value after an update, so its guard must land before `release_key.PUBLIC_KEY` is
set.

**Re-check of the fix diff** _(reviewer: Opus 5.5 high, `code-review` + `security-review`, on aab5186..468b636)_:
**APPROVE**, 9/10. E2, E3, E4, R1, R2a, R2b and R3 all fixed; no new finding; 149 passed, 3 skipped. Optional lows it
raised outside the fix diff (follow-ups, not done here): `ShelfSync.nsi` doesn't check the suffix rule itself when
`makensis /DSUFFIX` is run by hand; `build.py`'s `ignore_patterns("build-suffix.txt")` skips that name at any depth,
not only in `shelfsync/platform/`; `names.py` also accepts a lone trailing `\r`, wider than its docstring (harmless:
the rule still applies).

## 6. Integration notes
_(lead, 2026-11-02)_ Both builders worked in their own worktrees and fast-forwarded onto this branch; their worktrees
were removed. `origin/main` (#37 boto3/moto lock, #38 and #39 UI refactors) was merged as 15d7ac6, with no overlap with
T6's files. The app's sync tool stopped on "Committer identity unknown" on the host, so the lead merged with the
repo-local identity.

Checked here on 15d7ac6 before the push:
- `uv run ruff check`, `ruff format --check`, `mypy`, `mypy --platform linux`, `bandit -r backend` and the full
  `pytest`: results in the PR description (logs `.logs/t6-final-*.log`).
- **The release build** (`release-build.ps1 … -Suffix -rehearsal`, work folder `%TEMP%\ssrbt6c`) **passed**. The smoke
  test reports "the Run value and AUMID are ShelfSync-rehearsal and TecHaust.ShelfSync-rehearsal", the installer test's
  new check "the installed Python uses the Run value ShelfSync-rehearsal and the AUMID TecHaust.ShelfSync-rehearsal" is
  ok, and all installer checks passed (log `.logs/t6-release-build-final.log`).
- It was run from a short detached worktree (`%TEMP%\ss6b`) at the same commit. From this worktree's long path,
  build.py's compileall step failed with FileNotFoundError on a cryptography `.pyc` temp file past Windows'
  260-character limit: a limit of this worktree's path, not a T6 defect (CLAUDE.md's 60-character rule covers only
  `-Work`).

**Not verified:**
- The `-m windows` checks: the owner's, outside the Claude app. No code they cover changed for a given throwaway name.
  In Windows PowerShell, from the project folder:

      $env:UV_PYTHON_DOWNLOADS = "never"; uv run pytest -m windows --no-cov 2>&1 | Tee-Object .logs\t6-windows.log

- pwsh 7: not installed here. GitHub's release run uses it, with an empty `-Suffix`.
- The real-symlink E3 test: skipped on this account; it runs on Linux CI.
- An interactive install of a rehearsal Setup: still silent-only while the brief's out-of-scope items remain.

**Follow-ups** for the orchestrator to record in 10 and 11 (the 2026-10-28 row is now closed for the Run value and the
AUMID only):
1. A rehearsal build still uses the real data folder (so its "Remove my data" acts on the real one), the real Credential
   Manager service at run time, the real single-instance name and the real default `InstallDir`.
2. An update installed into a rehearsal copy drops the suffix. The update service should refuse to check or install
   when the build suffix isn't empty. This must land before `release_key.PUBLIC_KEY` is set.
3. The three optional lows from the re-check above.

**Decision for 11** (Lead (proposed)): an invalid `build-suffix.txt` makes Start with Windows report "failed" (never
"not_installed"), and toasts go out with no AUMID.

## 7. Handover
_(lead, 2026-11-02)_ Reviewed and approved (8.5/10, then 9/10 on the fix diff); the full checks and the rehearsal
release build passed on 15d7ac6. Next: push, open the PR, auto-merge on green.

_(lead, 2026-11-02, 08:20 IST)_ Merged on green as [#40](https://github.com/techaust/shelf_sync/pull/40). Its PC session is finished and can be archived. Its worktree and branch are removed from git; the folder `.claude/worktrees/fix-suffix-run-aumid-a5fa38` stays on disk (paths too long for `git worktree remove` to delete, and the app blocks a long-path delete), harmless, for the owner to delete in File Explorer. Task closed.
