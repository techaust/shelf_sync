# 10: Status

_Replaced (never appended) at the end of every session._

## Date and time
2026-11-04, 16:20 IST: the end of the day ("end the day"), in the PC session that started at about 01:40 IST. It was the first day on the newly formatted PC.

## Done
All merged on green under the automatic rule.

| PR | Task | What |
|---|---|---|
| [#51](https://github.com/techaust/shelf_sync/pull/51) | Fresh start | **The new folder layout:** `shelf_sync` in `D:\Business\2. GPL Projects\3. Other Assets\Applications\`, NSIS beside it, techaust_platform in `D:\Business\1. Parent Project\TecHaust Technologies\Application\`. Every path in the repo updated. OmniSync is back as read-only reference, and its `config.env` is blocked at the new path. The fresh-start runbook is rewritten from the real run |
| [#52](https://github.com/techaust/shelf_sync/pull/52) | py315-move (Tier B) | **Python 3.15.2 replaces 3.14.8** (owner's choice):<br>- winrt 4.x forced under windows-toasts 1.3.1.<br>- PyYAML built as pure Python, with its build tools pinned.<br>- The installer embeds 3.15.2.<br>- CI comments, cloud scripts, 04, 04-A (new V55, V56) and the ADRs updated.<br>Reviews: builder, analyst GO, reviewer APPROVE, and a fix re-check APPROVE. Three local release builds passed |
| [#53](https://github.com/techaust/shelf_sync/pull/53) | py315-move | The owner's `-m windows` run outside Claude passed (51 passed, 1 skipped; cold toast 0.46 s). The run file is closed |
| [#54](https://github.com/techaust/shelf_sync/pull/54) | Pages | **New links** for the plan page (https://claude.ai/artifact/PznaCjWtR9afUfV1ho4vqN) and the mockup (https://claude.ai/artifact/UER2z6uQage6XFJuHtYCys): the old ones no longer open from the owner's account |
| [#55](https://github.com/techaust/shelf_sync/pull/55) | Tools | **Everything ShelfSync doesn't use is turned off for this project:**<br>- Sentry, Supabase and Upstash plugins (`@inline`).<br>- The Claude Docs connector.<br>- The user-level Supabase, Upstash and duplicate AWS servers, and scheduled tasks (this PC's `disabledMcpServers`).<br>aws-core and the skills bundle stay on (owner) |
| (this PR) | End of day | CLAUDE.md rule 8 (where the tool switches live), the 08 status cell, this page, CHANGELOG #53–#55, and two memory notes |

**Set up on this PC** (machine-level, not in the repo):
- **Python 3.15.2:** the owner installed it, outside Claude.
- **uv 0.12.19** (SHA-256 checked) and **NSIS 3.13** (matches the pin).
- **Plugins:** `security-guidance` and `aws-core` reinstalled with the owner's yes.
- **Repo:** the downloaded copy was made into a clone, its git settings set, and the 14 memory notes restored.
- **Packages:** `uv sync` and `npm ci` (frontend, brand).

## In progress
- Nothing. No agent is running, and the builder's worktree and every finished branch are removed.

## Next
1. **Check the tool switches** ("check the tools"): after the owner restarts the Claude app, a new session should show no Sentry, Supabase, Upstash or Claude Docs.
2. **m2.8, the LocalWP half** (Tier B, with the analyst's early check), after the owner's answer to [runs/m2.0-plan.md](runs/m2.0-plan.md) §3 Q3. The 2026-11-03 answers to Q2, Q3 and Q5 were reverted, so all three are open.
3. **M2 exit test (m2.9, the owner's):** the two stores (read test only), S3 with both keys through **Test connection**, and the test stack. The keys were lost in the format and must be made again first ([runbooks/keys-and-policies.md](runbooks/keys-and-policies.md)).

## Waits on the owner
1. **Restart the Claude app.** After that, this session's tools see `uv` on the PATH, the aws-core plugin's AWS server can connect (once AWS keys exist), and the tool switches load.
2. **Upload the new `tools/cloud/setup.sh`** to the `shelf_sync` cloud environment (claude.ai/admin-settings › Cloud environments › `shelf_sync` › Setup script › Choose file). Until then cloud sessions print a Python PROBLEM line.
3. **Review the "Lead (proposed)" rows** in [11](11-decisions.md):
   - today's: local Node 24.22.1, and the PyYAML build tools pinned by version only, without a hash or pip-audit;
   - still open from 2026-11-02: the moto package set, m2.7's L1–L13, T2 to T5.
4. **Share the new pages** if anyone else should see them: both are private to the owner's account.
5. **m2.0-plan §3 Q2, Q3 and Q5** (import rule, WooCommerce over HTTPS on LocalWP, bucket versioning).
6. **Where the release signing key lives**, since the owner keeps no backups: decide before the key is made.
7. **Still open from before:**
   - 13's proposed strings (the Storage Test row, the region error);
   - T7's rehearsal outside Claude;
   - stopping `testenv/moto_s3.py` with Ctrl+C in a real console;
   - the Edge check;
   - the M1b exit test;
   - the optional "Automatically delete head branches" setting.

## Not verified
- **The tool switches:** they load at session start, so they were set and documented but not yet seen in a new session. Of them, only `claude mcp list` was checked: the three user-level servers show "Disabled for this project".
- **Toasts under the registered AUMID** from an installed copy on winrt 4.x. The owner's `-m windows` run used the default notifier.
- **`setup.sh` on a real cloud VM** with Python 3.15.2. The script's SHA-256 matches three sources.
- **The Python 3.15.2 installer's SHA-256:** the file was gone before it could be checked, so the PSF signature on `python.exe` was checked instead.
- **The stores' TLS chains:** Python 3.15 rejects certain eMudhra intermediate certificates. Checking the stores needs the owner's go-ahead; it's due before M6.
- **The new artifact pages on claude.ai and on a phone:** they were built from the repo and published, but not looked at.
- **Unchanged from before:**
  - anything against real AWS or a store;
  - V6 (the S3 extension against moto);
  - Playwright with axe (CI only), Windows High Contrast, a screen reader;
  - a second Windows user (V33), IPv6 listeners, the cross-port parts of V32, 2× full-page shots;
  - a daily backup at a real 02:00 and across DST.

## Open follow-ups
- **New today:**
  - The console code-page low from the py315 re-check: the signature check's `[Console]::OutputEncoding` leaves the shared console on UTF-8 for the rest of a release build. Cosmetic.
  - 3 moderate npm vulnerabilities in the frontend packages; seen at `npm ci` and not looked at.
  - The GitHub plugin's connection failed earlier today, then connected; `gh` covers everything either way.
  - The plugin's AWS server needs AWS keys and `uv` on the PATH.
- **The updater in a suffixed (rehearsal) build** must refuse to check or install, before `release_key.PUBLIC_KEY` is set (T6).
- **T7 review lows 1, 3, 4 and 5**, then one more real rehearsal run.
- **m2.7:** L1's known limit; review N2 (watch for flaky tests); one isolated Session per Test (M5 client cache).
- **T2:** share the store and storage Test button parts.
- **OmniSync's research scripts** can't run: there's no venv and no keys, and making a venv would change OmniSync.

## Usage
- **The 5-hour window:**
  - 3 % at the start (about 01:50 IST); 19 % at the peak of the py315 task (about 03:45 IST).
  - After the reset: 11 % now (16:16 IST); it resets at 20:10 IST.
  - Weekly, all models: 39 %.
- **Model audit** (`node tools/model-audit.mjs 2026-11-04`): every run Opus 5.5 at high.
  - 2 flagged "no skill loaded": the builder and the analyst, for whom no 09 §3 row fits.
  - The 2 `general-purpose` runs are the read-only helpers that `code-review` starts (the allowed exception, 12 §3).
- **Agents today:** the builder (twice resumed), the analyst, and two reviewers. At most two ran at once.
