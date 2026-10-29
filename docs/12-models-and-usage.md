# 12: Models, effort and usage

| | |
|---|---|
| **Phase** | 2, Project documentation (approved by the owner 2026-10-25; **revised and approved 2026-10-29**) |
| **Date** | 2026-10-29 |
| **Decisions** | Owner, 2026-10-29: one model and one effort, Opus 5.5 at high, for every task; tiers decide only the checks; a 95 % budget gate; agents at once set by the machine's resources ([11](11-decisions.md), [ADR 0009](adr/0009-opus-high-for-every-task.md), which replaces the model and usage parts of [ADR 0008](adr/0008-agent-system-and-models.md)) |
| **Model** | TecHaust's `docs/14-models-and-usage.md` (read-only reference), adapted to a Python + React app on this PC |

Which Claude model and effort each kind of work runs on, how the project is held to that, the budget gate, how many agents run at once, and how it is measured.

**The account:** a Claude **Team** plan (premium seat, owner, 2026-10-26; before that, Max). The session usage tool on 2026-10-26 shows a **5-hour limit** and a **weekly limit for Fable** only (Fable is never used here); it shows no weekly limit for Opus, and extra usage is off. If that changes, the owner says so and §5 is updated.

## 1. Principles
- **One model, one effort:** every task runs on **Opus 5.5** (`claude-opus-5-5`) at **high** effort: the lead, the analyst, the builder, the designer, the reviewer, and the three helpers (`code-finder`, `test-runner`, `doc-clerk`). **Never:** Sonnet, Haiku or Fable (any version, or the `sonnet`, `haiku`, `fable` and `best` aliases), and no effort other than `high`. Settings and a hook enforce it (§6).
- **Quality is never cut to save usage.** When usage runs high, work waits (§5); the model and effort never change.
- **Before any agent starts, the lead loads the skills for its task** and the agent loads them again itself ([09 §3](09-tooling.md)).
- Opus at high on every step fills the 5-hour window faster than a mixed plan; that costs time (waiting for resets), never money.

## 2. Tiers
The lead sets each task's tier in its brief ([runs/README.md](runs/README.md)). A milestone's tier comes from its riskiest part. **A tier now decides only which checks a task gets** (§4), never the model or effort.

| Tier | What puts a task in it | Where in the roadmap ([08](08-roadmap.md)) |
|---|---|---|
| **A** | The security-relevant Windows adapters in `platform/` (Credential Manager, the Defender scan runner); anything that can write to a live store or S3 (`apply/`: plans, writes, read-back, retry, rollback, restore, retention deletes); anything that can make a job auto-apply (`match/`: scoring, bands, guards, cut-offs, calibration); security (`secure/`: token, Host/Origin, Credential Manager, backup crypto, redaction); the safe ZIP reader; the updater's signature check | M1a security base (`secure/`: token, ticket, session, Host/Origin/CSRF, CSP, log redaction; the Credential Manager adapter for the install token), M1b updater signature check, M2 store and S3 secrets in Credential Manager and backup crypto, M4, M5 writes, M6 |
| **B** | Catalog linking, incremental sync, slots, Cleanup detection, snapshots, the job queue and worker, SSE, tray, launcher, installer, notifications, settings storage, the test stack | M1a and M1b (rest), M2 (rest), M3, M5 Review flow |
| **C** | Screens and components built from existing parts, CSV export, runbooks, user guide | M7, parts of M3 and M5 screens |
| **None** (the lead directly) | Docs, one-file fixes, merges, the budget check, owner-facing summaries | — |

| Check | Tier A | Tier B | Tier C |
|---|---|---|---|
| `analyst` brief draft (the lead writes the final brief) | yes | — | — |
| `analyst` early check of the build (GO or CHANGE) | yes | yes | — |
| `security-review` by the reviewer (also for anything in `secure/`, `inspect/`, `apply/`, `update/`, `platform/`, the API middleware or the installer, whatever the tier) | yes | — | — |
| `reviewer` full review | yes | yes | yes |
| **Second review** after any critical or high finding: once the fixes are in, a new reviewer goes over the whole task again, not only the fixes | yes | yes | yes |
| Re-check of the fix diff only, when the findings were medium or low | yes | yes | yes |

## 3. Who runs what
Every row runs on **Opus 5.5 at high**. The lead passes `model: "opus"` and `effort: "high"` when it starts an agent; the agent files hold the same values.

