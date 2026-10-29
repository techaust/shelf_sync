# 10: Status

_Replaced (never appended) at the end of every session._

## Date and time
2026-10-29, 23:31 IST: the end of the PC session that started at 21:29 IST. Work goes on in a **cloud session** (m2.6), which writes the next version of this file at its own end of day.

## Done
Merged on green. #30 needed the owner's yes; #31 and #32 merged themselves under the new automatic rule.

| PR | What |
|---|---|
| [#29](https://github.com/techaust/shelf_sync/pull/29) | The earlier end-of-day record |
| [#30](https://github.com/techaust/shelf_sync/pull/30) | **One model and effort:** every task on Opus 5.5 at high; tiers decide only the checks; 95 % budget gate; agents at once set by the machine ([ADR 0009](adr/0009-opus-high-for-every-task.md)) |
| [#31](https://github.com/techaust/shelf_sync/pull/31) | **Automatic push and auto-merge on green** (`automerge.yml`); **cloud session setup** (`tools/cloud/setup.sh`, `tools/cloud/session-start.sh`); `heavy.sh` reads Linux memory |
| [#32](https://github.com/techaust/shelf_sync/pull/32) | The cloud runbook for the Team plan: the `shelf_sync` environment, Limited network with seven allowed sites |

- **GitHub:** the repo's "Allow auto-merge" setting is on (owner's yes). #31 and #32 proved the workflow: each merged itself once its checks passed.
- **Cloud:** the owner installed the Claude GitHub App on `shelf_sync`, turned on the GitHub connector, and made the `shelf_sync` environment on the Team plan's Cloud environments page. The first cloud session started clean: Python 3.14.8, Node 24.19.0 and uv 0.12.19, with no PROBLEM lines (its own report).
- **Record:** CLAUDE.md (rules 3, 10 and 11, How work is split, Git workflow), [12](12-models-and-usage.md), [09](09-tooling.md), [11](11-decisions.md), ADR 0008 and 0009, the session skills, [runbooks/cloud-sessions.md](runbooks/cloud-sessions.md), the memory notes.

## In progress
- **m2.6 M2 docs**, lead-only, in the cloud session (branch `claude/friendly-keller-cepawy`). The owner approved its plan with a 46 % reading. One commit was pushed at 23:30 IST (runbooks, 04, 06, 07, 04-A, 11, and its run file `runs/m2.6-docs.md`, which lands with its PR). Its PR merges itself on green. **Before that, it rebases onto this record** and adds only its own CHANGELOG line (#29–#32 are already in).
- No agent runs on this PC. There are no local worktrees.

## Next
1. **m2.6**: finish in the cloud session.
2. **m2.7 S3 and m2.8 test stack** once boto3 and moto have the owner's yes; then the **m2.9 exit test**, which is the owner's.

## Waits on the owner
1. **Packages for S3 (m2.7) and the test stack (m2.8):** boto3 (run time) and moto with `s3` and `server` (dev). Nothing S3 is built until you say yes ([runs/m2.0-plan.md](runs/m2.0-plan.md) §3 Q1).
2. **One check in real Edge**, outside Claude, on the source app (`PYTHONPATH=backend uv run pythonw -m shelfsync.launcher`):
   - after you save a store's keys, an S3 key pair or the export passphrase, does Edge offer "Save password?" If it does, the secret fields change ([11](11-decisions.md) 2026-10-29);
   - does Copy in the S3 guide work?
   - does Export save a `.ssbak` file in Downloads?
3. **The M1b exit test** ([runbooks/m1b-exit-test.md](runbooks/m1b-exit-test.md)), outside the Claude app, including the Windows checks.
4. **The other M2 questions** in [runs/m2.0-plan.md](runs/m2.0-plan.md) §3.
5. **Review** the "Lead (proposed)" rows in [11](11-decisions.md), dated 2026-10-27 to 2026-10-29. Today's: how the one-model plan is enforced, usage read before every new agent, the cloud details, and the seven allowed sites.
6. **Model menu:** every session on **Opus 5.5, high**, on this PC and in the cloud.
7. **Usage in a cloud session:** it has no usage tool, so post the 5-hour % there each day, and again when a reading is over 2 hours old. A PC session can read it for you.
8. **Auto-fix:** the app refused to let the lead turn on Auto-fix for #31 (no reason given). Turn it on in the PR bar yourself, or allow `mcp__ccd_pr__set_monitor` in the app's permissions. Until then, a failed check is seen only when the lead looks.
9. **Optional:** GitHub's "Automatically delete head branches" setting would remove merged branches. 15 old branches are still on GitHub (not counting the cloud session's live one). A settings change, so it's yours.

## Not verified
- **A cloud session's PR merging itself:** the first one is m2.6's (opened with `gh api`, because `gh pr` is blocked in the cloud). The pre-push guard in the cloud hasn't been exercised yet either.
- **The one-model settings:** whether `availableModels: ["claude-opus-5-5"]` and the `sonnet`/`haiku` aliases pointed at Opus behave as [12 §6](12-models-and-usage.md) says. Nothing has asked for another model since. The `model-guard` hook was tested with sample inputs.
- **The M2.5 screens against the real server.** They were checked against a mock that sends the backend's real CSP, in the built-in pane. Also not checked:
  - a real Edge download, the Windows file picker, the clipboard and password prompts;
  - Windows High Contrast;
  - Playwright with axe (CI only).
- **A route-level error in the shell** (`RouteError`): checked by a unit render only. It can't be triggered in the pane.
- **The store Test connection against the live stores:** never run (no live reads without your yes).
- **Store and S3 entries in Credential Manager outside Claude:** the `-m windows` checks haven't run outside Claude since M2.1.
- **A daily backup at a real 02:00, and across a real DST change:** only fake clocks.
- **Unchanged from before:**
  - a second Windows user for V33;
  - IPv6 listeners;
  - the cross-port parts of V32 in a browser;
  - 2× full-page shots of the real app.

## Open follow-ups
- **`switchStore`** stays in `screens/settings/` until Settings › Updates' model and wording move out of `screens/` (11, 2026-10-29).
- **A `-Suffix` build still writes the real `ShelfSync` Run value and AUMID** if it's installed and started interactively (m1b.3 finding 7).
- **`tools/release/rehearse.py`** doesn't run against a current build (m2.1 review L3).
- **Token task:** move the duplicated dark rules in `app.css` into component tokens.
- **Cloud toolchain:** when `.python-version`, CI's Node or uv version changes, update `tools/cloud/setup.sh` (URL and SHA-256) and reload it into the `shelf_sync` environment.

## Usage
- **The 5-hour window:** at 50 % now; it resets at 00:10 IST.
- **Model audit for 2026-10-29** on this PC (`node tools/model-audit.mjs 2026-10-29`): 1 run, this lead, Opus 5.5 at high, `end-session` loaded; nothing flagged. The 12 earlier runs the 13:25 IST record listed are no longer in this PC's log folder (why wasn't checked). The cloud session's runs are logged on its own machine, and it audits them at its end of day.
