---
name: weekly-budget
description: "The Team plan's weekly limit, not the 5-hour bar, is what runs out on M3-size Tier B tasks; plan new agents around its reset"
metadata:
  node_type: memory
  type: project
  originSessionId: a90202f3-d96a-485e-963d-b29e931c5d2b
  modified: 2026-11-18T09:31:23.135Z
---

On 2026-11-17/18 three Tier B tasks with the full chain (builder, analyst, reviewer, second reviewer, re-checks) took the weekly "all models" reading from 77 % to 95 % in about 22 hours, while the 5-hour bar never passed 56 %. Each such task costs roughly 5–8 % of the week; fix rounds after reviews are a large share.

**Why:** 12 §5's gate reads only the 5-hour bar, so the weekly limit can run out with no warning from the gate, and then nothing can start until the weekly reset (Thursday about 12:30 IST in Nov 2026).

**How to apply:** read the weekly figure with the 5-hour one before every new agent ([[auto-use-tools]] covers the per-task tool loading); past about 90 %, finish the task in flight and start nothing new; tell the owner when the weekly figure, not the 5-hour bar, is the constraint. Related: [[user-owner]].
