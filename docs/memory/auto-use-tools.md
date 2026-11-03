---
name: auto-use-tools
description: "Load the fitting skills/plugins/MCP tools automatically per task, per docs/09-tooling.md"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 080147ab-c520-4114-88bf-e8ecd5f563c8
  modified: 2026-10-26T00:54:04.740Z
---

Use every skill, plugin and MCP tool that fits the task without being asked; the task → tool map is in ShelfSync `docs/09-tooling.md` §3 and CLAUDE.md hard rule on skills.

**Why:** owner, 2026-10-25: "note the toolset use cases also they should be used automatically according to the tasks" (same as techaust_platform rule 13).
**How to apply:** before starting a task, check the map and load the skills; say which were loaded. Using a tool never bypasses the approval rules for writes to live stores, S3 or GitHub. Installing a new plugin/MCP still needs the owner's yes. The owner also wants tools a project doesn't need turned off **for that project only** (2026-10-26: done in ShelfSync's `.claude/settings.json` with plugin toggles, MCP tool denies and skillOverrides, not by disabling account plugins, which would drop security-guidance).
