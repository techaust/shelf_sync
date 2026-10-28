# 10: Status

_Replaced (never appended) at the end of every session._

## Date and time
2026-10-28, 13:55 IST (end of the overnight session that started 2026-10-27, 18:46 IST).

## Done
Under the owner's overnight instruction ([11](11-decisions.md) 2026-10-28), each task went brief → build → review → fixes → re-review, with every local check and the release build passed before its push.

| PR | What | CI |
|---|---|---|
| [#15](https://github.com/techaust/shelf_sync/pull/15) | M1b.1 per-user installer, embedded-Python build, release workflow | green |
| [#16](https://github.com/techaust/shelf_sync/pull/16) | M1b.2 signed in-app updates, backup before migrations, Updates API | green |
| [#17](https://github.com/techaust/shelf_sync/pull/17) | One release script (`packaging/release-build.ps1`) for CI and this PC | green |
| [#18](https://github.com/techaust/shelf_sync/pull/18) | M1b.3 Settings › App API, log pruning by age, one installed-copy test; the M1b runbooks; the M2 plan | green |
| [#19](https://github.com/techaust/shelf_sync/pull/19) | M2.1 store settings, store keys in Credential Manager, read-only Test connection; M2 security docs and runbooks | green |
| [#20](https://github.com/techaust/shelf_sync/pull/20) | M1b.4 Settings shell, Settings › Updates and Settings › App screens (548 screen tests, 1,763 backend tests and the release build passed here first) | green |

- **M1b code is complete**; the exit test is the owner's ([runbooks/m1b-exit-test.md](runbooks/m1b-exit-test.md)).
- **M2 plan** ([runs/m2.0-plan.md](runs/m2.0-plan.md)): m2.1 merged; briefs written for m2.2, m2.3 and m2.4.
- **Record:** 11 rows for tonight's decisions; 13 wording for M1b.3, M1b.4 and M2.1; 05 palette keys; 06 entry names, IAM policies and residual risks; 07 MockTransport; runbooks `keys-and-policies.md`, `key-rotation.md` and the M1b set.

## In progress
- **M2.2 daily database backups, retention, restore command** (branch `feat/m2.2-db-backups`, local, not pushed):
  - the build and the first review's fixes are on the branch (full pytest 1,872 and the release build passed there);
  - the re-review's fixes N1–N6 (the builder's checks: ruff, format, mypy both platforms, 1,881 tests, bandit) are cherry-picked onto the branch as `d47e8fc`, with the handover in `a05360f`; the full checks and the release build haven't run on the branch since.
- No agent is running.

## Next
1. M2.2: move `feat/m2.2-db-backups` onto `main` with `git rebase --onto main cb52f30` (this record PR already carries its two docs commits `f1799b3` and `cb52f30`); run every check and the release build; push, PR, merge on green.
2. M2.3 storage settings (Tier A) from [runs/m2.3-storage-settings.md](runs/m2.3-storage-settings.md), then M2.4 backup export (Tier A) from [runs/m2.4-backup-export.md](runs/m2.4-backup-export.md); each with the early check, review, fixes and re-review.
3. The M2.5a and M2.5b screens brief for the designer (plan in [runs/m2.0-plan.md](runs/m2.0-plan.md) §1).
4. Remove the two finished agent worktrees (CLAUDE.md, Git workflow): `agent-a133ea61ee2221031` (still locked by process 9612) and `agent-a225369f658fc52e6`.

## Waits on the owner
1. **Model menu:** the lead ran at **high** all night (left there by the overnight instruction). Start the next session on **Opus 5.5, medium**.
2. **The M1b exit test** ([runbooks/m1b-exit-test.md](runbooks/m1b-exit-test.md)), outside the Claude app, including step 16, the Windows checks (`uv run pytest -m windows --no-cov`).
3. **Packages for S3 (m2.7) and the test stack (m2.8):** boto3 (run time) and moto with `s3` and `server` (dev). Nothing S3 is built until you say yes ([runs/m2.0-plan.md](runs/m2.0-plan.md) §3 Q1).
4. **The other M2 questions** in [runs/m2.0-plan.md](runs/m2.0-plan.md) §3: the import rule, the test-stack transport, store colours, how to read the bucket's versioning state.
5. **Review** the "Lead (proposed)" rows in [11](11-decisions.md), most of them dated 2026-10-27 and 2026-10-28.

## Not verified
- **M2.2's N1–N6 fixes** passed only the builder's checks in its worktree; the release build and `npm run schema:check` haven't run on them yet (the builder says no API shape changed).
- **The Settings screens (#20) in the installed app**, outside Claude: only the dev server and the reviewer's screenshots in the built-in browser.
- **The store Test connection against the live stores:** never run (no live reads without your yes); the fake answers are built from the WooCommerce docs (m2.0 R14). Whether a Shop Manager key can read `system_status` (R1) is checked in the M2 exit test.
- **Store entries in Credential Manager outside Claude** (m2.0 R9): the `-m windows` checks haven't been run outside Claude since M2.1.
- **A daily backup at a real 02:00, and across a real DST change:** only fake clocks.
- Unchanged from before: a second Windows user for V33; IPv6 listeners; the cross-port `SameSite` and preflight parts of V32 in a browser; 2× full-page screenshots of the real app; the original stuck Quit (never reproduced).

## Open follow-ups
- **A `-Suffix` build still writes the real `ShelfSync` Run value and AUMID** if installed and started interactively ([11](11-decisions.md) 2026-10-28, m1b.3 finding 7).
- **`tools/release/rehearse.py`** doesn't run against a current build; repaired before the next rehearsal (m2.1 review L3).
- **`packaging/smoke.py` gains a `hashlib.scrypt` call** in M2.4 (m2.0 R6).
- **The OneDrive Desktop lags after a delete:** `packaging/test-installer.ps1` now waits up to 10 s for the shortcuts to go; watch it in CI.
- **Token task:** move the duplicated dark rules in `app.css` into component tokens.

## Usage
- The 5-hour window is at **1 %** (a new window; it resets at 18:09 IST). The owner lifted the 80 % pause for the overnight run only; the two-agent limit held throughout.
- **Model audit since 2026-10-27** (`node tools/model-audit.mjs 2026-10-27`): 45 runs, all Opus or Sonnet 5.5, never Fable.
  - **The lead ran at high** for the overnight work (flagged as a note; the 12 §3 rule is medium outside the five key steps).
  - **7 runs flagged "no skill loaded":** five builders and two analysts; no 09 §3 skill fits their tasks (Context7 was optional and not needed).
  - The `general-purpose` runs are the read-only helpers that `code-review` and `security-review` start (the 12 §3 exception).
