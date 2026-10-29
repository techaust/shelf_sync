# CLAUDE.md

This file provides guidance to Claude Code when working in this folder. **It holds rules only, never status or history.**

## Project
**ShelfSync** ("ShelfSync by TecHaust"): a localhost-only Windows app for one user that takes vendor ZIPs (WordPress themes and plugins), identifies the product, scans it with Windows Defender, uploads one file to S3, and updates the download on every WooCommerce store (today **GPLFamily** and **PluginWay**). It replaces **OmniSync**. No AI is needed to run it. Folder and GitHub repo: **`shelf_sync`**.

The owner starts each day with **"start the day"** and ends it with **"end the day"** (skills in `.claude/skills/`). Each step of a task (brief, review triage, integration) gets its own conversation, opened with **"continue"** and closed with a handover in its run file.

## The record (read at the start, update at the end)
- **`docs/10-status.md`:** where things stand. **Replace** it at the end of each session; never append.
- **`docs/11-decisions.md`:** one row per decision. **Never ask the owner again about a question decided there.**
- **`docs/runs/<task>.md`:** one per task given to an agent ([docs/runs/README.md](docs/runs/README.md)).
- **`CHANGELOG.md`** (from M1a): one line per merged PR, newest first.
- **Memory notes:** Claude Code's project memory (`~/.claude/projects/<this folder>/memory/`, index `MEMORY.md`) holds the owner's preferences and project facts that aren't in these docs. Update it when they change.

