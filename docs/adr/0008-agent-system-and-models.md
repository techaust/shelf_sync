# ADR 0008: TecHaust's agent system, three models, a light usage check

- **Status:** Accepted (owner, 2026-10-25)
- **Date:** 2026-10-25
- **Replaces:** the "Not copied" part of [ADR 0007](0007-docs-and-workflow-like-techaust.md)

## Context
ADR 0007 left out TecHaust's multi-agent system. When planning model and effort use, the owner chose the full system after all, with the three-model set, the lead on Opus at medium (high for named key steps), and a light usage check instead of TecHaust's gate before every agent.

## Decision
- **Models:** Opus 5.5, Sonnet 5.5, Haiku 5.5 only; never Fable; effort low to high.
- **Agents:** `analyst`, `builder`, `designer`, `reviewer` (Opus/Sonnet) and `code-finder`, `test-runner`, `doc-clerk` (Haiku), with run files per task, tiers A/B/C, and worktrees from M1.
- **Lead:** Opus 5.5, medium by default; high for five named key steps ([12 §3](../12-models-and-usage.md)).
- **Usage:** read once a day (and before a Tier A builder or a designer); it limits how much runs at once, never the model or effort.
- **Enforcement:** `.claude/settings.json`, the `model-guard` hook, and the `model-audit` script.

## Consequences
- Reviews come from a fresh Opus reviewer, not from the agent that wrote the code.
- Heavy commands share a lock with techaust_platform, because both run on this 7.8 GB PC.
- Before M1 there is no git repo, so Phase 3 runs one agent at a time in the project folder.
