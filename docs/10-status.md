# 10: Status

_Replaced (never appended) at the end of every session. Last updated: **2026-10-26, about 20:00 IST**._

## Done
- **Phase 3, brand and screens: approved 2026-10-26.** Look and feel scored 9 in [02 §12](02-plan.md).
  - **P3.0:** the built-in browser works inside agents over localhost (not `file://`).
  - **P3.1–P3.2, logo:** the owner chose the S-cut logo, then it was refined and audited ([14](14-brand-audit.md), [runs/p3.1](runs/p3.1-logo-concepts.md), [runs/p3.2](runs/p3.2-logo-refine.md)).
  - **P3.3, brand assets:** a pipeline in `brand/` builds all 46 assets. It has 221 tests and `npm audit` reports 0 ([runs/p3.3](runs/p3.3-brand-pipeline.md)).
  - **P3.4, mockups:** every screen, the wizard, the help panel and all states, after three review rounds. The decision-tied wording is in [13 §6](13-content.md) ([runs/p3.4](runs/p3.4-mockups.md)).
  - **P3.5, screenshots:** 16 screenshots plus 13 extras at 2×. The mockup artifact is at https://claude.ai/artifact/Gzzm2Mztikj8xqL49UoiRj and shrinks to fit on phones ([runs/p3.5](runs/p3.5-screenshots.md)).
  - **P3.6, plan page:** republished at a **new link**, https://claude.ai/artifact/9CYLJk6kRPncuJ3Lmunn5f. The old link is in the owner's previous Claude organization.
- **Owner decisions today** ([11](11-decisions.md)):
  - Reset access token ends every open session ([06 §2](06-security.md)).
  - Storage Test writes, reads and deletes a tiny test file ([06 §5](06-security.md)).
  - Roll back app keeps the data, or restores the pre-update backup after a warning ([04 §8](04-architecture.md)).
- **CLAUDE.md:** the commands now list brand, the plan page and the mockup artifact. New rules cover the screenshot method, screen wording and phones.

## In progress
- Nothing. No agent is running.

## Next
1. **M1a** ([08](08-roadmap.md)): the `shelf_sync` GitHub repo, the app shell, CI and the tray. The lead plans it with the owner first. Creating the repo and every push need the owner's yes.

## Waits on the owner
- **Model menu:** start the next session on **Opus 5.5, medium**.
- **Review the "Lead (proposed)" rows** in [11](11-decisions.md) dated 2026-10-26 when convenient. They are routine choices from P3.3–P3.6.
- **Optional:** add anything you remember about UDesign ([01](01-audit.md)) before M4.
- **Optional, your call:** the user-level AWS MCP setting runs `mcp-proxy-for-aws@latest` (unpinned).
- **Optional, $0:** a trademark search for "ShelfSync" ([14 §4](14-brand-audit.md)).

## Not verified
- **The two artifacts on claude.ai itself.** The pane isn't signed in, so the lead checked the same page files locally. The owner saw the mockup on a phone. The plan page's flow chart draws only on claude.ai.
- **Brand assets in Windows:** the icons in the real Windows tray and File Explorer, the NSIS art at 150 % and 200 %, and the README header on GitHub (M1).
- **Screen accessibility:** axe, a screen reader, forced colours and reduced motion haven't been run on the screens (they will be on the React screens from M1a). Teaching progress in the mockup is static sample data.
- **The 72 hidden skills:** plugin-prefixed `skillOverrides` (sentry:*, supabase:*, upstash:*, some anthropic-skills:*) still appear in the skill list. Not investigated.
- **Model audit:** today's audit flags one early designer run with no skill loaded (06:48 IST, the P3.0 browser probe, which needed none). Each `code-review` helper (general-purpose, read-only) is listed as the 12 §3 exception. The lead ran at high only for the P3.1 choice and the P3.2 brief.
- **AWS MCP sign-in:** not checked.
- **04-A rows still to verify** at their milestone: V29 and V31 (M1a); V12, V14, V15 and V26 (M1b); V6 and V8 (M2); V3 and V28 (M3); V4 and V5 (M5).
- **Not run yet:**
  - `security-review` needs the git repo (M1a).
  - The deny rules cover file reads only, not shell commands.
  - The bucket mapping waits for M4 prep.

## Open follow-ups
- **For M1** (from P3.4–P3.5):
  - a ShelfSync token layer: the app-bar tokens, fixed type sizes, code at 14 px, and the `color-mix` tints listed in [runs/p3.4](runs/p3.4-mockups.md) §4
  - one shared SecretField
  - aligning the wizard's Test-step badges
  - measuring "Installs in under a minute"
- **Teaching progress** (strip, Dashboard row, one announcement) is designed; it's built in M4.
- `brand/draft/` (the P3.2 generator) is still there. The P3.2 audit cites it; remove it only with the owner's yes.