## Read first
- Plan: `docs/02-plan.md`. Build order and gates: `docs/08-roadmap.md`. Tools: `docs/09-tooling.md`. **Models and effort: `docs/12-models-and-usage.md`.**
- Requirements: `docs/03-prd.md` (IDs like `MAT-05` are used in tests and commits).
- Architecture `04` (with `04-architecture-appendix/A-stack-verification.md`: never state a library or platform behaviour as fact unless it's verified there), design `05`, security `06`, testing `07`, content `13`, ADRs `docs/adr/`. Background: `docs/01-audit.md`.

## Hard rules (the owner's)
1. **Never guess.** If information is missing or a decision is the owner's, stop and ask with AskUserQuestion: up to 4 questions per batch, the recommended option first and marked "(Recommended)". **Interview the owner before drafting anything big.**
2. **Approval gates:** each phase and milestone ends with a short summary and waits for "approved" ([08](docs/08-roadmap.md)). For anything touching more than one file, present a numbered plan first unless already approved.
3. **Live systems:** ask before anything that writes to the live stores, the S3 bucket, or GitHub beyond branch pushes and PR merges (repo creation or deletion, settings, branch protection, tags, releases). **Branch pushes and PR merges are automatic** once a task is done (Git workflow). Nothing writes to the live stores before M6. Read-only checks of the live stores or bucket also need the owner's go-ahead.
4. **OmniSync is read-only reference:** `D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\OmniSync`. Never modify it, never run its pipeline, ship none of its code, and never open its `config.env`. The one exception: `tools/research/*.py` import `omnisync.config` read-only (with `python -B`) to borrow store settings ([runbook](docs/runbooks/research-scripts.md)).
5. **`techaust_platform` is read-only reference** (`D:\BUSINESS\1. PARENT PROJECT\TECHAUST TECHNOLOGIES\WEBSITE\techaust_platform`): read its tokens and docs, never change it. Never read any `CREDENTIALS` folder.
6. **$0 only:** no paid tools, services or certificates. If money would remove a limitation, say so plainly as **optional**. Flag even tiny costs (like AWS request charges).
7. **Secrets:** never hardcode, commit, log or ask for them in chat. For a secret the owner must enter, give a small PowerShell script with hidden input that stores it, and ask for its result line only. Anything pasted in chat counts as exposed and is rotated.
8. **Tools are used automatically:** before each task, load every skill and tool in its row of `docs/09-tooling.md` §3, without being asked, and say which were loaded. **Never install a plugin, MCP server or package without the owner's yes.** Tools this project doesn't use are turned off for it in `.claude/settings.json` (09 §2); never turn one back on without the owner's yes.
9. **Ratings are 100 % genuine**, with reasons. Report honestly what ran, what passed and what wasn't verified.
10. **Screenshots** use the built-in browser pane on this PC (so visual checks never run in a cloud session), never headless Chrome or the Playwright MCP browser (owner's choice; Playwright MCP is blocked in settings). Full-page 2× shots go through the in-pane capture helper and its 127.0.0.1-only receiver (`docs/05-design-system-appendix/screenshots/README.md`).
11. **Models and effort** follow `docs/12-models-and-usage.md`: **every task runs on Opus 5.5 at high**, the lead and every agent, helpers included. No Sonnet, Haiku or Fable, and no other effort level. If the model or effort is wrong, say so in one line and wait.
12. **Never change Windows security settings** (Smart App Control, Defender, SmartScreen); the owner decides those.
13. Keep the record, this file and the memory notes current so work can resume across sessions.

## Working with the owner
- The owner isn't a shell user: click-by-click steps, one command per code block, full paths.
- Take routine engineering decisions yourself, state them, and record them in `docs/11-decisions.md` (who: Lead; "Lead (proposed)" until the owner has reviewed them).

## How work is split
`docs/12-models-and-usage.md` is the full plan. In short:
- **Tiers:** A (anything that can write to a store or S3, auto-apply logic, security, the ZIP reader, the updater), B (sync, catalog, jobs, tray, installer), C (screens from existing parts, docs). A tier decides only which checks a task gets, never the model or effort.
- **Order inside a task:** `builder` → Tiers A and B: `analyst` early check → `designer` → `reviewer` → fixes → after any critical or high finding, a second full review by a new reviewer; otherwise a re-check of the fix diff. All on Opus 5.5 at high.
- **Helpers:** `code-finder`, `test-runner`, `doc-clerk` (Opus 5.5 at high). Never the built-in Explore, Plan or general-purpose agents (the hook refuses them; the read-only helpers that review skills start are the observed exception, see `docs/12-models-and-usage.md` §3).
- **Budget gate:** read the 5-hour bar at the start of the day and before every new agent ([12 §5](docs/12-models-and-usage.md)). At or under 95 %, new agents start; over 95 %, nothing new starts, and running agents keep going and save their work as they go. In a cloud session: no reading posted that day, nothing new starts; a reading over 2 hours old, one agent at a time. It limits how much runs at once, never the model or effort.
- **Agents at once** (every agent counts, helpers too; [12 §4](docs/12-models-and-usage.md)): **this PC (7.8 GB RAM)** at most 2, at most 1 using a browser (the lead's browser pane counts); **a cloud session** checks the virtual machine before each start: another agent starts while it has at least 3 GB free memory and its processors aren't fully loaded, up to 5, none using a browser (visual checks stay on this PC, rule 10).
- **Cloud sessions** ([runbooks/cloud-sessions.md](docs/runbooks/cloud-sessions.md)): backend code, unit tests (Vitest included), lint, type checks, builds and docs. Never there: visual checks, the Windows checks, the release build (`packaging/`, `release.yml`, the launcher, `paths.py`), anything touching the live stores or S3. They run in the `shelf_sync` environment (Team plan: made on the Cloud environments admin page; Limited network with seven allowed sites). `tools/cloud/session-start.sh` prepares each session and prints any problem; fix a **PROBLEM** line before other work. A cloud session can't read usage: the owner posts the 5-hour % (a PC session can read it for them). When a PC session and a cloud session work at once, each leaves alone the files the other's open branch touches (check with `git diff --stat main...<branch>`), so their PRs don't conflict.
- **Heavy commands** (the security suite, builds, full lint, full test runs) take turns through `bash tools/heavy.sh --log <name> <command>`, here and in the cloud (on this PC the lock is shared with techaust_platform and other projects: when it is held or reports low memory, wait for it, never stop another project's job, and never report a partial run as done).

## Git workflow
Repo: https://github.com/techaust/shelf_sync (created 2026-10-26; **public during development**, owner's choice, [11](docs/11-decisions.md)). Anything committed is public: never commit secrets or store addresses.
- `main` is protected on GitHub while the repo is public (PR required, CI must pass, linear history, no force-push; [11](docs/11-decisions.md) 2026-10-26), and a tracked pre-push hook also refuses pushes to `main` and force-pushes.
- Work on a branch → push → PR → merge on green, **all automatic** (owner, 2026-10-29): when a task is done (the reviewer approved it, or it's a lead-only change, and the local checks below passed), the lead pushes and opens the PR without asking, and turns on the app's Auto-fix for it (if the app refuses, it tells the owner, who can turn it on in the PR bar). `.github/workflows/automerge.yml` turns on GitHub auto-merge for every PR from this repo's own branches, so GitHub squash-merges it once the required checks pass. A failed check comes back to the lead to fix. When `main` moves on first, the lead brings the branch up to date (the required checks must be up to date).
- **In a cloud session** `gh pr …` is blocked (GraphQL); open the PR with `gh api repos/techaust/shelf_sync/pulls -f title=… -f head=<branch> -f base=main -f body=…`; the workflow does the rest.
- A branch cut from another branch's pre-squash head is moved with `git rebase --onto main <old base>`, and the full checks run again before its push.
- Agents work in their own git worktrees and never push; the lead integrates.
- A finished agent's worktree can stay locked by the Claude app's process. Check `git -C <worktree> status` shows nothing uncommitted, then `git worktree remove -f -f <worktree>` and `git branch -D <its branch>`; only after its commits are integrated.
- Commit identity (repo-local): `TecHaust Technologies <admin@techaust.com>`. Conventional commits citing PRD IDs, e.g. `feat(match): edition-word penalty [MAT-05]`.

## Stack (summary; full list `docs/09-tooling.md` §7, pins in `docs/04-architecture.md` §2 at M1)
Python 3.14 (embedded, signed; [ADR 0001](docs/adr/0001-python-fastapi-sqlite-react.md)) · FastAPI + uvicorn · SQLite (`sqlite3`, WAL, numbered SQL migrations) · httpx · boto3 · keyring · cryptography · pystray · windows-toasts · React + TypeScript + Vite · Tailwind v4 from `brand/tokens.json` · Radix UI · Lucide · Archivo + IBM Plex Mono (self-hosted) · pytest, hypothesis, respx, moto · Playwright + axe · ruff, mypy, Biome · uv (locks) · NSIS · GitHub Actions.

## Commands
App (from the repo root; heavy ones through `bash tools/heavy.sh --log <name> …`). Python is **3.14.8** (`.python-version`). **Set `UV_PYTHON_DOWNLOADS=never` for every uv command**: uv must never download an interpreter (rule 8; CI and `.claude/settings.json` set it too; a cloud session gets 3.14.8 from `tools/cloud/setup.sh`, checked by SHA-256).
- `uv sync --locked`: install the locked Python packages.
- `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run pytest`, `uv run bandit -r backend`: the same checks CI runs. pip-audit as CI runs it: `uv export --locked --no-emit-project --format requirements-txt --output-file <file>`, then `uv run pip-audit --require-hashes --disable-pip -r <file>`.
- `uv run pytest -m windows --no-cov`: the Windows checks (Credential Manager, Run key, mutex, socket owner, toast; throwaway entries). Deselected by default; run before each milestone exit, and **by the owner in Windows PowerShell outside the Claude app** for the result that counts. The V31 Defender check (`-m defender`, `SHELFSYNC_RUN_V31=1`) runs only with the owner present.
- `PYTHONPATH=backend uv run pythonw -m shelfsync.launcher`: the app with its tray, as installed (one copy; a second launch opens a signed-in tab). `PYTHONPATH=backend uv run python -m shelfsync`: the server alone, no tray (development).
- **Outside the Claude app:** everything Claude starts (shells, agents, the terminal panel, even unsandboxed) runs inside the Claude app's package, which keeps a private copy of new `%LOCALAPPDATA%` and `%APPDATA%` folders that Explorer and Windows can't see ([04-A V36](docs/04-architecture-appendix/A-stack-verification.md)). So a check where Windows itself must see ShelfSync's files or registry (View logs, Start with Windows, the installer, the milestone-exit Windows checks) is run by the owner in Windows PowerShell: give the command with a `Tee-Object` to `.logs\`, then read the log. Read the real data folder from inside Claude through `\\127.0.0.1\C$\Users\<user>\AppData\Local\ShelfSync`. Agents use a throwaway `SHELFSYNC_DATA_DIR`.
- Screens (in `frontend/`): `npm ci`, `npm run lint`, `npm run typecheck`, `npm test` (Vitest), `npm run build` (writes `frontend/dist/`, which the server serves), `npm run schema:check`. Playwright + axe (`npm run e2e`) run in CI only: no test browser is downloaded to this PC.
- **Release build (the same script `release.yml` runs):** after `npm run build`, `bash tools/heavy.sh --log release-build powershell -NoProfile -ExecutionPolicy Bypass -File packaging/release-build.ps1 -Python <Python 3.14.8's python.exe> -Makensis "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\tools\nsis-3.13\makensis.exe" -Work C:\Users\<user>\AppData\Local\Temp\ssrb<n> -Suffix -rehearsal` (a new, empty, short folder: at most 60 characters, or the installer test's nested paths pass Windows' 260-character limit). It builds, smoke-tests, compiles, installer-tests and writes the manifest, and never touches the real install names or Credential Manager service. **Run it and see it pass before any push that touches `packaging/`, `release.yml`, `paths.py`, the launcher or anything the build ships**, so GitHub only re-runs what already passed here. Before a push that touches Python, also run `uv run mypy --platform linux`: CI runs on Linux, and Windows-only names fail only there.

Other tools:
- `node tools/model-audit.mjs [YYYY-MM-DD]`: every run since that date (default today), with models, effort and skills; it flags anything outside the plan.
- Brand (in `brand/`, through `bash tools/heavy.sh --log <name> …`): `npm run build` rebuilds every logo, icon and image; `npm test` (vitest) also fails on any hand edit.
- Plan page: `python -I docs/02-plan-appendix/build_plan_page.py <out.html>`, then publish to https://claude.ai/artifact/9CYLJk6kRPncuJ3Lmunn5f. **Republish it after every change to 02.**
- Mockup artifact: `python -I docs/05-design-system-appendix/screenshots/capture/build_artifact.py docs/05-design-system-appendix/mockup <out.html>`, then publish to https://claude.ai/artifact/Gzzm2Mztikj8xqL49UoiRj. It's a desktop layout that shrinks to fit on phones.

## Conventions
- **Docs:** Markdown in `docs/`; HTML mockups, images and the small scripts that build them only in `docs/NN-name-appendix/` folders.
- **Screen wording:** [13](docs/13-content.md); until M1 moves it into the app, the approved mockup holds the full screen text (13 §6).
- **Phones:** the app is desktop-only (05 §6), but any page published for the owner must read well on a phone.
- **Time:** store UTC (ISO 8601); show Windows local time with the zone name; schedules in local time.
- **Screen code layers:** `api/` → `lib/` → `components/` → `app/` and `screens/`; `components/`, `lib/` and `api/` never import from `screens/`. A lazy part (`React.lazy`) sits in a `Suspense` inside a `ChunkBoundary` (a test refuses any other); a write that needs a decision gets a pure, tested `plan…()` function rather than logic inside the component.
- **Design:** tokens only, never hand-typed colours; store colours only as identifiers ([05](docs/05-design-system.md)); wording from [13](docs/13-content.md).
- **Security:** deny by default; no secrets in logs, URLs (except the single-use, 60-second `#t=` sign-in ticket; the install token itself never goes in a URL) or the browser.
- **Supply chain:** exact pins with hashes (uv, `package-lock.json`); GitHub Actions pinned by commit SHA; new packages only with the owner's yes.
- File names, slugs and hashes are shown in IBM Plex Mono; versions, counts and times use tabular numbers.
