# 12: Models, effort and usage

| | |
|---|---|
| **Phase** | 2, Project documentation (**approved by the owner 2026-10-25**) |
| **Date** | 2026-10-25 |
| **Decisions** | Owner, 2026-10-25: three models only; the lead on Opus medium, high for named key steps; TecHaust's full agent system; a light budget check ([11](11-decisions.md), [ADR 0008](adr/0008-agent-system-and-models.md)) |
| **Model** | TecHaust's `docs/14-models-and-usage.md` (read-only reference), adapted to a Python + React app on this PC |

Which Claude model and effort each kind of work runs on, how the project is held to that, the usage check, and how it is measured.

**The account:** a Claude **Team** plan (premium seat, owner, 2026-10-26; before that, Max). The session usage tool on 2026-10-26 shows a **5-hour limit** and a **weekly limit for Fable** only (Fable is never used here); it shows no weekly limit for Opus, Sonnet or Haiku, and extra usage is off. If that changes, the owner says so and §5 is updated.

## 1. Principles
- **Three models only:** Opus 5.5 (`claude-opus-5-5`), Sonnet 5.5 (`claude-sonnet-5-5`), Haiku 5.5 (`claude-haiku-5-5`). Settings and a hook enforce it (§6). **Never:** Fable (any version, or the `fable` / `best` aliases), effort `xhigh` or `max`.
- **Opus where judgement or taste decides the result:** the lead, the hard thinking, every screen and brand asset, every review, and the matching and apply logic that can change a live store. **Sonnet** builds routine code. **Haiku** does mechanical work.
- **Quality is never cut to save usage.** Effort levels in §3 don't change with usage; when usage runs high, work slows down instead (§5).
- **Before any agent starts, the lead loads the skills for its task** and the agent loads them again itself ([09 §3](09-tooling.md)).

## 2. Tiers
The lead sets each task's tier in its brief ([runs/README.md](runs/README.md)). A milestone's tier comes from its riskiest part.

| Tier | What puts a task in it | Where in the roadmap ([08](08-roadmap.md)) |
|---|---|---|
| **A** | The security-relevant Windows adapters in `platform/` (Credential Manager, the Defender scan runner); anything that can write to a live store or S3 (`apply/`: plans, writes, read-back, retry, rollback, restore, retention deletes); anything that can make a job auto-apply (`match/`: scoring, bands, guards, cut-offs, calibration); security (`secure/`: token, Host/Origin, Credential Manager, backup crypto, redaction); the safe ZIP reader; the updater's signature check | M1a security base (`secure/`: token, ticket, session, Host/Origin/CSRF, CSP, log redaction), M1b updater signature check, M2 Credential Manager and backup crypto, M4, M5 writes, M6 |
| **B** | Catalog linking, incremental sync, slots, Cleanup detection, snapshots, the job queue and worker, SSE, tray, launcher, installer, notifications, settings storage, the test stack | M1a and M1b (rest), M2 (rest), M3, M5 Review flow |
| **C** | Screens and components built from existing parts, CSV export, runbooks, user guide | M7, parts of M3 and M5 screens |
| **None** (the lead directly) | Docs, one-file fixes, merges, the budget check, owner-facing summaries | — |

Brand and screen design (Phase 3, and the first build of each screen) are treated as **A for effort** (designer at high), whatever the code tier.

## 3. Who runs what

### The lead (the conversation that talks to the owner)
- **Opus 5.5 at medium** by default, for every routine step: starting the day, briefs for Tiers B and C, integration, PRs, owner summaries, ending the day. The project's `effortLevel` is `medium`.
- **High for these key steps only.** The lead asks the owner to switch to **Opus 5.5, high** in the model menu at the start of the step, and back to medium when it's done:
  1. writing the **final Tier A brief** from the analyst's draft
  2. **triaging a Tier A review** (fix, follow-up or keep, with reasons)
  3. deciding the **calibration cut-offs** from the M4 report before they ship
  4. the **live canary** in M6, every step
  5. choosing between the three **logo concepts** for the owner and writing the refinement brief (P3.1–P3.2)
