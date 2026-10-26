# 10: Status

_Replaced (never appended) at the end of every session. Last updated: **2026-10-26, about 22:35 IST**._

## Done
- **M1a planning** with the owner, then the approved 8-step M1a plan. Answers in [11](11-decisions.md):
  - `main` guarded by a local pre-push hook
  - packages approved as one list
  - Playwright and axe in CI only
  - `brand/draft/` kept
- **Repo:** https://github.com/techaust/shelf_sync, created 2026-10-26.
  - First commit `59ae0f5` (521 files, secret-scanned) was the one direct push.
  - It became **public** after GitHub refused to start Actions jobs on the private repo (an account billing block).
  - `main` is now **protected on GitHub**: PR required, both CI checks must pass, linear history, no force-push or deletion, admins included. The local hook stays too.
- **M1a package pins** approved and recorded in [04 §2.1](04-architecture.md): 13 Python, 22 UI, 4 CI actions, each released on or before 2026-10-12.
  - **Security fixes may pass the cutoff** (owner): certifi 2026.10.19 and filelock 4.2.1.
- **M1a.1 Backbone, merged as PR #2** ([runs/m1a.1-backbone.md](runs/m1a.1-backbone.md)):
  - FastAPI health route; the data folder; SQLite with numbered migrations
  - the 127.0.0.1 port with retry and fallback (SET-06, ERR-06)
  - JSON logs with the redaction hook (LOG-01); UTC times (NFR-8); tests fail on outbound calls (NFR-5)
  - CI: Python checks with a per-folder coverage gate, plus the brand tests
  - reviewer APPROVE, fix round, re-check APPROVE
- **PR #3:** `CHANGELOG.md`, the app commands in CLAUDE.md, CI pinned to `ubuntu-24.04`, agent worktrees ignored.
- **Docs updated for the public repo:** CLAUDE.md, 02, 03, 04, 04-A V23, 06 §10, 08, 09.

## In progress
- Nothing. No agent is running.

## Next
1. **M1a.2, security base** (Tier A):
   - the `analyst` drafts the brief
   - the lead writes the final brief at **Opus 5.5 high** (the owner switches the model menu, then back to medium)
   - then builder → analyst early check → reviewer with `security-review`

   The brief must route every output through `redact` (M1a.1 review #11).
2. **M1a.3, app shell** (designer, Opus high), which can run beside M1a.2: React, tokens and fonts, UI-SHELL, axe in CI. It also covers the M1 token follow-ups below.
3. **M1a.4, tray and Windows**: UI-TRAY, SYS-02/03/04, V29 and V31, plus M1a.1's carry-overs (single instance before start-up touches `tmp\`, `runtime.json`, nine lows).

## Waits on the owner
- **This end-of-day PR:** yes to push `docs/end-of-day-2026-10-26` and open the PR, then yes to merge it on green.
- **Model menu:** start the next session on **Opus 5.5, medium**.
- **Review the "Lead (proposed)" rows** in [11](11-decisions.md) when convenient (now about 30).
- **GitHub billing (your call):** the techaust account has a billing block that stops Actions on private repos. It doesn't affect the public repo.
- **Optional:**
  - anything you remember about UDesign ([01](01-audit.md)) before M4
  - the unpinned `mcp-proxy-for-aws@latest` setting (the AWS MCP also timed out today)
  - a $0 trademark search for "ShelfSync"

## Not verified
- **M1a.1 on Windows outside the tests:**
  - starting the server by hand (`python -m shelfsync`)
  - whether the 3 s port retry covers a real 2-minute TIME_WAIT after a restart
  - nested junctions inside `tmp\`
- **The per-folder coverage gate** has only run with empty folders ("nothing to check").
- **The two artifacts on claude.ai itself:** the pane isn't signed in. The plan page was rebuilt and republished today (version 3) after the 02 §1 and §11 changes; its source `plan-page.src.html` changed in this PR.
- **Brand assets in Windows** (tray, File Explorer, NSIS at 150 %/200 %) and the README header on GitHub.
- **Screen accessibility:** axe, screen reader, forced colours and reduced motion arrive with the React screens (M1a.3).
- **Hidden skills:** plugin-prefixed `skillOverrides` still appear in the skill list. Not investigated.
- **Model audit today:** 6 runs.
  - The builder is flagged "no skill loaded". That's expected: no 09 §3 skill fits, and it used Context7.
  - Each review's skill started a read-only general-purpose helper at high (the 12 §3 exception), including under the medium re-check.
  - The lead stayed at medium all day.
- **AWS MCP:** timed out at start-up; sign-in not checked.
- **04-A rows still to verify:** V29 and V31 (M1a.4); V12, V14, V15 and V26 (M1b); V6 and V8 (M2); V3 and V28 (M3); V4 and V5 (M5).
- **The deny rules** cover file reads only, not shell commands. The bucket mapping waits for M4 prep.

## Open follow-ups
- **M1b:**
  - logs pruned by age (M1a.1 review #10)
  - whether the updater keeps the GitHub token while the repo is public ([04 §7](04-architecture.md))
- **M1 tokens** (from P3.4–P3.5):
  - a ShelfSync token layer (app-bar tokens, fixed type sizes, code at 14 px, the `color-mix` tints in [runs/p3.4](runs/p3.4-mockups.md) §4)
  - one shared SecretField
  - aligning the wizard's Test-step badges
  - measuring "Installs in under a minute"
- **Pin refresh:** Starlette suggests `httpx2` for its test client (harmless now).
- **Teaching progress** is designed; it's built in M4.
- **`brand/draft/`** stays; it was committed (owner).
