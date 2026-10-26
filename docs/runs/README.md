# Run files

Each task given to a `builder` or `designer` gets one file, `docs/runs/<task>.md` (for example `p3.1-logo-concepts.md`, `m4-match-scoring.md`), that starts with three header lines:
- `Status: open | merged (PR #N) | abandoned`
- `Tier: A | B | C` ([12 §2](../12-models-and-usage.md))
- `Usage:` one entry per agent run: the agent, model and effort (copied from `node tools/model-audit.mjs`, not from what was intended), the skills it loaded, then the 5-hour percentage at its start and end, e.g. `builder claude-sonnet-5-5/high [aws-sdk-python-usage]: 5-h 3 → 38 %`

Then these sections:

1. **Brief**, written by the lead before any agent starts (drafted by the `analyst` for Tier A):
   - the PRD IDs ([03](../03-prd.md))
   - the files involved, split by layer: backend for the `builder`, screens and brand for the `designer`
   - the skills to load ([09 §3](../09-tooling.md))
   - what "done" means (the tests and checks that prove it)
   - what's out of scope, and what another task owns
2. **Early check** (Tier A only): the builder's report once the schema, migrations, core logic and API routes are committed, then the analyst's GO or CHANGE.
3. **Builder report**, by the builder: files changed, commands run and their results, anything not verified, open questions.
4. **Designer report**, by the designer: the same, plus the screenshot paths, any placeholder or sample data, and confirmation that `frontend-design` was loaded first.
5. **Review**, the reviewer's reply (APPROVE or SEND BACK, each finding with its severity, and the visual review when there are screens), copied in by the lead.
6. **Integration notes**, by the lead: how it was merged, the full-check results, follow-ups.
7. **Handover**, by the lead at the end of each conversation: where the task stands and the next step. The next conversation ("continue") starts here.
