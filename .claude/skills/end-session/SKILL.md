---
name: end-session
description: Close the working day on ShelfSync and leave the record current. Use when the owner says "end the day", "stop for today", "wrap up" or "pause the session" (not the app's "Pause everything").
---

1. **`docs/10-status.md`:** **replace** it with the state now. Never append. Sections: Date and time (IST), Done, In progress, Next, Waits on the owner, **Not verified**, Open follow-ups.
2. **`docs/11-decisions.md`:** one row for every decision taken today, by the owner or the Lead (mark unreviewed Lead defaults "Lead (proposed)").
3. **Run files:** bring every `docs/runs/*.md` touched today up to date, with its integration notes, `Usage:` line and a **Handover** section.
4. **Models:** run `node tools/model-audit.mjs` (today's runs). Copy each agent run's model, effort and skills into its run file's `Usage:` line. Anything flagged (any run not on Opus 5.5 at high) goes into the summary.
5. **`CHANGELOG.md`** (from M1a): one line per PR merged since the last entry, newest first, as `- YYYY-MM-DD [#N](https://github.com/techaust/shelf_sync/pull/N) title`, from `gh pr list --state merged --limit 20`.
6. **Docs and links:** update any doc whose subject changed today, and check every relative link in the docs you changed.
7. **Memory:** update the memory notes if a preference or project fact changed.
8. **Commit (from M1a):** commit the docs on a `docs/…` branch, push it and open the PR without asking; it merges itself once the required checks pass (CLAUDE.md, Git workflow).
9. **Agents:** list any agent still running. Stop none without the owner's word.
10. **Tell the owner,** in a few plain lines: what was done; what was verified, and how; what wasn't verified; what waits on them; the next step; the usage now.
