# 10: Status

_Replaced (never appended) at the end of every session._

## Date and time
2026-11-02, about 08:05 IST: the end of the orchestrating PC session that started at about 00:45 IST. The owner asked for every pending task to run in parallel under one session and went to sleep at about 01:20 IST; the session ran the rest on its own.

## Done
All merged on green under the automatic rule.

| PR | Task | What |
|---|---|---|
| [#37](https://github.com/techaust/shelf_sync/pull/37) | P0 | **boto3 1.43.112 and moto 5.2.4 locked** (owner's yes): `moto[s3]` plus flask and flask-cors instead of the `server` extra (16 packages, not about 44) |
| [#38](https://github.com/techaust/shelf_sync/pull/38) | T4 | `switchStore` and the Settings › Updates model and wording moved to `lib/`; `lib/layers.test.ts` enforces "nothing in `api/`, `lib/`, `components/` reaches `screens/`" (cloud session) |
| [#39](https://github.com/techaust/shelf_sync/pull/39) | T5 | Dark values as component tokens, each theme scope written once (cloud session); 48 computed-colour comparisons with `main` identical (04-A V54) |
| [#40](https://github.com/techaust/shelf_sync/pull/40) | T6 | A `-Suffix` build uses suffixed Run value and AUMID (m1b.3 finding 7) |
| [#41](https://github.com/techaust/shelf_sync/pull/41) | T1 / m2.7 | **The S3 client and the 3-step Storage Test** (`POST /api/storage/test`, ERR-03): an isolated boto3 client, only its own `shelfsync-test/` object, L1–L13 in 11; 04-A V8, V10, V51–V53 verified |
| [#42](https://github.com/techaust/shelf_sync/pull/42) | T7 | `tools/release/rehearse.py` runs a current build again: **46 of 46 checks** inside Claude; each copy gated (throwaway names, no real data folder) |
| [#43](https://github.com/techaust/shelf_sync/pull/43) | T3 / m2.8 (moto part) | `testenv/moto_s3.py`: moto S3 on 127.0.0.1:47630 only, Host allowlist, CORS off; runbook `test-stack.md`; V8 presigned URLs recorded (moto accepts expired and tampered links) |
| [#44](https://github.com/techaust/shelf_sync/pull/44) | T2 | **Test connection on Settings › Storage**: the three steps, the left-behind warning, the stale-answer note; checked in the pane against a local moto server |

Every task had its run file, the reviews its tier asks for (Tier A/B: the analyst's early check; screens: a visual review in the built-in pane), and a release build before any push that ships code. Details are in each run file (`docs/runs/t1`… are named `m2.7-s3.md`, `t2-…` to `t7-…`).

## In progress
- Nothing. No agent runs; the session's local worktrees for the merged tasks may still sit in `.claude\worktrees\` (all committed and merged; safe to remove).

## Next
1. **M2 exit test (m2.9, the owner's):** the two stores (read test only), S3 with both keys through the new **Test connection**, and the test stack. Before it: the owner's LocalWP half of m2.8 (below).
2. **m2.8, the LocalWP half** (Tier B, with the analyst's early check): LocalWP + WooCommerce + the owner's Amazon S3 Storage extension pointed at `testenv/moto_s3.py` (V6), after the owner's answer to [runs/m2.0-plan.md](runs/m2.0-plan.md) §3 Q3.

## Waits on the owner
1. **Review the night's "Lead (proposed)" rows** in [11](11-decisions.md), dated 2026-11-02: the moto package set, m2.7's L1–L13 and the region rule, T2's layout and strings, T3's server defaults, T4 and T5's structure. One row records a lead mistake: T3 ran as Tier C, though 12 §2 puts the test stack in Tier B.
2. **13's new proposed strings:** the Storage Test row (m2.7 and T2) and the region error.
3. **Runs outside the Claude app** (Windows PowerShell):
   - T7's rehearsal outside Claude (steps in [runs/t7-rehearse-current-build.md](runs/t7-rehearse-current-build.md) §2);
   - the `-m windows` checks (T6 changed the Run value and AUMID code);
   - `testenv/moto_s3.py` stopped with Ctrl+C in a real console ([runbooks/test-stack.md](runbooks/test-stack.md)).
4. **m2.0-plan §3 Q3** (WooCommerce over HTTPS on LocalWP) and **Q5** (bucket versioning state; with versioning on, each Test leaves a tiny old version and a delete marker).
5. Still open from before: the Edge check (password prompts, Copy, Export download), the M1b exit test, Auto-fix (now works from the lead: turned on for #37–#44), and the optional "Automatically delete head branches" setting (more merged branches on GitHub now, including the cloud sessions' `refactor/switch-store-lib` and `refactor/dark-tokens`, which were re-pushed under new names after rebasing).

## Not verified
- **Anything against real AWS or a store** (by design): V52's 403 without `s3:ListBucket`, what other S3-compatible services answer, and whether one rejects the checksum headers. The M2 exit test is the first live check.
- **V6:** whether the S3 extension works against `testenv/moto_s3.py` (with CORS off and the Host allowlist).
- **Screens:** Playwright with axe (CI only), Windows High Contrast, a screen reader; T2's stale note in dark; the brief loading skeletons and forced colours after T5 (unit-tested only). The built-in pane's captures were cropped late in the night, so some T2 shots are partial (their text was read from the page).
- **T7 outside Claude**, a killed rehearsal run, and the real mutex shared by rehearsal copies (a T6 follow-up).
- **T6:** an update installed into a rehearsal copy drops the suffix (follow-up below).
- **Unchanged from before:** a second Windows user for V33; IPv6 listeners; the cross-port parts of V32 in a browser; 2× full-page shots of the real app; a daily backup at a real 02:00 and across DST; the store Test connection against the live stores.

## Open follow-ups
- **The updater in a suffixed (rehearsal) build** must refuse to check or install, or an update drops the suffix; this must land before `release_key.PUBLIC_KEY` is set (T6). A rehearsal copy also still uses the real data folder, Credential Manager service at run time, single-instance name and default `InstallDir`.
- **T7 review lows 1, 3, 4, 5:** block (not only prove) the real Credential Manager service in copies; guard each credential delete; per-store leftovers; refuse a `--work` inside a real folder. Then one more real rehearsal run.
- **m2.7:** L1's known limit (an overran Storage Test held by a trickling endpoint keeps the busy flag); review N2 (the hold-past-the-limit tests need the clients built within 2 s; watch for flakes); one isolated Session per Test (M5 client cache).
- **T2:** share the store and storage Test button and result parts (`components/StoreTest.tsx` gains `id`, `describedBy`, `blocked`).
- **Older, unchanged:** `switchStore` follow-up **closed** by T4; the token task **closed** by T5; `rehearse.py` **closed** by T7. Still open: the cloud toolchain (update `tools/cloud/setup.sh` when versions change).

## Usage
- **The 5-hour window:** 31 % at 00:51 IST; it reset at about 02:20 IST and reached **97 %** at about 06:15 IST, when new agents stopped (the 95 % gate) until the reset at about 07:20 IST; about 17 % at the end (08:05 IST).
- **Cloud sessions:** T4 and T5 ran in the cloud from the owner's go. Later tasks couldn't start cloud sessions: the app starts them only on the owner's own words, not from an automated turn, so T1, T2, T3 and T7 ran here with agents, at most two at once. Cloud sessions also can't report back; the lead watched their branches on GitHub.
- **Model audit** (`node tools/model-audit.mjs 2026-11-02`, this PC): every run Opus 5.5 at high. 2 flagged "no skill loaded": T7's builder and analyst, whose brief named no skill (none fits a rehearsal-script change). The four built-in `general-purpose` runs are the read-only helpers `code-review` starts (the allowed exception, 12 §3). The cloud sessions' runs (T4, T5) are logged on their own machines.
