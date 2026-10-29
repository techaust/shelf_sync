---
name: start-session
description: Start or resume work on ShelfSync. Use when the owner says "start the day", "good morning", "continue", "resume" or "where are we".
---

0. **Catch up with GitHub first, on this PC** (a cloud session starts from a fresh clone, and its start-up script does the packages there), so the record read next is the latest one. Work merged from a cloud session reaches this PC only through here:
   - `git fetch origin`, then `git status -sb` and `git branch --show-current`.
   - On a branch whose PR has merged (or whose commits are all in `origin/main`), with nothing uncommitted: `git switch main`, then delete that local branch. On `main`: `git pull --ff-only`. With uncommitted work, or on a branch with unmerged commits: pull nothing and say so in one line.
   - **Installed packages:** `UV_PYTHON_DOWNLOADS=never uv sync --locked` (it changes nothing when the packages already match `uv.lock`). Then, for each of `frontend/` and `brand/`: if `node_modules/.shelfsync-npm-ci.sha256` is missing or `sha256sum --check --status` fails against it, run `bash tools/heavy.sh --log npm-ci-<folder> npm ci --no-audit --no-fund` in that folder, and after it passes write the stamp with `sha256sum package-lock.json > node_modules/.shelfsync-npm-ci.sha256`.
   - Say in one line what came in (commits pulled, PRs merged since this PC last looked) and what was reinstalled, or "already up to date".
1. **Read the record:**
   - `CLAUDE.md` (the rules) and the memory notes (`MEMORY.md` index)
   - `docs/10-status.md` (where things stand)
   - `docs/11-decisions.md` (never re-ask a decided question)
   - `docs/08-roadmap.md` for the current phase or milestone, its PRD IDs and exit test
   - any open `docs/runs/*.md`: on "continue", start from the newest **Handover** section
2. **Check the setup** ([docs/12](../../../docs/12-models-and-usage.md) §3, §6):
   - run `git status` (or any command) so the model-guard hook reports this conversation's effort level
   - the lead must be **Opus 5.5 at high**. If not, say so in one line ("Please pick Opus 5.5, high in the model menu") and do nothing else until it's fixed
3. **Read the usage** (load `mcp__ccd_session_mgmt__get_usage` with ToolSearch): the 5-hour %. State the day's rule in one line: at or under 95 %, new agents start (this PC: at most 2, at most 1 using a browser); over 95 %, nothing new starts until the reset ([docs/12](../../../docs/12-models-and-usage.md) §4–§5). Unreadable means one agent at a time. Read it again before every new agent. In a cloud session: if there's no usage tool, ask the owner to post the %, note it with its time in the run file, check the virtual machine's free memory and load before each agent (12 §4), and apply the cloud rules (no reading today, nothing new; a reading over 2 hours old, one agent at a time). If a weekly reading for Opus appears, tell the owner.
4. **Check the work in flight** (from M1a, once the repo exists): `git status`, `git branch --show-current`, `git worktree list`, `gh pr list --state open` (in a cloud session `gh api repos/techaust/shelf_sync/pulls`, since `gh pr` is blocked there), `gh run list --limit 3`. In a cloud session, read what `tools/cloud/session-start.sh` printed and fix any PROBLEM first. (On this PC, step 0 already pulled `main` and caught up the packages.)
5. **Load the tools for today's task** from `docs/09-tooling.md` §3, without being asked, and name them in one line.
6. **Say where things stand** in one short paragraph: done since the last session, in progress, waiting on the owner, the next item, and today's usage rule.
7. **Continue from the next item.**
   - If it touches more than one file, first present a numbered plan and wait, unless the owner has already approved it.
   - If it writes to the live stores or the S3 bucket, or changes GitHub beyond branch pushes and PR merges, ask first. Pushes and merges of finished work are automatic (CLAUDE.md, Git workflow).
   - If it waits on the owner, say exactly what they need to do (click by click), and stop.
