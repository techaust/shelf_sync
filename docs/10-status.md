# 10: Status

_Replaced (never appended) at the end of every session._

## Date and time
2026-11-05, about 15:10 IST: the end of the day ("end the day"), in the PC session that started at about 03:10 IST. The m2.8 work ran overnight while the owner slept; t8 ran in a side session the owner started.

## Done
All merged on green under the automatic rule.

| PR | Task | What |
|---|---|---|
| [#59](https://github.com/techaust/shelf_sync/pull/59) | m2.0 answers | The owner answered m2.0 §3:<br>- **Q2:** import only into a fresh install.<br>- **Q3:** Laragon (already at `C:\laragon`) replaces LocalWP; on its non-commercial free tier, the owner made the call on its terms.<br>- **Q5:** the owner reads bucket versioning in the S3 console.<br>LocalWP → Laragon across 02, 04, 04-A (new V57), 07, 08, 09 and the runbooks. The plan page was republished |
| [#60](https://github.com/techaust/shelf_sync/pull/60) | m2.8, Laragon half (Tier B) | **The test harness for the Laragon site** `https://shelfsync-test.test`:<br>- `testenv/laragon.py`: `cert`, `keys`, `check`, `seed` (13 sample products, no SKU), every connection pinned to 127.0.0.1.<br>- The site gets the harness's own exact-name certificate: Python refuses Laragon's `*.test` wildcard, and Laragon rewrites its own certificate (owner's tries, 04-A V57).<br>- Runbook [test-stack.md](runbooks/test-stack.md) §3, click by click, each step marked (you) or (Claude).<br>Reviews: analyst CHANGE (9 fixed), reviewer APPROVE (11 fixed), re-check APPROVE (1 low fixed by the lead) |
| [#61](https://github.com/techaust/shelf_sync/pull/61) | t8 (Tier A) | **Store client:** a 3xx whose `Location` httpx can't read now answers `redirected` on Test connection instead of crashing (found in m2.8's re-check). It also removed m2.8's stopgap. Analyst GO (4 lows fixed), reviewer APPROVE, 2804 tests passed, release build passed |
| (this PR) | End of day | CLAUDE.md (Laragon is the owner's, the test-stack commands), 08, the run files closed, fresh-start (the Laragon site comes back by redoing the runbook), this page, CHANGELOG #56–#61 |

**Seen 2026-11-05** after the owner's full restart of the Claude app: Sentry, Supabase, Upstash, Cloudflare and Playwright are hidden; the Claude Docs connector and `scheduled-tasks` still show, and the deny rules stop their tools (09 §2, [11](11-decisions.md)).

## In progress
- **No agent is running.** The t8 side session ([runs/t8-woo-redirect.md](runs/t8-woo-redirect.md)) is done; the app's worktree for it, `.claude/worktrees/loving-khayyam-9dfca1`, goes when that session is archived.

## Next
1. **The Laragon site (the owner's part, about 20 minutes):** [runbooks/test-stack.md](runbooks/test-stack.md) §3.1–§3.4: make the site, `cert`, reload Apache, check Laragon keeps the site file, WooCommerce and its two keys, the S3 extension pointed at the moto server.
2. **Then the lead:** `check` (closes V57 for Laragon) and `seed`; then the owner tries one download (§3.6, V6). Results go into [runs/m2.8](runs/m2.8-laragon-test-stack.md) §6 and 04-A.
3. **M2 exit test (m2.9, the owner's):** the two stores (read test only), S3 with both keys through **Test connection**, and the test stack. The AWS keys must be made again first ([runbooks/keys-and-policies.md](runbooks/keys-and-policies.md)).

## Waits on the owner
1. **The Laragon site setup** (Next 1).
2. **Upload the new `tools/cloud/setup.sh`** to the `shelf_sync` cloud environment (claude.ai/admin-settings › Cloud environments › `shelf_sync` › Setup script › Choose file). Until then cloud sessions print a Python PROBLEM line.
3. **Review the "Lead (proposed)" rows** in [11](11-decisions.md):
   - today's: the test-stack transport, m2.8's harness shape and rules (with the certificate's paths), t8's response-hook rule;
   - from 2026-11-04: local Node 24.22.1, the PyYAML build tools pinned by version only;
   - still open from 2026-11-02: the moto package set, m2.7's L1–L13, T2 to T5.
4. **Make the AWS keys again** (lost in the format), before the exit test.
5. **Where the release signing key lives**, since the owner keeps no backups: decide before the key is made.
6. **Archive the finished t8 side session** if wanted (its worktree goes with it).
7. **Still open from before:**
   - 13's proposed strings (the Storage Test row, the region error);
   - T7's rehearsal outside Claude;
   - stopping `testenv/moto_s3.py` with Ctrl+C in a real console;
   - the Edge check;
   - the M1b exit test;
   - the optional "Automatically delete head branches" setting;
   - sharing the plan and mockup pages, if anyone else should see them.

## Not verified
- **Anything against the real Laragon site:** that Laragon leaves `sites-enabled\00-shelfsync-test.test.conf` alone; that Apache reads the certificate's key, which is locked to the owner's account; WooCommerce's Basic auth over that HTTPS; V57's real request; the seed; V6 (the S3 extension against moto). All wait for the owner's runbook steps.
- **t8 against a real store:** proven with mocked responses and a fuzz test only.
- **Toasts under the registered AUMID** from an installed copy on winrt 4.x.
- **`setup.sh` on a real cloud VM** with Python 3.15.2.
- **The stores' TLS chains** under Python 3.15 (certain eMudhra intermediates are rejected). Checking needs the owner's go-ahead; due before M6.
- **The artifact pages on a phone:** published, not looked at.
- **Unchanged from before:**
  - anything against real AWS or a store;
  - Playwright with axe (CI only), Windows High Contrast, a screen reader;
  - a second Windows user (V33), IPv6 listeners, the cross-port parts of V32, 2× full-page shots;
  - a daily backup at a real 02:00 and across DST.

## Open follow-ups
- **New today, from t8** ([runs/t8-woo-redirect.md](runs/t8-woo-redirect.md) §6), each its own task:
  - **F1 (Tier A):** refuse a store host httpx can't decode, at save, in the backup import, and in `testenv/laragon.py`.
  - **F2 (Tier A, low):** the updater's same httpx exposure in `update/github.py` (its hosts are allowlisted GitHub).
  - **F3 (low):** one shared `_redirect_host` for the client and `seed`.
  - A store's cookie text can reach the app log through a `http.cookiejar` warning.
- **From 2026-11-04:** the console code-page low from the py315 re-check; 3 moderate npm vulnerabilities in the frontend packages (not looked at); the plugin's AWS server needs AWS keys.
- **The updater in a suffixed (rehearsal) build** must refuse to check or install, before `release_key.PUBLIC_KEY` is set (T6).
- **T7 review lows 1, 3, 4 and 5**, then one more real rehearsal run.
- **m2.7:** L1's known limit; review N2 (watch for flaky tests); one isolated Session per Test (M5 client cache).
- **T2:** share the store and storage Test button parts.
- **OmniSync's research scripts** can't run: there's no venv and no keys, and making a venv would change OmniSync.

## Usage
- **The 5-hour window:** 16 % at the m2.8 brief (about 03:40 IST); about 60 % at the end of m2.8 (about 05:45 IST); after the 06:10 IST reset, 5 → 13 % for t8; 14 % now (15:10 IST), resetting at 16:10 IST. Weekly, all models: 2 %.
- **Model audit** (`node tools/model-audit.mjs 2026-11-05`): every run Opus 5.5 at high, within the plan. The one `general-purpose` run in each task is the read-only helper that `code-review` starts (the allowed exception, 12 §3); t8's "no skill loaded" flags are the analysts and the builder, for whom no 09 §3 skill fits.
- **Agents today:** m2.8: builder (three parts), analyst, reviewer (twice). t8: analyst (twice), builder, reviewer. At most two ran at once.
