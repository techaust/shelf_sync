# ADR 0007: Documentation and working rules follow techaust_platform

- **Status:** Accepted (owner, 2026-10-25). Its "Not copied" part is **replaced by [ADR 0008](0008-agent-system-and-models.md)** (the agent system and model plan are now copied)
- **Date:** 2026-10-25

## Context
The owner asked for ShelfSync's docs to be rebuilt in categories, as in `techaust_platform`, and for tools to be used automatically per task.

## Decision
- **Docs:** numbered `docs/NN-name.md` in Markdown; supporting material in `docs/NN-name-appendix/` (which may also hold HTML mockups and images, e.g. `05-design-system-appendix/`); ADRs in `docs/adr/`; procedures in `docs/runbooks/`; task run files in `docs/runs/`. Only `README.md`, `CLAUDE.md` and (from M1) `CHANGELOG.md` sit in the root.
- **TecHaust's document types copied:** audit with evidence appendices, plan, PRD, architecture with a stack-verification appendix, design system, a brand audit (created at P3.2), security, testing, roadmap, tooling, status, decisions, models and usage, and content (wording; TecHaust's 07, ShelfSync's 13).
- **The record:** [10-status](../10-status.md) is replaced each session; [11-decisions](../11-decisions.md) gets one row per decision; neither is re-asked.
- **Rules:** `CLAUDE.md` holds rules only; the task → tool map in [09 §3](../09-tooling.md) is followed automatically.
- **Sessions:** project skills `start-session` ("start the day") and `end-session` ("end the day").
- ~~**Not copied:** the agent system, run files, tiers, budget gate and model hook.~~ Replaced by ADR 0008.

## Consequences
- Work can resume across sessions from the record alone.
