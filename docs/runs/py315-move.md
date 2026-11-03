# Run: move to Python 3.15.2 (py315-move)

Status: open
Tier: B ([12 §2](../12-models-and-usage.md): the tray's toasts, the installer build, packaging)
Usage:

## 1. Brief
_(lead, 2026-11-04)_ The owner moved the project from Python 3.14.8 to **3.15.2** after the fresh start (owner, 2026-11-04, [11](../11-decisions.md)), and approved the package list below. Python 3.15.2 is installed on this PC at `C:\Users\<user>\AppData\Local\Programs\Python\Python315\python.exe` (owner-installed outside Claude, PSF signature valid; not on PATH, use the full path or `py -3.15`).

**PRD IDs:** none new. Keeps SYS-01 (tray and toasts), SYS-06/SYS-07 (installer and update build) and the M1b packaging checks passing on the new Python.

**Approved package changes (owner, 2026-11-04; the lead's throwaway re-lock resolved exactly this, 99 packages):**
- `requires-python = "==3.15.*"`; `.python-version` `3.15.2`.
- winrt forced under `windows-toasts==1.3.1` (which declares `winrt-*~=3.0`) with `[tool.uv] override-dependencies`, each `; sys_platform == 'win32'`:
  `winrt-runtime==4.1.0`, `winrt-windows-data-xml-dom==4!10.0.28000.2957`, `winrt-windows-foundation==4!10.0.28000.2957`, `winrt-windows-foundation-collections==4!10.0.28000.2957`, `winrt-windows-ui-notifications==4!10.0.28000.2957`; uv adds `winrt-windows-storage-streams 4!10.0.28000.2957` as a new dependency.
- 14-day exceptions in `exclude-newer-package` (`2026-11-01T00:00:00Z`) for those six winrt packages only. `exclude-newer` stays `2026-10-13T00:00:00Z`; the other 92 packages must stay at their locked versions (stop and ask if `uv lock` changes any other).
- PyYAML 6.0.3 (dev only: bandit, moto, responses) has no cp315 wheel on Windows or Linux, so uv builds it from its sdist. If it won't build, stop and report; don't add a compiler, a different PyYAML or any other package.
- Every uv command with `UV_PYTHON_DOWNLOADS=never`.

**Files (backend layer, builder):**
- `pyproject.toml` (requires-python, ruff `target-version = "py315"`, mypy `python_version = "3.15"`, the override and exceptions with a comment citing 11), `.python-version`, `uv.lock` (from `uv lock`, never by hand).
- `packaging/build.py`: `PYTHON_VERSION = "3.15.2"`, `PYTHON_TAG = "315"`, `EMBED_SHA256 = "d012f3aa29cf07436dae8aea1fec0fd195c2612a0b059b1f915ae0afb9ad1f62"` (python.org's release page for 3.15.2, Windows embeddable package 64-bit, 13.1 MB; check the downloaded file against it); docstrings and comments naming 3.14 or `python314`.
- `packaging/release-build.ps1`, `packaging/smoke.py`: comments and any version check.
- Every other code or test reference to `314` / `3.14` (`tests/test_packaging_build.py`, `tests/test_m1b1_launcher.py`, `tests/test_tray_icons_path.py`, `tests/test_update_manifest.py`, and the launcher or update code if it names `python314._pth`). Find them all with a search, not only this list.
- `.github/workflows/checks.yml` (comments; `python-version-file` already follows `.python-version`; actions/python-versions has a 3.15.2 build). `release.yml` if it names a version.
- `tools/cloud/setup.sh` and `tools/cloud/session-start.sh`: GitHub's actions/python-versions 3.15.2 Linux build for Ubuntu 24.04 x64 (its release URL and SHA-256 from that repo's `versions-manifest.json` and the release asset, both checked), `python3.15` names, `/opt/hostedtoolcache/Python/3.15.2/x64`.
- Docs: [04](../04-architecture.md) §2.1 (the Python and embeddable rows, their SHA-256), [ADR 0001](../adr/0001-python-fastapi-sqlite-react.md) and [0002](../adr/0002-embedded-python-nsis.md) (a dated amendment line each, not a rewrite), [04-A](../04-architecture-appendix/A-stack-verification.md) (a new V row: windows-toasts 1.3.1 on winrt 4.x, what was verified and what only the owner's `-m windows` run proves), [09](../09-tooling.md) and [02](../02-plan.md) / [08](../08-roadmap.md) only where they state the current Python version, CLAUDE.md's "Python is **3.14.8**" and the release-build line, [runbooks/fresh-start.md](../runbooks/fresh-start.md) and [runbooks/cloud-sessions.md](../runbooks/cloud-sessions.md), the `docs/memory/` notes naming 3.14.8. Leave history (dated rows in 11, old run files, CHANGELOG) as it is.

**First, before the edits above (a go/no-go):** in your worktree, after `uv lock` and `uv sync --locked`, prove windows-toasts imports and builds a toast on winrt 4: `uv run python -c "from windows_toasts import InteractableWindowsToaster, Toast, ToastText1; Toast(text_fields=['x'])"` (or the closest that `backend/shelfsync/platform/notify.py` uses), then `uv run pytest -m windows -k toast --no-cov` inside Claude (not the result that counts, V36, but it shows the API still fits). If the import or the API fails, **stop and report**: no toast code is written in this task (owner's choice was the override, not new code).

**Skills:** none fits from 09 §3 for the builder (Context7 isn't signed in on this PC; use the official python.org and PyPI pages). The reviewer loads `code-review` and `security-review` (packaging, `platform/`).

**Done means:**
- `uv sync --locked`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run mypy --platform linux`, `uv run pytest`, `uv run bandit -r backend`, and pip-audit as CI runs it (CLAUDE.md "Commands") all pass on 3.15.2, through `bash tools/heavy.sh --log <name> …`.
- `uv run pytest -m windows --no-cov` run inside Claude, reported as such.
- The release build passes (the lead runs it: `packaging/release-build.ps1` with `-Python` the 3.15.2 python.exe, NSIS at `D:\Business\2. GPL Projects\3. Other Assets\Applications\tools\nsis-3.13\makensis.exe`, a new short `-Work` folder, `-Suffix -rehearsal`).
- One commit per logical step, conventional messages; no push (the lead integrates).

**Out of scope:** any feature, refactor or fix not needed for 3.15.2; Node, uv or NSIS versions; frontend code; the owner's `-m windows` run outside Claude (the lead gives the steps).

## 2. Early check

### Builder: stopped at step 2, PyYAML won't build (2026-11-04)
_(builder)_ **Blocked.** The brief says to stop if PyYAML won't build, so the go/no-go (step 3) **was not run** and nothing else was edited.

**Skills:** none loaded. 09 §3 has no builder row for this task (the brief says the same), and Context7 isn't signed in on this PC (the session reported it needs authorising).

**Step 1, pins and lock (done, commit `c77f510`):** `.python-version` `3.15.2`. In `pyproject.toml`: `requires-python = "==3.15.*"`, ruff `py315`, mypy `3.15`, the five winrt `override-dependencies` (each `; sys_platform == 'win32'`), and the six winrt `exclude-newer-package` entries at `2026-11-01T00:00:00Z`. `exclude-newer` stays `2026-10-13T00:00:00Z`. `UV_PYTHON_DOWNLOADS=never uv lock --python <3.15.2 python.exe>` ran through `heavy.sh` (`.logs/uv-lock-py315.log`, exit 0) and resolved 99 packages. A package-by-package comparison of the old and new `uv.lock` (tomllib script):
- **Versions:** only the five winrt packages changed (3.2.1 → 4.1.0 / `4!10.0.28000.2957`), plus `winrt-windows-storage-streams 4!10.0.28000.2957`, which is new. Every other package keeps its version, and none was removed.
- **Hashes:** no existing wheel or sdist hash changed.
- **Wheel lists:** these changed only because `requires-python` changed. The cp314/cp314t wheels were dropped and the cp315/cp315t wheels of the same versions were added (cffi, charset-normalizer, coverage, librt, markupsafe, msgpack, mypy, pillow, pydantic-core, pyobjc-*, tomli, ast-serialize). PyYAML gained no wheel, so it has no cp315 wheel, as the brief says.
- **anyio** no longer lists `typing-extensions` as a dependency. That's a marker evaluated on 3.15, not a version change; `typing-extensions` 4.16.0 is still locked.

**Step 2, `uv sync --locked` (looked fine, then failed):**
- The first sync passed (`.logs/uv-sync-py315.log`, exit 0, all 99 installed). But PyYAML wasn't built: the log shows `Registry requirement already cached: pyyaml==6.0.3`. The cached wheel is `py3-none-any` (pure Python, no `_yaml` C extension), generator `setuptools (84.2.1)`, made at 02:21 today, before this task, in the Claude app's private uv cache. Probably by the lead's throwaway re-lock (not verified).
- `--refresh-package pyyaml --reinstall-package pyyaml` reused that same built wheel (`.logs/uv-sync-py315-pyyaml.log`).
- **A clean build fails:** `uv sync --locked --no-cache --reinstall-package pyyaml` (`.logs/uv-sync-py315-pyyaml-nocache.log`, exit 1). The build deps uv chose under the 14-day cutoff were setuptools 84.0.0 and Cython 3.3.0. PyYAML tries to compile `yaml._yaml`, and the build stops with:
  `error: Microsoft Visual C++ 14.0 or greater is required. Get it with "Microsoft C++ Build Tools": https://visualstudio.microsoft.com/visual-cpp-build-tools/`
  (`error: Failed to build pyyaml==6.0.3`; `Call to _pyyaml_pep517.build_wheel failed (exit code: 1)`). The log also shows `No pyyaml_build_config setting found.`
- **Today's `.venv` works only because of that earlier cached wheel.** On a fresh PC, a new worktree with an empty cache, or `--no-cache`, `uv sync --locked` fails on Windows. Linux CI and cloud sessions have a C compiler, so the sdist would probably build there (not verified).

**Not verified (no more tries, per the brief):**
- Why the 02:21 build passed. The setuptools version differs (84.2.1 there, 84.0.0 under the project's cutoff), but I don't know whether that's the cause.
- Whether a PyYAML build setting (the `pyyaml_build_config` config setting or an environment variable) gives a pure-Python build.

**For the owner or lead to decide (I took no action):**
- Install a compiler (free; the brief rules it out).
- A pure-Python PyYAML build through a build setting.
- A build constraint on setuptools.
- Wait for PyYAML cp315 wheels.
- Stay on 3.14.8 for now.

Each of these, except waiting or staying on 3.14.8, changes the approved list or the build.

**Also noticed:** 11 has no row yet for the owner's 2026-11-04 move to 3.15.2, which the brief and my `pyproject.toml` comments cite.

**Commits:** `c77f510` (pins and lock). This report is in the next commit. Nothing pushed.

### Builder addendum: PyYAML fixed, go/no-go is GO (2026-11-04)
_(builder, after the lead's decision: `PYYAML_FORCE_LIBYAML=0`, Lead (proposed), 11)_

**PyYAML:**
- Added `extra-build-variables = { pyyaml = { PYYAML_FORCE_LIBYAML = "0" } }` to `[tool.uv]`, with a comment citing 11.
- `uv lock --check` exits 0 (99 packages) and `uv.lock` is unchanged.
- **The clean build passes:** `uv sync --locked --no-cache --reinstall-package pyyaml` exits 0 (`.logs/uv-sync-py315-pyyaml-pure.log`). It built `pyyaml-6.0.3-py3-none-any.whl` with no `yaml._yaml` extension, using setuptools 84.0.0 and Cython 3.3.0 (both resolved under the date cutoff).
- `uv run python -c "import yaml; ..."` printed `3.15.2 6.0.3 False {'a': [1, 2]}`: `__with_libyaml__` is False and `safe_load` works.

**Decision rows:** the three 2026-11-04 rows (Python 3.15.2, the winrt 4.x override, the PyYAML build) are appended to [11](../11-decisions.md) exactly as the lead gave them.

**Go/no-go: GO.**
- **Import:** windows-toasts 1.3.1 imports on winrt-runtime 4.1.0 and winrt-Windows.UI.Notifications `4!10.0.28000.2957`.
- **Build a toast:** `Toast([...])` and `InteractableWindowsToaster('ShelfSync')` build, the same calls `backend/shelfsync/platform/notify.py` makes. The notifier AUMID defaults to `{1AC14E77-…}\cmd.exe`, as on winrt 3.
- **The toast tests:** `uv run pytest -m windows -k toast --no-cov -v` ran **inside Claude** through `heavy.sh` (`.logs/pytest-windows-toast-py315.log`). **3 passed** (2686 deselected):
  - `test_v29_windows_toasts_imports_on_windows_and_a_toast_can_be_made`
  - `test_the_real_adapter_shows_one_toast_without_raising`, which sends a real toast through `ToastNotifier`
  - `test_cold_toast_time_from_process_start_to_a_shown_toast`, at 4.44 s
- This isn't the result that counts (V36); the owner's `-m windows` run outside Claude is.

**New warning on winrt 4:** windows-toasts' `toasters.py:300` now raises `DeprecationWarning: ToastNotificationManager.create_toast_notifier_with_id() is deprecated, use create_toast_notifier() instead`. It's harmless today: pytest doesn't turn warnings into errors here, and Python hides `DeprecationWarning` in the app by default. It's worth a line in the new 04-A V row, because a later winrt release may remove that call.

**Commits:** `e262432` (PyYAML build switch and the 11 rows). This addendum is in the next commit. Nothing pushed. Packaging, tests, CI, cloud scripts and docs haven't been started.

## 3. Builder report

## 5. Review

## 6. Integration notes

## 7. Handover
