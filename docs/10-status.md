# 10: Status

_Replaced (never appended) at the end of every session._

## Date and time
2026-11-18, about 15:10 IST: the end of the day ("end the day"). One PC session ran from 2026-11-17 about 17:10 IST to now; the owner slept from about 23:15 to 10:20 IST and said "keep working". (This page wasn't replaced on 2026-11-17, so it covers both days.)

## Done
All merged on green under the automatic rule.

| PR | Task | What |
|---|---|---|
| [#63](https://github.com/techaust/shelf_sync/pull/63) | m2.8 verified | The Laragon test site verified end to end; **the owner's M2 exit test passed; M2 approved 2026-11-17**; opentelemetry-api 1.45.2 (a CVE fix) |
| [#64](https://github.com/techaust/shelf_sync/pull/64) | m3.0 | The M3 plan; the owner answered its eight questions (all recommended) |
| [#65](https://github.com/techaust/shelf_sync/pull/65) | m3.1 (Tier B + security) | **Read the stores' catalogs and link them:** migration 0003, the paged GET-only reader (APL-12 retries, caps, count check, cookie drop), linking by slug, near-miss detection, download slots, the runner, `/api/sync`, `/api/catalog`, `/api/wizard`, and the L1 dry-read command. Analyst CHANGE; review 1 SEND BACK (1 high: new keys could reach an old address mid-run), fixed; second full review APPROVE; re-check APPROVE |
| [#66](https://github.com/techaust/shelf_sync/pull/66), [#68](https://github.com/techaust/shelf_sync/pull/68) | L1 | **The first live read** (the owner, outside Claude): GPLFamily read in full on 2026-11-17, PluginWay stalled twice that evening; with t9's trace both read in full on 2026-11-18. 2,398 products on each store, 2,395 slugs on both, 2 of 01-A's 3 near-miss pairs found ([runs/t9 §7](runs/t9-l1-diagnostics.md)) |
| [#67](https://github.com/techaust/shelf_sync/pull/67) | t9 (Tier B + security) | **Diagnostics for L1** (trace, `--no-meta`, `--per-page`, `--read-seconds`), used to show PluginWay's stalls weren't ShelfSync's settings. Analyst CHANGE; review 1 SEND BACK (1 high: a misleading `ended` label), fixed; second full review APPROVE; two re-checks APPROVE |
| [#69](https://github.com/techaust/shelf_sync/pull/69) | m3.2 (Tier B + security) | **Incremental sync every 15 minutes and the 02:00 snapshot:** migration 0004, snapshots stored as changes with per-store retention, trashed and deleted products found (a deletion only on a confirmed 404), same-night retries, the scheduler, change detection for Cleanup, the test-only launcher. **04-A V3 verified** (a downloads update keeps the ids) and **V28 answered** on the test site. Analyst CHANGE; review 1 SEND BACK (1 high: a bulk deletion stopped snapshots for good), fixed; second full review APPROVE; two re-checks APPROVE |
| (this PR) | End of day | This page, CHANGELOG #62–#69, 08's status, the run files' handovers, decision rows |

**The owner's decisions in these two days** ([11](11-decisions.md)): M3 Q1–Q8 (2026-11-17); a store's address edited after its catalog exists asks "same store" or "a different store"; **APL-12 counts failed reads, not failed requests** (10 failed reads in a row auto-pause a store).

## In progress
- **No agent is running.** No worktree is left; every task branch is merged and deleted.

## Next
1. **m3.3, Cleanup's backend** (after the weekly reset, 2026-11-19 12:30 IST): issues from m3.2's change sink, link-pair, dismiss, not-the-same, accept (SYNC-02), undo (CAT-08), activity rows, and CAT-03's title rule fix ([11](11-decisions.md) 2026-11-18).
2. **m3.4, the Catalog screens** (designer, with the browser), beside m3.3 once two agents may run again.
3. Then m3.5 (the Cleanup screens), m3.6 (docs: 04 §4–§5, 06, 07, 13, the 11 rows), and the M3 exit test (the owner's, [runs/m3.0 §5](runs/m3.0-plan.md)).

## Waits on the owner
1. **Review the "Lead (proposed)" rows** in [11](11-decisions.md), in particular today's: m3.1's and m3.2's choices, t9's diagnostics, CAT-03's title rule. Older ones are still open too (the moto package set, m2.7's L1–L13, T2 to T5, m2.8's harness rules, Node 24.22.1, the PyYAML pins).
2. **Upload the current `tools/cloud/setup.sh`** to the `shelf_sync` cloud environment, if not done since 2026-11-05 (not confirmed in the record).
3. **Where the release signing key lives**, since the owner keeps no backups: decide before the key is made.
4. **Still open from before:** 13's proposed strings (the Storage Test row, the region error); T7's rehearsal outside Claude; stopping `testenv/moto_s3.py` with Ctrl+C in a real console; the Edge check; the M1b exit test; the optional "Automatically delete head branches" setting; sharing the plan and mockup pages.
5. **From the M3 exit test on:** ShelfSync reads both stores every 15 minutes and at 02:00 while it runs (the owner's standing go-ahead, M3 Q4). Nothing reads the live stores until the owner builds the catalog in the installed app.

## Not verified
- **The live stores under m3.2's sync and snapshot:** only L1's dry reads have touched them (read-only, counts only). From the M3 exit test on.
- **Real-world timing of the scheduler:** a real 60 s loop across a real sleep, a real daylight-saving change, a real uvicorn start and stop.
- **The cause of PluginWay's 2026-11-17 evening stalls:** likely load on its side (it sits behind Cloudflare); not proven. An evening read around 22:00 IST would test it (optional).
- **WooCommerce's minimum version for `include_status`** (V28): it works on 11.3.0; the docs give no minimum.
- **`-m windows`**, Playwright with axe (CI only), a screen reader, Windows High Contrast.
- **Unchanged from before:** anything against real AWS; a second Windows user (V33); IPv6 listeners; the cross-port parts of V32; 2× full-page shots; the stores' TLS chains under Python 3.15 (due before M6); the artifact pages on a phone.

## Open follow-ups
- **From m3.1** ([runs/m3.1 §5](runs/m3.1-catalog-read.md)): one shared `parse_system_status`; `seed` keeping download ids by file; one shared in-memory database helper; a repeated 400 past page 1 counted; m3.3 to report "same slug on two stores, separate items".
- **From m3.2** ([runs/m3.2 §5](runs/m3.2-sync-snapshots.md)): a clock-jump leftover night whose stretched state rows overlap the real nights (for M5's restore); purged products aging out of the expected set past retention; speed (chunked `item_link`, decoding unchanged rows, `next_runs` connections); duplicated helpers; `GET /api/sync` not saying which stores a mixed run read in full (for m3.4).
- **Flaky tests on load:** `tests/test_run_application.py` and `tests/test_server.py` hold fixed ports 47615–47624, which Linux CI can hand out to client connections (failed once on #65's CI, passed on re-run); `tests/test_storage_test.py::test_running_out_of_time_during_the_cleanup_names_the_key` failed once under a full local run (passed 3/3 alone).
- **The builders skip the release build** when only `backend/` changes; the lead runs it before every push of shipped code (done for #65, #67, #69).
- **From t8** (2026-11-05): F1 (refuse a store host httpx can't decode, Tier A), F2 (the updater's same exposure), F3 (one shared `_redirect_host`). The cookie-text-in-log note is fixed by m3.1's cookie drop.
- **Older:** the console code-page low from the py315 re-check; 3 moderate npm vulnerabilities in the frontend (not looked at); the updater refusing in a suffixed build (T6); T7 review lows 1, 3, 4, 5; m2.7's L1 limit and review N2; T2 (shared Test button parts); OmniSync's research scripts can't run (no venv, no keys).

## Usage
- **The 5-hour window:** 9 % at the start (2026-11-17 about 17:15 IST); resets at about 19:00 and 00:00 and 05:00 and 10:00 IST; 56 % now (15:10 IST).
- **Weekly (all models): 77 → 95 %**, resetting 2026-11-19 12:30 IST. One agent at a time throughout; no new agent until the reset.
- **Model audit** (`node tools/model-audit.mjs 2026-11-17` and `2026-11-18`): every run Opus 5.5 at high. The "no skill loaded" flags are the builders and analysts, for whom no 09 §3 skill fits; each `general-purpose` run is the read-only helper that `code-review` starts (the allowed exception, 12 §3).
- **Agents in these two days:** m3.1: builder (four rounds), analyst, reviewer, a second reviewer (with re-check). t9: builder (five rounds), analyst, reviewer, a second reviewer (with two re-checks). m3.2: builder (five rounds), analyst, reviewer, a second reviewer (with two re-checks).
