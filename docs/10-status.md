# 10: Status

_Replaced (never appended) at the end of every session._

## Date and time
2026-10-29, morning IST (the session that started 2026-10-28 evening, ran overnight, and merged #25 to #27 with the owner's yes).

## Done
Merged with the owner's yes, each with every local check and the release build passed before its push:

| PR | What | CI |
|---|---|---|
| [#22](https://github.com/techaust/shelf_sync/pull/22) | M2.2 daily database backups, retention, restore command, backup settings API | green |
| [#23](https://github.com/techaust/shelf_sync/pull/23) | M2.3 storage settings, the four S3 secrets in Credential Manager, storage API without Test | green |
| [#24](https://github.com/techaust/shelf_sync/pull/24) | M2.4 encrypted backup export and import, body limit, shared secrets lock | green |

Then, with the owner's yes this morning (each rebased onto `main`, with all 14 checks and the release build passed again before its push):

| PR | What | CI |
|---|---|---|
| [#25](https://github.com/techaust/shelf_sync/pull/25) | End-of-day record | green |
| [#26](https://github.com/techaust/shelf_sync/pull/26) | M2.5a Settings › Stores, store health chips, Help panel guides (review 7.5 → APPROVE 9/10) | green |
| [#27](https://github.com/techaust/shelf_sync/pull/27) | M2.5b Settings › Storage and Backup, lazy Settings pages (main chunk 481 kB), load-failure guard (review 7 → APPROVE 9/10) | green |

- **Record:**
  - 11 rows for tonight's decisions;
  - 13 rows for M2.5a and M2.5b, ERR-01 in two lines, and `busy` on store writes;
  - the run files for m2.5a and m2.5b (§3–§7);
  - m2.2–m2.4 closed;
  - CHANGELOG #21–#27.

## In progress
Nothing is running; no agent worktrees are left. This record sits on the local branch `docs/record-2026-10-29-merges`, not pushed.

## Next
1. **This record PR**, with the owner's yes.
2. **m2.6 M2 docs** (the lead), including the runbooks' "Save" vs the screen's "Add store" / "Save store".
3. m2.7 S3 and m2.8 test stack once boto3 and moto have the owner's yes; then the m2.9 exit test.

## Waits on the owner
1. **Yes to push and merge** this record PR.
2. **One check in real Edge** (outside Claude, on the source app, now that M2.5a and M2.5b are merged):
   - after saving a store's keys, an S3 key pair or the export passphrase, does Edge offer "Save password?"
   - does Copy in the S3 guide work?
   - does Export save a `.ssbak` file in Downloads?

   If Edge offers to save passwords, the secret fields change ([11](11-decisions.md) 2026-10-29).
3. **The M1b exit test** ([runbooks/m1b-exit-test.md](runbooks/m1b-exit-test.md)), outside the Claude app, including the Windows checks.
4. **Packages for S3 (m2.7) and the test stack (m2.8):** boto3 (run time) and moto with `s3` and `server` (dev). Nothing S3 is built until you say yes.
5. **The other M2 questions** in [runs/m2.0-plan.md](runs/m2.0-plan.md) §3.
6. **Review** the "Lead (proposed)" rows in [11](11-decisions.md), most of them from 2026-10-27 to 2026-10-29.

## Not verified
- **The M2.5 screens against the real server:** only a mock that sends the backend's real CSP, in the built-in pane. Also unverified there: a real Edge download, the Windows file picker, the clipboard, password prompts, Windows High Contrast, and Playwright with axe (CI only).
- **A route-level error in the shell** (`RouteError`): unit render only; it can't be triggered in the pane.
- **The store Test connection against the live stores:** never run (no live reads without your yes).
- **Store and S3 entries in Credential Manager outside Claude:** the `-m windows` checks haven't run outside Claude since M2.1.
- **A daily backup at a real 02:00, and across a real DST change:** only fake clocks.
- Unchanged: a second Windows user for V33; IPv6 listeners; the cross-port parts of V32 in a browser; 2× full-page shots of the real app.

## Open follow-ups
- **`switchStore`** stays in `screens/settings/` until Settings › Updates' model and wording move out of `screens/`.
- **A `-Suffix` build still writes the real `ShelfSync` Run value and AUMID** if installed and started interactively (m1b.3 finding 7).
- **`tools/release/rehearse.py`** doesn't run against a current build (m2.1 review L3).
- **The runbooks** call the Add card's button "Save"; the screen says "Add store" and "Save store" (for m2.6).
- **Token task:** move the duplicated dark rules in `app.css` into component tokens.

## Usage
- **The 5-hour window:** it reached 77 % before 04:10 IST. The m2.5b designer was held until the reset (12 §5), and the window then started again from 0 %. The two-agent limit and one browser at a time held all night.
- **Model audit for 2026-10-29** (`node tools/model-audit.mjs 2026-10-29`): 10 runs, all Opus, Sonnet or Haiku 5.5, never Fable. The lead ran at medium.
  - Two runs were flagged "no skill loaded": the M2.4 builder and the first M2.4 reviewer run. No skill in 09 §3 fits the builder. That reviewer applied the `code-review` and `security-review` checklists by hand (the skills run against `main`), without loading them.
  - The one `general-purpose` run was the read-only helper that `code-review` starts (the 12 §3 exception).
