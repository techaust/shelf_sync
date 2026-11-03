---
name: cloud-sessions
description: "The owner runs ShelfSync work in cloud sessions too (env shelf_sync); Team-plan screens differ from Anthropic's docs; cloud can't read usage"
metadata:
  node_type: memory
  type: project
  originSessionId: 17c740cf-3ed1-42b4-8c6c-dee818fb6b73
  modified: 2026-11-02T08:13:18.836Z
---

Since 2026-10-29 the owner also works in Claude Code **cloud sessions**, in the `shelf_sync` environment, and may hand a day over to one ("I am continuing in the cloud session"). The first one started clean (Python 3.14.8, Node 24.19.0, uv 0.12.19 via `tools/cloud/setup.sh`).

Non-obvious facts learned setting it up:
- On the **Team plan** the screens differ from Anthropic's docs: the GitHub connector is an Owner switch (claude.ai/admin-settings/connectors), environments are made on the **Cloud environments** admin page, and network access offers **None / Limited / Full** (no "Trusted"). The owner chose Limited with seven allowed sites (runbooks/cloud-sessions.md §2.3).
- A cloud session has **no usage tool**: the owner posts the 5-hour %. A PC session can read it with `get_usage` and give the owner the number.
- `gh pr …` is blocked there (GraphQL); PRs go through `gh api`.
- **Orchestrating cloud sessions from a PC session (2026-11-02):** the app starts a cloud session only on the owner's own words in that turn, never from an automated turn (a task note or background event), and needs the app window on screen. A cloud session can't message back or wake the PC session; the lead watches its branch on GitHub (a background `git ls-remote` loop). So once the owner is away, later tasks run on the PC as agents (at most 2), not in the cloud. Screen tasks from the cloud push a branch without a PR, so the PC can do the visual check first. `list_sessions` on the PC doesn't show cloud sessions, so the owner closes them at claude.ai/code once their work merges (done for T4/T5 on 2026-11-02).

**Why:** the owner isn't a shell user and lost time when the steps didn't match the screen.
**How to apply:** give Team-plan steps first; when a PC session and a cloud session run at once, don't edit the files the cloud branch touches (`git diff --stat main...<branch>`), so the PRs don't conflict. Related: [[github-repo]], [[user-owner]], [[claude-app-msix-virtualization]].
