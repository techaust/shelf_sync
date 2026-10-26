# 10: Status

_Replaced (never appended) at the end of every session. Last updated: **2026-10-27**._

## Done
- **PR #5 merged:** the final M1a.2 brief (analyst draft, lead at Opus high), keyring pins, doc fixes, 04-A V32/V33. Owner decisions in [11](11-decisions.md): keyring in M1a.2 with exact pins; sign-ins kept in memory only.
- **All three remaining M1a build steps are built, reviewed and re-checked, on local branches (nothing pushed):**

| Task | Branch (head) | Review | Local checks |
|---|---|---|---|
| M1a.2 security base (Tier A) | `feat/m1a.2-security` (`6dca164`) | early check CHANGE → fixed; review APPROVE (`code-review` + `security-review`); triage at high; re-check APPROVE | 421 passed; `secure/` 100 %; Windows checks 9 passed; pip-audit clean |
| M1a.3 app shell | `feat/m1a.3-app-shell` (`86ab5b4`, on M1a.2 at `872dea4`) | SEND BACK (1 high) → fixed; re-check APPROVE (code + visual); round 2 of lows done | Vitest 261, pytest 465, build, `npm audit` 0, brand 221; Playwright + axe written, CI only |
| M1a.4 tray, launcher, Windows | `feat/m1a.4-tray` (`2168f5c`, on M1a.2 at `6dca164`) | APPROVE (security verdict: no other user or process can get the token); three fix rounds; re-checks APPROVE | 625 passed; Windows checks 27 passed; V29 and V33 confirmed; **pip-audit fails on Pillow** |

- **Docs branch `docs/m1a.3-m1a.4-briefs`** (local): the M1a.3 and M1a.4 briefs, new wording in [13](13-content.md) §3, four "Lead (proposed)" rows in [11](11-decisions.md), Playwright output in `.gitignore`, this page.

## Waits on the owner
1. **Pillow (package decision).** Pillow 12.3.0 has 37 known vulnerabilities, fixed in **13.0.0 (released 2026-10-16, 11 days old)**. Recommended: allow 13.0.0 as a security exception, like certifi and filelock; then rerun the tray tests and the Windows checks. Until then M1a.4's CI is red and can't merge. Real risk today is low: Pillow only opens ShelfSync's own six tray icons.
2. **Pushes and merges, in this order** (each push and merge needs your yes):
   1. `docs/m1a.3-m1a.4-briefs` (docs)
   2. `feat/m1a.2-security`
   3. `feat/m1a.3-app-shell`, rebased on `main` (its first CI run includes Playwright + axe)
   4. `feat/m1a.4-tray`, rebased, after the Pillow decision
3. **V31 Defender check, with you present:** it writes the harmless EICAR test string and raises a Defender alert. Command is in [runs/m1a.4-tray-windows.md](runs/m1a.4-tray-windows.md) §3.
4. **M1a exit test, with you:** the app runs from the tray (right-click menu, Open, View logs, Quit couldn't be clicked by agents today).
5. **Review** the "Lead (proposed)" rows in [11](11-decisions.md) when convenient.
6. **Model menu:** start the next session on **Opus 5.5, medium**.

## Not verified
- **CI on GitHub** for M1a.2, M1a.3, M1a.4: nothing pushed. The Playwright + axe suite (24 tests, forced colours and reduced motion included) has never run.
- **The real tray menu**, Quit and View logs on a running launcher (no interactive input for agents); proven by tests with real pystray objects only.
- **Forced colours** in the browser pane (can't be emulated); checked in code.
- **2× full-page screenshots** of the real app: the capture helper is blocked by the app's CSP by design; pane captures only.
- **V31** (not run), a second Windows user for V33, IPv6 listeners.
- **Model audit for today** (`node tools/model-audit.mjs 2026-10-27`): 23 runs, all Opus or Sonnet 5.5 at the planned effort.
  - Four builder runs are flagged "no skill loaded". That's expected: no 09 §3 skill fits the builder.
  - Each review skill started a read-only general-purpose helper (the 12 §3 exception).
  - The lead ran at high for the two key steps, the M1a.2 final brief and the review triage.
  - The run files' `Usage:` lines are still to fill when each is integrated.

## Next (after the merges)
- **M1b brief:** installer and updater, plus today's carry-overs: a data-folder lock file for a second logon session; ShelfSync's own toast AUMID; `UI_DIR` from `paths.py` and a missing UI as an error when installed; optional install-folder image check and a socket-owner re-check after connecting; logs pruned by age; whether the updater keeps the GitHub token.
- **M2 brief:** modals with native `<dialog>`; store, S3 and GitHub secrets in Credential Manager registered with `redact`.
- **Token follow-up:** move the duplicated dark rules in `app.css` into component tokens.

## Usage
5-hour window at 51 % late in the session, with up to two agents at once all day. The lead was at medium except the M1a.2 final brief and review triage (high, as planned).
