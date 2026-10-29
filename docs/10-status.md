# 10: Status

_Replaced (never appended) at the end of every session._

## Date and time
2026-10-29, 13:25 IST: the end of the session that started 2026-10-28 at 17:12 IST and ran overnight.

## Done
All merged on green with the owner's yes. Before each push, all 14 checks and the release build passed on this PC. M2.5a and M2.5b were checked again after their rebases onto `main`.

| PR | What | Review |
|---|---|---|
| [#22](https://github.com/techaust/shelf_sync/pull/22) | M2.2 daily database backups, retention, restore command, backup settings API | approve |
| [#23](https://github.com/techaust/shelf_sync/pull/23) | M2.3 storage settings, the four S3 secrets in Credential Manager, storage API without Test | 10/10 |
| [#24](https://github.com/techaust/shelf_sync/pull/24) | M2.4 encrypted backup export and import, body limit, shared secrets lock | 10/10 |
| [#25](https://github.com/techaust/shelf_sync/pull/25) | Overnight record | docs |
| [#26](https://github.com/techaust/shelf_sync/pull/26) | M2.5a Settings › Stores, store health chips, Help panel guides | 7.5 → 9/10 |
| [#27](https://github.com/techaust/shelf_sync/pull/27) | M2.5b Settings › Storage and Backup; Settings pages load on demand (main chunk 481 kB); screens that fail to load keep the shell | 7 → 9/10 |
| [#28](https://github.com/techaust/shelf_sync/pull/28) | Record of the #25–#27 merges | docs |

- **M2:** m2.1 to m2.5b are merged: stores, backups, storage settings, export and import, and all their screens. m2.7 (S3) and m2.8 (test stack) wait on the owner's package yes.
- **Record:**
  - 11 rows for the day's decisions;
  - 13 wording for M2.3, M2.4, M2.5a and M2.5b;
  - 06 §2 and §3;
  - every run file from m2.2 to m2.5b closed, with its Usage line;
  - [08](08-roadmap.md) shows M2's progress;
  - CLAUDE.md gains the screen-code layers rule and the shared-queue rule.

## In progress
Nothing. No agent is running. There are no worktrees and no branches other than this record's (`docs/end-of-day-2026-10-29b`).

## Next
1. **This record PR**, with the owner's yes.
2. **m2.6 M2 docs** (lead):
   - the runbooks call the Add card's button "Save", but the screen says "Add store" and "Save store";
   - the restore runbook and the new Help guide must say the same thing;
   - user-facing notes for Stores, Storage and Backup.
3. **m2.7 S3 and m2.8 test stack** once boto3 and moto have the owner's yes; then the **m2.9 exit test**, which is the owner's.

## Waits on the owner
1. **Packages for S3 (m2.7) and the test stack (m2.8):** boto3 (run time) and moto with `s3` and `server` (dev). Nothing S3 is built until you say yes ([runs/m2.0-plan.md](runs/m2.0-plan.md) §3 Q1).
2. **One check in real Edge**, outside Claude, on the source app (`PYTHONPATH=backend uv run pythonw -m shelfsync.launcher`):
   - after you save a store's keys, an S3 key pair or the export passphrase, does Edge offer "Save password?" If it does, the secret fields change ([11](11-decisions.md) 2026-10-29);
   - does Copy in the S3 guide work?
   - does Export save a `.ssbak` file in Downloads?
3. **The M1b exit test** ([runbooks/m1b-exit-test.md](runbooks/m1b-exit-test.md)), outside the Claude app, including the Windows checks.
4. **The other M2 questions** in [runs/m2.0-plan.md](runs/m2.0-plan.md) §3.
5. **Review** the "Lead (proposed)" rows in [11](11-decisions.md), dated 2026-10-27 to 2026-10-29. One of them is how "keep building milestones" was read: build only, with no push or merge without your yes.
6. **Model menu:** start every session on **Opus 5.5, high** (the plan from 2026-10-29: Opus 5.5 at high for every task, [12](12-models-and-usage.md)).
7. **Cloud sessions, once** (in progress 2026-10-29: the GitHub App is installed): turn on the GitHub connector, make the `shelf_sync` environment (Limited network, seven allowed sites, `tools/cloud/setup.sh`), connect GitHub at claude.ai/code ([runbooks/cloud-sessions.md](runbooks/cloud-sessions.md) §2).

## Not verified
- **Cloud sessions** (2026-10-29): `tools/cloud/setup.sh` and `tools/cloud/session-start.sh` haven't run on a cloud machine yet; the first session's start-up lines are the check ([runbooks/cloud-sessions.md](runbooks/cloud-sessions.md) §4).
- **The one-model settings** (2026-10-29): whether `availableModels: ["claude-opus-5-5"]` and the `sonnet`/`haiku` aliases pointed at Opus behave as [12 §6](12-models-and-usage.md) describes is checked on the first day they're active. The `model-guard` hook was tested with sample inputs.
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

## Usage
- **The 5-hour window:** at 69 % now; it resets at 14:10 IST.
  - Overnight it reached 77 %, so the m2.5b designer was held until the reset (12 §5).
  - At most two agents ran at once, and only one used the browser.
  - The shared heavy queue was held twice by other projects' jobs; ShelfSync's checks waited.
- **Model audit for 2026-10-29** (`node tools/model-audit.mjs 2026-10-29`): 12 runs, all Opus, Sonnet or Haiku 5.5, never Fable. The lead ran at medium all day.
  - **Two runs flagged "no skill loaded":** the M2.4 builder (no 09 §3 skill fits it) and the M2.4 reviewer's later rounds (it loaded `code-review` and `security-review` in its first round on 2026-10-28, then re-applied them by hand).
  - **One `general-purpose` run:** the read-only helper that `code-review` starts (the 12 §3 exception).
