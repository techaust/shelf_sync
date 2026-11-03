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

## 3. Builder report

## 5. Review

## 6. Integration notes

## 7. Handover
