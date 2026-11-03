---
name: github-repo
description: techaust/shelf_sync is public during development (billing block on private Actions); main protected; pushes and merges automatic since 2026-10-29
metadata:
  node_type: memory
  type: project
  originSessionId: 977e7fbb-3029-4996-9c88-fcf3ade00401
  modified: 2026-10-27T08:11:11.025Z
---

The repo https://github.com/techaust/shelf_sync was created 2026-10-26 as private. GitHub then refused to start any Actions job on it ("recent account payments have failed or your spending limit needs to be increased"), and `gh`'s token can't read the account's billing. The owner chose to make the repo **public during development**, accepting that the store names, their WooCommerce/WordPress versions and the security design are readable. On the public repo the jobs ran, and `main` got GitHub's own branch protection (PR required, "Python checks" and "Brand checks" must pass and be up to date, linear history, admins included), on top of the local `.githooks/pre-push` guard.

**Why:** GitHub Free has no branch protection on private repos, and the billing block is the owner's to sort out.
**How to apply:** never commit secrets or real store addresses (anything committed is public). Merge only by PR. Since 2026-10-29 (owner) branch pushes and PR merges are automatic once a task is done: the repo's "Allow auto-merge" is on and `.github/workflows/automerge.yml` squash-merges every same-repo PR on green; repo settings, branch protection, tags and releases still need the owner's yes. In cloud sessions `gh pr` is blocked (GraphQL): use `gh api`. A branch cut from another branch's pre-squash head moves with `git rebase --onto main <old base>`; rerun the full checks before pushing (on 2026-10-27 this caught M1a.3 + M1a.4 only breaking together). The UI CI job runs Playwright + axe, which never run on this PC. Turn on the app's PR Auto-fix for each PR the lead opens (pushing by itself is allowed now). If the repo goes private again, protection and free minutes both go away: re-check docs/04-A V23 first. Related: [[user-owner]], [[published-pages]].