- A hook tells the lead its effort on its first command and whenever it changes (§6). If the model isn't Opus 5.5, or the effort isn't the one the step needs, the lead says so in one line and waits.

### Agents (`.claude/agents/`)
The lead passes `model` and `effort` when it starts an agent; the agent files hold the defaults.

| Work | Agent, model | Tier A | Tier B | Tier C |
|---|---|---|---|---|
| Hard thinking: Tier A brief drafts, the early check of a Tier A build, risky migration merges, failures nobody can explain, phase plans, the calibration analysis | `analyst`, Opus | high | high | — |
| Backend code and tests: `inspect/`, `match/`, `apply/`, `catalog/`, `jobs/`, `db/`, `secure/`, `update/`, `platform/`, `tray/`, packaging | `builder`, Sonnet | high | medium | medium |
| Brand assets, mockups, screens, components (designed and built) | `designer`, Opus | high | high | high |
| Finish the checks after a stop | the same agent | medium | medium | medium |
| Fix findings in backend code | `builder`, Sonnet | medium (high if any finding is critical) | medium | low |
| Fix findings in screens | `designer`, Opus | medium | medium | medium |
| Review: code, plus a visual review when there are screens | `reviewer`, Opus | high | high | high |
| Re-check the fix diff only | `reviewer`, Opus | medium | medium | medium |

### Haiku agents
They skip CLAUDE.md (`omitClaudeMd: true`), so each file repeats the rules that apply to it. They never touch `inspect/`, `match/`, `apply/`, `secure/`, `update/`, `platform/`, migrations, screens or reviews.

| Agent | Effort | Job |
|---|---|---|
| `code-finder` | low | "Where is X" (read-only), in place of the built-in Explore, Plan and general-purpose agents |
| `test-runner` | low | Runs one suite through `tools/heavy.sh --log` and reports only the failures |
| `doc-clerk` | medium | CHANGELOG lines, status tables, relative-link fixes; the lead checks the diff |

### Built-in agents
- `claude-code-guide` (Haiku): only for questions about Claude Code itself.
- Explore, Plan, general-purpose, `claude`: **never** started by the lead or an agent (the hook refuses them). **Exception:** the read-only helpers that the `code-review` and `security-review` skills start on their own, on Opus or Sonnet 5.5; anything other than reading that they do is discarded. Observed on 2026-10-25: `code-review`'s general-purpose helper ran inside the reviewer and the hook didn't refuse it, while the same hook refused the lead's own live Explore and untyped Agent calls. Why the helper wasn't refused isn't verified; `model-audit` lists such runs with a note so they stay visible.