### The lead (the conversation that talks to the owner)
- Every step: starting the day, briefs, review triage, integration, PRs, owner summaries, ending the day. The project's `effortLevel` is `high`.
- A hook tells the lead its effort on its first command and whenever it changes (§6). If the model isn't Opus 5.5 or the effort isn't high, the lead says so in one line ("Please pick Opus 5.5, high in the model menu") and waits.

### Agents (`.claude/agents/`)

| Agent | Work |
|---|---|
| `analyst` | Hard thinking: Tier A brief drafts, the early check of a Tier A or B build, risky migration merges, failures nobody can explain, phase plans, the calibration analysis. Read-only |
| `builder` | Backend code and tests: `inspect/`, `match/`, `apply/`, `catalog/`, `jobs/`, `db/`, `secure/`, `update/`, `platform/`, `tray/`, packaging; and fixes to its own findings |
| `designer` | Brand assets, mockups, screens, components (designed and built); and fixes to screen findings |
| `reviewer` | Code review, plus a visual review when there are screens; the second review; the re-check of a fix diff |
| `code-finder` | "Where is X" (read-only), in place of the built-in Explore, Plan and general-purpose agents |
| `test-runner` | Runs one suite through `tools/heavy.sh --log` and reports only the failures |
| `doc-clerk` | CHANGELOG lines, status tables, relative-link fixes; the lead checks the diff |

The three helpers read CLAUDE.md like every other agent. They never touch `inspect/`, `match/`, `apply/`, `secure/`, `update/`, `platform/`, migrations, screens or reviews.

**Saving work as it goes:** the `builder` and `designer` commit in their own worktree after each finished step, so an agent that runs into the 5-hour limit, or is stopped, loses nothing. The lead squashes the commits when it integrates.

### Built-in agents
- `claude-code-guide`: only for questions about Claude Code itself, and only started with `model: "opus"` (its own default is not Opus; the hook refuses it otherwise).
- Explore, Plan, general-purpose, `claude`: **never** started by the lead or an agent (the hook refuses them). **Exception:** the read-only helpers that the `code-review` and `security-review` skills start on their own; anything other than reading that they do is discarded. Their model is chosen by the skill, not by this project (the earlier plan recorded them on Opus or Sonnet 5.5), so `model-audit` **flags** any that isn't Opus 5.5 at high, and the lead reports it to the owner. Observed on 2026-10-25: `code-review`'s general-purpose helper ran inside the reviewer and the hook didn't refuse it, while the same hook refused the lead's own live Explore and untyped Agent calls. Why the helper wasn't refused isn't verified.

