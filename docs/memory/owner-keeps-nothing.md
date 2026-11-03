---
name: owner-keeps-nothing
description: The owner keeps no backups of their own; everything needed to resume must be on GitHub or claude.ai
metadata:
  node_type: memory
  type: feedback
  originSessionId: fe98bbd1-9ff2-4a01-a8cf-8b79b7dcd27c
  modified: 2026-11-03T13:15:26.373Z
---

On 2026-11-03, planning to format the PC, the owner said: "I will not keep anything myself. You can save them on the project github somewhere so i don't need to do anything. i am doing a fresh start." They let OmniSync go (it was never on GitHub) rather than make a private repo for it; after the format (2026-11-04) they put its folder back anyway, under a new folder layout, without its venv or keys.

**Why:** the owner wants to be able to wipe the PC at any time and carry on from GitHub alone, with no USB drives or copies to look after.

**How to apply:** keep everything a new PC needs in the repo: the record, the memory notes (`docs/memory/`, synced by `tools/memory-sync.sh` in "start the day" and "end the day"), and the setup steps (`docs/runbooks/fresh-start.md`). Secrets can never go there (the repo is public), so plan for keys to be made again rather than restored. **Open conflict:** `docs/runbooks/release.md` A has the owner keep the release signing key plus an offline copy. Raise this with the owner before that key is made (none existed on 2026-11-03). Related: [[user-owner]], [[github-repo]].
