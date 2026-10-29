# ADR 0009: Opus 5.5 at high for every task, a 95 % gate, agents by the machine's resources

- **Status:** Accepted (owner, 2026-10-29)
- **Date:** 2026-10-29
- **Replaces:** the Models, Lead and Usage parts of [ADR 0008](0008-agent-system-and-models.md) (its agent system, run files, tiers and worktrees stay)

## Context
ADR 0008 mixed three models and varied effort by tier, with the lead on Opus at medium and high only for five named key steps. The owner wants the best result on every step rather than a saving on routine ones, and wants how much runs at once to follow the machine it runs on, including cloud sessions.

## Decision
- **Models:** every task runs on Opus 5.5 at high effort: the lead, the analyst, builder, designer, reviewer, and the three helpers (`code-finder`, `test-runner`, `doc-clerk`). No Sonnet, Haiku or Fable, and no other effort level. The built-in Explore agent stays refused; `code-finder` does its job.
- **Tiers** stay, but decide only which checks a task gets: the analyst's early check for Tiers A and B; after any critical or high finding, in any tier, a second full review by a new reviewer once the fixes are in.
- **Budget gate:** new agents start while the 5-hour bar is at or under 95 %. Over 95 %, nothing new starts; running agents keep going and save their work as they go. In a cloud session, with no reading posted that day nothing new starts, and with a reading over 2 hours old only one agent runs at a time.
- **Agents at once:** every agent counts, helpers too. This PC: at most 2, at most 1 using a browser. A cloud session: another agent starts while the virtual machine has at least 3 GB free memory and its processors aren't fully loaded, up to 5, at most 2 using a browser. Heavy commands take turns in both places.
- **Enforcement:** `.claude/settings.json` (only `claude-opus-5-5`, effort `high`, every alias pointed at Opus), the `model-guard` hook and the `model-audit` script ([12 §6](../12-models-and-usage.md)).

## Consequences
- The 5-hour window fills faster, so work waits for resets more often. It costs no money on the Team plan.
- An agent started near 95 % may reach the limit mid-task; committing after each finished step keeps its work.
- Helpers started by the `code-review` and `security-review` skills pick their own model; the audit flags any that isn't Opus 5.5 at high, and the lead reports it.
- Starting a cloud session needs a pushed branch, and every push still needs the owner's yes.
