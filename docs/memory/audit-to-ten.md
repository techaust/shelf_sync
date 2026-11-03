---
name: audit-to-ten
description: "When the owner asks for an audit \"to 10/10\", rate every file on every aspect, fix everything, and loop independent reviewer re-checks until approve"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 8f80a177-4da1-4f07-9bc0-9f594a69f66d
  modified: 2026-10-25T18:02:28.165Z
---

When the owner asks to "audit everything, rate it out of 10 and make it 10/10", they mean: score every file on every aspect (accuracy, consistency, completeness, clarity, actionability, TecHaust fidelity, honesty, security, code), fix every finding, then have the `reviewer` agent re-check independently, and repeat until it approves. On 2026-10-25 they asked twice more after approvals ("do everything to make you and me happy", "recheck 10/10"), so they value one more re-check over stopping early.

**Why:** they want scores they can trust (CLAUDE.md rule 9). An honest list of what can't reach 10 yet, with what unlocks each, satisfied them.

**How to apply:** report a scores table, then the fix plan; gather the owner's answers and read-only evidence (with go-ahead) to close gaps; after each round, say whether the last fixes were re-reviewed. Never round up. Related: [[user-owner]].
