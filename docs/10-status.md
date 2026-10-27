# 10: Status

_Replaced (never appended) at the end of every session._

## Date and time
2026-10-27, 17:55 IST (end of the second session of the day).

## Done
- **M1a approved by the owner** after its exit test, run from Windows PowerShell outside the Claude app:
  - Open, View logs, a second start and Quit all work from the tray.
  - The Windows checks passed outside Claude.
  - V31 verified: Defender made the EICAR file unreadable at once and removed it after about 15 s.
- **M1a.5, the Quit fix ([#12](https://github.com/techaust/shelf_sync/pull/12)).** In the exit test, one Quit once stopped the server but left the program and its icon running until a second click; it wasn't reproduced in three tries. The fix:
  - tray actions run off the icon's loop;
  - the tray's stop checks that its loop ended, and hides the icon if not;
  - shut-down log lines;
  - a `faulthandler` safety exit (45 s, then 10 s) with a stall report read back through `redact`.

  Analyst, builder, then three reviewer passes, all APPROVE with every finding fixed. The owner's re-test outside Claude passed.
- **M1b started.**
  - The analyst drafted the plan and the updater brief, saved in [runs/m1b.2-updater.md](runs/m1b.2-updater.md) §0–§1.
  - The owner decided the update token is optional, the test account, real test releases, where the signing key lives, that "Remove my data" also clears Credential Manager, about 3.5 days, and portable NSIS.
  - The owner approved the M1b package list (rows in [11](11-decisions.md)).
- **M1b.0, Python 3.14 ([#13](https://github.com/techaust/shelf_sync/pull/13)).** 3.12.10 (April 2025) was 3.12's last release with Windows builds, so the owner moved ShelfSync to 3.14.
  - The owner installed 3.14.8 from python.org.
  - The re-lock changed no package.
  - CI gets 3.14.8 through `actions/setup-python` v7.0.0 (owner's yes) with `UV_PYTHON_DOWNLOADS: never`.
  - CI green on 3.14.8.
- **Record:**
  - [04-A](04-architecture-appendix/A-stack-verification.md): V31 verified; V11 and V12 updated for 3.14; new rows V34 (pystray stop), V35 (faulthandler) and V36 (the Claude app keeps a private copy of `%LOCALAPPDATA%`).
  - [06 §3](06-security.md): the stall file; [06 §5](06-security.md): the optional token.
  - [03](03-prd.md) SYS-06 and SET-04; the [ADR 0001](adr/0001-python-fastapi-sqlite-react.md) amendment and [ADR 0002](adr/0002-embedded-python-nsis.md).
  - 02, 04 and 09 for 3.14.
  - CLAUDE.md: Python 3.14.8, `UV_PYTHON_DOWNLOADS=never`, and the outside-Claude rule.
  - The roadmap, CHANGELOG #11–#13, and the run files.

| PR | What | CI |
|---|---|---|
| [#12](https://github.com/techaust/shelf_sync/pull/12) | M1a.5 Quit always exits | green (704 tests, the symlink tests included) |
| [#13](https://github.com/techaust/shelf_sync/pull/13) | M1b.0 Python 3.14; M1a closed; M1b decisions | green on 3.14.8 |

## In progress
Nothing. No agent is running. This record update is on the branch `docs/end-of-day-2026-10-27-c`.

## Next
1. **m1b.1 brief** (installer and packaging, Tier B), at medium.
2. **m1b.2 final brief** (updater, Tier A), at **Opus 5.5, high** (12 §3 key step 1), from the analyst's draft in [runs/m1b.2-updater.md](runs/m1b.2-updater.md).
3. Then the m1b.1 and m1b.2 builders side by side, under the shared-file contracts in that file's §0.

## Waits on the owner
1. **This record update:** push and merge it, with your yes.
2. **Model menu:** start the next session on **Opus 5.5, medium**; switch to **high** only when the m1b.2 final brief starts.
3. **Restart this PC once** when convenient. Two leftover worktree folders couldn't be deleted because a file in them was in use: `.claude/worktrees/agent-a4a26e3752a5edaf4` and `.claude/worktrees/agent-a3ab7c793b83446b9`. Git no longer tracks either, so the lead removes them after the restart.
4. **Review** the "Lead (proposed)" rows in [11](11-decisions.md) when convenient.

## Not verified
- **The original stuck Quit:** never reproduced. The fix is proven only against simulated failures, and the safety exit is there in case.
- **A cold crash toast's time** against the safety exit's 10 s last stage (m1b.1 times it).
- **Whether HKCU registry writes are also virtualized** inside the Claude app's package. The Windows checks passed both inside and outside Claude.
- **The real tray menu, clicked by an agent:** agents still can't click it; the owner's clicks proved it today.
- Unchanged from before: a second Windows user for V33; IPv6 listeners; the cross-port `SameSite` and preflight parts of V32 in a browser; 2× full-page screenshots of the real app.

## Open follow-ups
- **M1b carry-overs** (into m1b.1 and m1b.3, listed in [runs/m1b.2-updater.md](runs/m1b.2-updater.md) §0):
  - a data-folder lock file for a second logon session;
  - ShelfSync's own toast AUMID;
  - `UI_DIR` from `paths.py`, and a missing UI as an error when installed;
  - **the Run value must start ShelfSync in the tray without opening a tab** (found by the analyst);
  - logs pruned by age;
  - the `httpx` deprecation warning from `starlette.testclient`;
  - the optional install-folder image check and a socket-owner re-check.
- **Wording for 13:** the Updates empty state must change, because the token is now optional. Plus the updater's new messages (m1b.2 and m1b.4).
- **M2:** modals with the native `<dialog>`; store, S3 and GitHub secrets in Credential Manager registered with `redact`; BAK-01 must never delete a pre-migration backup that a kept version needs.
- **Token task:** move the duplicated dark rules in `app.css` into component tokens.

## Usage
- The 5-hour window was at **18 %** at the end of this session (a new window from about 16:30 IST; it peaked around 49 % in the previous one), so up to two agents can run at once.
- **Model audit for today:** 9 runs, all Opus or Sonnet 5.5 at the planned effort. The lead stayed at medium all session.
- Four analyst and builder runs are flagged "no skill loaded" because no 09 §3 skill fits them. The two `general-purpose` runs are the read-only helpers that `code-review` starts (the 12 §3 exception).