## 4. How a task runs
1. **Brief** in `docs/runs/<task>.md` (Tier A: the analyst drafts it, the lead writes the final one at high).
2. `builder`: data, logic, API, with tests, in its own git worktree.
3. Tier A: the `analyst`'s **early check** of that diff (GO or CHANGE).
4. `designer`: the screens on top, with its own visual check.
5. `reviewer`: code + visual review → APPROVE or SEND BACK.
6. Fixes (backend to the builder, screens to the designer), then the re-check.
7. The lead integrates, runs the full checks, opens the PR (after the owner's yes for the first push), and fills in the run file.

A task with only screens skips 2–3; a task with no screens skips 4.

**Before the repo exists (Phase 3):** there are no worktrees. The designer works in the project folder on `brand/` and `docs/05-design-system-appendix/` only, one agent at a time, and nothing is committed until M1 creates the repo.

**Screenshots:** the owner declined headless Chrome. The designer and reviewer use the built-in browser tools if they're available inside an agent; if not, they prepare the pages and **the lead takes the screenshots in the built-in browser pane**. The Playwright MCP browser is blocked in this project's settings because it may run headless; using it would need the owner's yes and the block lifted. Whether the built-in browser works inside an agent is checked at P3.0 ([08](08-roadmap.md)), before any design work.

**Limits on this PC (7.8 GB RAM):** at most **two agents at once**, never two that use a browser, and heavy commands one at a time through `tools/heavy.sh` (§7). The heavy-command lock is **shared with techaust_platform**, so the two projects never run heavy commands at the same moment.

## 5. The usage check (light)
At the start of each day the lead reads the usage (the `get_usage` session tool: "5-hour limit") and states the day's rule in one line.

| Reading | What runs |
|---|---|
| 5-hour window under 80 % | Up to two agents at once (never two browser users) |
| 5-hour window at 80 % or more | No new agent or step starts until it resets; only finishing what is in flight |
| Usage can't be read | One agent at a time, and said |

The Team plan shows no weekly limit for the models used here, so there is no weekly rule. If the tool shows a weekly reading for them again, the lead tells the owner and §5 is revisited.

The check changes **how much runs at once, never the model or the effort.** It's read once a day and again only when the lead is about to start a Tier A builder or a designer.

## 6. Keeping to the plan

| Lock | What it does |
|---|---|
| `.claude/settings.json` → `env` | Pins `opus` → `claude-opus-5-5`, `sonnet` → `claude-sonnet-5-5`, `haiku` → `claude-haiku-5-5` |
| `.claude/settings.json` → `availableModels` | Allows only those three IDs |
| `.claude/settings.json` → `effortLevel` | `medium` (the lead's default) |
| `.claude/settings.json` → `permissions.deny` | Blocks file reads (Read, Grep, Glob) of OmniSync's `config.env`, any `CREDENTIALS` folder (inside or outside the project) and `.env` files, for the lead and every agent (owner, 2026-10-25; tested with probe files). Shell commands aren't covered by these rules, so CLAUDE.md rules 4–5 still apply to them. It also blocks the tools of MCP servers this project doesn't use ([09 §2](09-tooling.md)) |
| `.claude/settings.json` → `enabledPlugins`, `skillOverrides` | Turn off, for this project only, the plugins and skills it doesn't use ([09 §2](09-tooling.md); owner, 2026-10-26) |
| Agent files | Each names its exact model ID and default effort |
| `tools/model-guard.mjs` (`PreToolUse` hook on Agent and Bash) | Refuses an agent on another model, at `xhigh`/`max`, or of a built-in Explore, Plan, general-purpose or `claude` type (a call with no type counts as general-purpose); tells the lead its effort on its first command and whenever it changes |
| `node tools/model-audit.mjs [date]` | Lists every run since the date with its real model, effort and loaded skills; flags anything outside this plan. Run at the end of each day |

- `CLAUDE_CODE_EFFORT_LEVEL` stays unset (it would override every agent's effort).
- A new Anthropic model is a question for the owner; nothing changes until a [11](11-decisions.md) row records it.
- **Tested when:** the settings and hook are checked on the first day they're active (an agent asked for Fable must be refused; the lead must be told its effort). Until that check, they're marked "not yet verified" in [10](10-status.md).

## 7. Habits that save usage without touching quality
- Each agent's tools are a fixed list (in its file); none gets the AWS, GitHub or other connectors.
- Long output goes to a log: `bash tools/heavy.sh --log <name> <command>` writes `.logs/<name>.log` (git-ignored) and prints the exit code and the last 40 lines. Agents grep the log; they never read all of it.
- The reviewer reads the diff and opens a whole file only where the diff points.
- **One lead conversation per step** of a task (brief, review triage, integration), closed with a handover in the run file; the owner opens the next with "continue". The prompt cache lasts about an hour, so an idle conversation costs more to resume.
- No progress check-ins while agents run; the lead waits for the completion notice.

## 8. Measuring
- Each run file's `Usage:` line records every agent run: agent, model and effort (copied from `node tools/model-audit.mjs`, not from what was intended), the skills it loaded, and the 5-hour percentage at its start and end.
- The end-of-day routine runs the audit; anything flagged goes into the owner's summary.
- **Quality guard:** if a Tier B or C task gets a critical finding, or is sent back twice, that tier's builder or designer fix effort goes up one step for the next task (at most high), recorded as a [11](11-decisions.md) row.
- **Cost report:** after the first Tier A build (M2) and the first designer task (Phase 3), the lead reports what each kind of run cost in 5-hour percentage points. Effort levels change only with the owner's approval, and never downwards for Tier A, screens or reviews.