## 4. How a task runs
1. **Brief** in `docs/runs/<task>.md` (Tier A: the analyst drafts it, the lead writes the final one).
2. `builder`: data, logic, API, with tests, in its own git worktree.
3. Tiers A and B: the `analyst`'s **early check** of that diff (GO or CHANGE).
4. `designer`: the screens on top, with its own visual check.
5. `reviewer`: code + visual review → APPROVE or SEND BACK.
6. Fixes (backend to the builder, screens to the designer). After any critical or high finding: the **second review** of the whole task by a new reviewer. After only medium or low findings: the re-check of the fix diff.
7. The lead integrates, runs the full checks, opens the PR (after the owner's yes for the push), and fills in the run file.

A task with only screens skips 2–3; a task with no screens skips 4.

**Before the repo exists (Phase 3):** there are no worktrees. The designer works in the project folder on `brand/` and `docs/05-design-system-appendix/` only, one agent at a time, and nothing is committed until M1 creates the repo.

**Screenshots:** the owner declined headless Chrome. The designer and reviewer use the built-in browser tools if they're available inside an agent; if not, they prepare the pages and **the lead takes the screenshots in the built-in browser pane**. The Playwright MCP browser is blocked in this project's settings because it may run headless; using it would need the owner's yes and the block lifted.

### Agents at once
**Every agent counts**, the helpers too. The lead itself isn't counted, but the lead using the browser pane takes the one browser place on this PC.

| Where | Limit |
|---|---|
| **This PC** (7.8 GB RAM, 2 cores / 4 threads) | At most **2 agents**, and at most **1** of them using a browser. When `tools/heavy.sh` reports low memory, the next agent waits |
| **A cloud session** | Before each start, the lead checks the virtual machine (`free -m` and `nproc`, plus the 1-minute load average from `/proc/loadavg`). Another agent starts only while there are **at least 3 GB of free memory** and the processors **aren't fully loaded** (the 1-minute load average is below the number of processors), up to **5 agents**, with at most **2** using a browser. The lead states the readings in one line |

**Heavy commands** (the security suite, builds, full lint, full test runs) take turns through `bash tools/heavy.sh --log <name> <command>`, on this PC and in a cloud session. On this PC the lock is **shared with techaust_platform** and other projects: when it is held or reports low memory, the work waits; another project's job is never stopped, and a partial run is never reported as done.

A cloud session starts from a branch pushed to GitHub; that push needs the owner's yes, like every push.

## 5. The budget gate
The lead reads the 5-hour bar (the `get_usage` session tool: "5-hour limit") at the start of each day and again **before every new agent starts**.

| Reading | What runs |
|---|---|
| **At or under 95 %** | New agents start, within the limits in §4 |
| **Over 95 %** | Nothing new starts until the window resets. Agents already running keep going and save their work as they go (§3) |

**In a cloud session:** the session reads the usage tool if it has one; if not, the owner types the 5-hour % in that session's chat. The lead writes each reading and its time in the run file.
- With **no reading posted that day**, nothing new starts.
- With a reading **over 2 hours old**, only one agent runs at a time.

**On this PC:** if the usage can't be read, only one agent runs at a time, and the lead says so.

The Team plan shows no weekly limit for Opus, so there is no weekly rule. If the tool shows a weekly reading for it, the lead tells the owner and §5 is revisited. The gate changes **how much runs at once, never the model or the effort.**

## 6. Keeping to the plan

| Lock | What it does |
|---|---|
| `.claude/settings.json` → `env` | Points the `opus`, `sonnet` and `haiku` names all at `claude-opus-5-5`, so an alias can't reach another model |
| `.claude/settings.json` → `availableModels` | Allows only `claude-opus-5-5` |
| `.claude/settings.json` → `effortLevel` | `high` |
| `.claude/settings.json` → `permissions.deny` | Blocks file reads (Read, Grep, Glob) of OmniSync's `config.env`, any `CREDENTIALS` folder (inside or outside the project) and `.env` files, for the lead and every agent (owner, 2026-10-25; tested with probe files). Shell commands aren't covered by these rules, so CLAUDE.md rules 4–5 still apply to them. It also blocks the tools of MCP servers this project doesn't use ([09 §2](09-tooling.md)) |
| `.claude/settings.json` → `enabledPlugins`, `skillOverrides` | Turn off, for this project only, the plugins and skills it doesn't use ([09 §2](09-tooling.md); owner, 2026-10-26) |
| Agent files | Each names `claude-opus-5-5` and effort `high` |
| `tools/model-guard.mjs` (`PreToolUse` hook on Agent and Bash) | Refuses an agent on any model but Opus 5.5, at any effort but high, of a built-in Explore, Plan, general-purpose or `claude` type (a call with no type counts as general-purpose), or `claude-code-guide` without `model: "opus"`; tells the lead its effort on its first command and whenever it changes |
| `node tools/model-audit.mjs [date]` | Lists every run since the date with its real model, effort and loaded skills; flags any run, lead or agent, that isn't Opus 5.5 at high. Run at the end of each day |

- `CLAUDE_CODE_EFFORT_LEVEL` stays unset (it would override every agent's effort).
- A new Anthropic model is a question for the owner; nothing changes until a [11](11-decisions.md) row records it.
- **Tested when:** the guard is tested with sample inputs when it changes (an agent asked for Sonnet, Haiku, Fable or medium must be refused; Opus at high must pass). Whether the `env` aliases and `availableModels` behave as described is checked on the first day they're active; until then they're marked "not yet verified" in [10](10-status.md).

## 7. Habits that save usage without touching quality
- Each agent's tools are a fixed list (in its file); none gets the AWS, GitHub or other connectors.
- Long output goes to a log: `bash tools/heavy.sh --log <name> <command>` writes `.logs/<name>.log` (git-ignored) and prints the exit code and the last 40 lines. Agents grep the log; they never read all of it.
- The reviewer reads the diff and opens a whole file only where the diff points (the second review reads the whole task's diff again).
- **One lead conversation per step** of a task (brief, review triage, integration), closed with a handover in the run file; the owner opens the next with "continue". The prompt cache lasts about an hour, so an idle conversation costs more to resume.
- No progress check-ins while agents run; the lead waits for the completion notice.

## 8. Measuring
- Each run file's `Usage:` line records every agent run: agent, model and effort (copied from `node tools/model-audit.mjs`, not from what was intended), the skills it loaded, and the 5-hour percentage at its start and end.
- The end-of-day routine runs the audit; anything flagged goes into the owner's summary.
