---
name: start-session
description: Start or resume work on ShelfSync. Use when the owner says "start the day", "good morning", "continue", "resume" or "where are we".
---

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
4. **Check the work in flight** (from M1a, once the repo exists): `git status`, `git branch --show-current`, `git worktree list`, `gh pr list --state open`, `gh run list --limit 3`. If the current branch's PR has merged and nothing is uncommitted, switch to `main`, `git pull --ff-only`, and delete that local branch.
5. **Load the tools for today's task** from `docs/09-tooling.md` §3, without being asked, and name them in one line.
6. **Say where things stand** in one short paragraph: done since the last session, in progress, waiting on the owner, the next item, and today's usage rule.
7. **Continue from the next item.**
   - If it touches more than one file, first present a numbered plan and wait, unless the owner has already approved it.
   - If it writes to the live stores, the S3 bucket or GitHub, ask first.
   - If it waits on the owner, say exactly what they need to do (click by click), and stop.
