---
name: prove-locally-before-push
description: The owner is frustrated by CI round trips; prove everything CI will run on this PC before asking to push
metadata:
  node_type: memory
  type: feedback
  originSessionId: 4bece7eb-6e53-4685-8214-544d2391e9d7
  modified: 2026-10-27T19:42:44.027Z
---

On 2026-10-28, after four GitHub-only failures in a row on the M1b PRs (a Windows-only import and a Windows-only lock in a test that broke on Linux, a form feed my Python-string edit put into release.yml, and an NSIS icon path that only broke with a relative script path), the owner said "Fix it permanently. It's wasting so much time."

**Why:** each failure cost a push approval, a ~10-minute CI wait and another "check now" from the owner.

**How to apply:**
- Before any push touching packaging, release.yml or anything the build ships, run `packaging/release-build.ps1` locally (the same script release.yml calls) and see it pass.
- Before any Python push, run `uv run mypy --platform linux` as well as the normal checks.
- Never edit files with backslash-heavy text through shell or Python string literals: use the Edit tool, then scan for control characters.
- Batch all fixes into one push. Since 2026-10-29 pushes are automatic, so these local checks are the only gate before CI; release-build work (Windows) never goes to a cloud session.

Related: [[github-repo]], [[user-owner]].
