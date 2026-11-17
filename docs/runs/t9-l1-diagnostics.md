Status: open (brief written 2026-11-17)
Tier: B (12 §2: catalog), plus `security-review` by the reviewer (it touches `apply/`, 09 §3)
Usage: lead `claude-opus-5-5/high` [start-session] (PC): 5-h 15 % at the brief (2026-11-17, about 23:05 IST); weekly (all models) 82 %, so one agent at a time

# t9: diagnostics for the L1 dry read, to find why PluginWay stalls

L1 ([m3.1](m3.1-catalog-read.md) §7) read GF in full but PW stalled twice: run 1 answered `system_status` and pages 1–12, then page 13 never finished until the store's 10-minute bound; run 2 answered pages 1–15 within about a minute, then page 16 timed out on all 4 tries. The 2026-10-25 research reads, which read PW in full, kept cookies, used `requests`, a 90 s timeout and `_fields=id,type,downloadable,downloads`. This task gives L1 what it needs to tell the hypotheses apart (a firewall or host limit after about 13–16 requests, perhaps scoring a client that sends no cookies back; PW slow on some pages when `meta_data` is asked for; chance load), **one setting at a time**, without changing what the app itself does.

## 1. Brief

### PRD IDs
None new. It serves CAT-01 and APL-12 (L1, [m3.0](m3.0-plan.md) §2). Tests cite CAT-01 and APL-12.

### What to build
1. **An observer seam in the reader** (`apply/catalog_read.py`): `read_catalog` (and `read_store_catalog`) take an optional `observe` callback, called once per **attempt** (the first try and each retry) with a small frozen record:
   - what: `system_status` or `products`, the page number, the attempt number (1–4);
   - the outcome: `ok` or the fixed reason, and the HTTP status when an answer arrived;
   - the elapsed time of that attempt (monotonic, milliseconds), and the body bytes received;
   - for a timeout: whether the answer's **headers had arrived** (a stall after the headers is a slow or trickling body; before them, nothing came at all), and the bytes received before it ended. This needs `WooClient.get` to say so: `ReadRefused` may carry the status and the bytes received for a timeout during the body. That is the **only** change allowed in `apply/woocommerce.py`, and Test connection's behaviour must stay the same;
   - **response facts as fixed words, never values:** `cf-ray` present (yes/no); the `server` header's product as one of `cloudflare`, `nginx`, `apache`, `litespeed`, `openresty`, `other`, `none`; `cf-cache-status` as one of `hit`, `miss`, `dynamic`, `bypass`, `expired`, `other`, `none`; the **names** of cookies the store set, only from the allowlist `__cf_bm`, `cf_clearance`, `_cfuvid`, `PHPSESSID`, `wordpress_logged_in`, `wordpress_sec`, `wp-settings`, plus a count of any others (never a value, never an unlisted name). Read these from the response **before** the cookie drop removes `Set-Cookie` (say how; the cookie drop itself stays as it is, and no cookie is kept).
   - With `observe=None` (the app's runner, every existing caller) nothing changes: same requests, same results. A test proves it.
2. **Reader options for L1 only**, each defaulting to today's value, never set by the app: the products `_fields` without `meta_data` (`meta=False`); `per_page` (25–100); and `max_pages` (L1 may raise it so a smaller `per_page` still fits; the app keeps 40). With `meta=False`, `latest_version` data is simply absent (no error).
3. **L1 options** (`catalog/report.py`):
   - `--trace`: one line per attempt from the observer, for example `PW products page 13 try 1: timeout after 30.0 s, headers yes, 118,400 bytes; server cloudflare, cf-ray yes, cf-cache dynamic, cookies __cf_bm`. Fixed words and numbers only, local time `HH:MM:SS` at the start of each line;
   - `--no-meta`, `--per-page N` (25–100; L1 raises `max_pages` to fit), and the existing `--spacing-ms` (still at least 1,000);
   - the request list shown at the start reflects the options exactly (built from the same parameters, as now);
   - at the end, a short timing summary per store: requests, the median and slowest attempt times, and how many attempts timed out with and without headers.
4. **Tests** (fakes only, no network): the observer's records for a normal read, a 429 replayed, a timeout before headers and one during the body; each response fact's allowlist (an unlisted server or cookie name becomes `other`, a cookie value never appears); the trace and summary in a fresh subprocess contain no host, key, cookie value, query string, slug, title or file name; `--no-meta` and `--per-page` change the request list and the requests sent identically; the app's runner is unaffected (`observe=None`, the default options).

### Rules
- **No live call.** Nothing in this task sends a request to the live stores, the real bucket, the test site or GitHub. The owner runs L1.
- No new package; `uv.lock` unchanged. Context7 for httpx if you need streaming or header details you haven't used here.
- `UV_PYTHON_DOWNLOADS=never`; heavy runs through `bash tools/heavy.sh --log t9-<name> …` (wait for the lock, never stop another job). `mypy` clean on Windows and `--platform linux`.
- Commit in steps (conventional commits citing CAT-01, APL-12; the repo-local identity CLAUDE.md names). Never push.
- **Stop at the early check** once the observer seam, the `woocommerce.py` change and the reader options are committed with their tests; write §2's builder report and stop. The L1 options and their tests follow the analyst's check.

### Files
`backend/shelfsync/apply/catalog_read.py`, `backend/shelfsync/apply/woocommerce.py` (only as item 1 says), `backend/shelfsync/catalog/report.py`, `tests/**`, this run file (§2 and §3 only). **Never touch** anything else, in particular the runner, the API, `frontend/`, `packaging/`, `uv.lock`, the other docs.

### Skills and tools to load ([09 §3](../09-tooling.md))
Context7 (httpx 0.28.1) if needed. The reviewer loads `security-review` and `code-review`.

### Done
Full `uv run pytest`, `ruff check`, `ruff format --check`, `mypy`, `mypy --platform linux`, `bandit -r backend` pass (through `tools/heavy.sh`). The builder report lists every command with its result, each choice made, and what isn't verified.

### Out of scope
Changing the app's reader settings, keeping cookies, changing the User-Agent, or anything else the diagnosis may later point to (each a decision after the PW reads, before m3.2's brief); the follow-ups listed in m3.1 §5.

## 2. Early check

### Builder (Opus 5.5 high), 2026-11-17: items 1, 2 and 4 (their part); item 3 waits for the analyst

**Skills and tools.** 09 §3: "writing code that uses a library" → Context7 for httpx 0.28.1 (loaded; it had nothing on `Headers.get_list` or the hook order, so I read both in the installed source, `.venv/Lib/site-packages/httpx`). No 09 §3 skill fits a builder here: `security-review` and `code-review` are the reviewer's; `aws-sdk-python-usage` doesn't apply (no S3); `frontend-design`, `dataviz` and `artifact-design` don't apply (no screen, chart or page).

**Commits** (on the worktree branch, fast-forwarded from `b2da36f`; not pushed):

| Commit | What |
|---|---|
| `7a5c9fb` | `feat(stores)`: a timeout during the body says the headers had arrived and how many bytes came [CAT-01, APL-12] |
| `96b9d6d` | `feat(catalog)`: the reader's observer seam, response facts and L1 options [CAT-01, APL-12] |

**Files changed:** `backend/shelfsync/apply/woocommerce.py`, `backend/shelfsync/apply/catalog_read.py`, `tests/store_support.py` (a `StallingStream` and `stalling()` helper), `tests/test_woocommerce_client.py` (4 tests, 7 cases), `tests/test_catalog_diagnostics.py` (new, 23 tests, 63 cases), this file (§2). `catalog/report.py` isn't touched (item 3). Nothing else.

**How it works**
- **`woocommerce.py`, the one change.** `ReadRefused` gains two keyword-only fields, `headers_status` (the status whose headers had arrived when the body stalled; None when nothing came) and `received` (body bytes read before it ended), set only for a `timeout` (an httpx timeout, or the deadline passing between chunks). `WooClient.get` notes the status once the headers are in and counts bytes as before. **`status` stays None for a timeout:** putting the status there would have changed Test connection's `http_status` for a first-GET body timeout (None → 200) and the reader's `CatalogRead.http_status` and log line. Tested: both of Test connection's GETs give the same `ReadOutcome` as before.
- **Reading the facts before the cookie drop.** httpx 0.28.1 runs the response hooks only after `_send_single_request`, which calls `transport.handle_request` and then `cookies.extract_cookies` (`_client.py` 979–982, 1014, 1022). So a hook sees the answer after `GetOnlyTransport` has dropped `Set-Cookie`, and only a transport inside it sees them. `FactsTransport(inner)` is the transport L1 gives `WooClient`, which wraps it: `GetOnlyTransport(FactsTransport(real))`. For each answer it keeps `response_facts(headers)` (fixed words and a count only) and hands the answer on unchanged. Then `GetOnlyTransport` drops the cookies exactly as before. It only ever sees GETs. `read_catalog(..., facts=…)` takes the same object to attach the facts to each attempt (`take()`, once). Tested: no cookie in the jar, none sent back, and no cookie value, hash suffix, unlisted name or `cf-ray` value in the records.
- **The observer.** `read_catalog` and `read_store_catalog` (through `**options`) take `observe: Callable[[Attempt], None] | None`. `_Session.request` calls it once per attempt, right after `client.get` returns or refuses, and before the failure count or the retry decision, so the attempt that auto-pauses a store is recorded too. `Attempt` (frozen) holds `what` (`system_status`/`products`), `page`, `attempt` (1–4), `outcome`, `http_status`, `elapsed_ms`, `body_bytes`, `headers` and `facts`. With `observe=None` the session makes no extra clock call and builds nothing.
- **Options.** `read_catalog(meta=True, per_page=100, max_pages=40)` goes into a small frozen `_Shape` that checks the values and builds each page's query through `listing_params(page, per_page=, meta=)`, the function L1's request list already uses. `parse_page(body, per_page=, meta=)` caps a page at `per_page` rows and, with `meta=False`, reads no `meta_data` (`Product.meta == ()`, `meta_skipped == 0`, and a row without `meta_data` is fine).

**Choices I made (Lead (proposed) if the lead keeps them)**
1. `ReadRefused` carries the facts in new fields, and `status` keeps its old meaning (above).
2. The facts come from an inner transport (`FactsTransport`), not a hook, and not from a change to `GetOnlyTransport`.
3. **Outcome words:** `ok` (an answer the reader takes: a 200 page, or a usable `system_status`), `past_the_end` (a 400 on page 2 or later, which isn't a failure), and otherwise the fixed reason. A 200 page that later fails parsing is `ok` for the attempt; the read's own result says `bad_response`.
4. **`headers` has three states:** True for any HTTP answer, and for a `redirected` or `bad_response` refusal (both happen only after the headers are in). For a timeout: whether `headers_status` was set. For `unreachable`/`tls_error`: whether the `FactsTransport` saw an answer, or None (not known) without one.
5. **`body_bytes`:** the body length for an answer, `received` for a timeout (0 when nothing came), None when not known (a redirect, or a body refused as too long).
6. **`elapsed_ms`:** the reader's monotonic clock from just before `client.get` to just after, never the spacing or the back-off before it.
7. **`server`:** the first token of the header (cut at `/`, space, `(`, `,` or `;`), lowercased, matched exactly; an empty header is `other`, a missing one `none`. **`cf-cache-status`:** the whole value, trimmed and lowercased, matched exactly.
8. **Cookie names:** case-sensitive. `__cf_bm`, `cf_clearance`, `_cfuvid` and `PHPSESSID` match exactly. `wordpress_logged_in`, `wordpress_sec` and `wp-settings` also match as a family (`wordpress_logged_in_<hash>`, `wordpress_sec_<hash>`, `wp-settings-1`, `wp-settings-time-1`), because WordPress always adds a suffix. Only the family word is kept: the hash is derived from the site address. Each word appears once, in the brief's order. `Set-Cookie2` counts too. A header with no `=`, and WordPress's admin cookie `wordpress_<hash>`, count as others.
9. **Ranges:** `per_page` must be 25–100. `max_pages` must be ≥ 1 with `max_pages × per_page` ≤ 4,000 (the app's 40 × 100), so `per_page 25` allows up to 160 pages. A value outside is a `ValueError` before anything is sent.
10. An exception raised by the `observe` callback isn't caught: it's L1's own code, not the store's answer.

**Commands run and their results** (all with `UV_PYTHON_DOWNLOADS=never`, `--locked`)
- While working: `uv run pytest --no-cov` on `test_catalog_read`, `test_woocommerce_client`, `test_catalog_report`, `test_catalog_diagnostics` and `test_catalog_runner`: 314 passed. `ruff check` and `ruff format` on the changed files: clean. `mypy` on the two changed modules and the new test file: no issues.
- Through `bash tools/heavy.sh --log t9-<name>`, each exit 0:
  - `uv run pytest` (`t9-pytest`): **3137 passed, 19 skipped, 58 deselected** in 399 s. Coverage 93 % in total, 99 % for `apply/catalog_read.py` (missed 367, 500, 770, 778, all uncovered before t9) and for `apply/woocommerce.py` (missed 221, also uncovered before).
  - `uv run mypy` (`t9-mypy`) and `uv run mypy --platform linux` (`t9-mypy-linux`): no issues in 96 source files.
  - `uv run bandit -r backend` (`t9-bandit`): no issues at any severity. The 17 `nosec` skips were there before; t9 adds none.
  - `uv run ruff format --check` (`t9-ruff-format`): 209 files already formatted. `uv run ruff check` (`t9-ruff`, the one full lint): all checks passed.
- `uv.lock` unchanged; no package added. No request went anywhere but `httpx.MockTransport`.

**Not verified**
- A real stall on a real socket. The tests raise `httpx.ReadTimeout` from a fake body stream after some chunks, which is where httpx raises it during `iter_raw`. That `HTTPTransport.handle_request` returns once the headers are in (so a real stall counts as "headers yes") follows from httpx streaming, but no real server was used.
- Real stores' `Server`, `cf-ray`, `cf-cache-status` and `Set-Cookie` headers (the owner's L1 runs will show them).
- `pytest -m windows`, pip-audit (no package changed), the release build (the lead runs it at integration: `backend/shelfsync` ships).

**Open questions (for the lead, before item 3)**
1. **The 10-minute bound with a smaller `per_page`.** `STORE_SECONDS` (600 s) still bounds one store's read, and `read_catalog` already takes `store_seconds`. At `per_page 25`, a store has four times as many requests, each at least 1 s apart, so a large store may reach the bound before the end. Should L1 also raise `store_seconds` (and if so, to what), or does `--per-page` keep the 10 minutes? The brief doesn't say, so I didn't guess.
2. Item 3's summary counts "timed out with and without headers". With these records that is `outcome == "timeout"` split on `headers`. Nothing more is needed from the reader unless the analyst wants it.

### Analyst (Opus 5.5 high): CHANGE
Safety is clean and nothing built is wrong, but the records can't yet separate what the PW reads must show. Pasted by the builder from the lead's message, one line per finding with the lead's decision (all accepted):
1. Medium, the stage of a stall. **Lead:** `FactsTransport` sets httpcore's `trace` extension to a callback that keeps only the event name (from a fixed set) and a monotonic time, never `info`. `Attempt` gains `stage` (`connect|tls|send|headers|body|done`), `new_connection`, `headers_ms`, and `error` (`connect_timeout|read_timeout|write_timeout|pool_timeout|connect_error|read_error|protocol_error|other`). The mapping is tested directly, and so is that `info` is never kept.
2. Medium, the shape of a trickle. **Lead:** `FactsTransport` wraps `response.stream` in a counting stream and records `first_byte_ms`, `longest_gap_ms` and `declared_bytes` (`Content-Length` as a number, None when chunked). Check that replacing the stream works in httpx 0.28.1, and test it.
3. Medium, a connection dropped mid-body loses its bytes. **Lead:** finding 2's counting stream counts them; no further `woocommerce.py` change.
4. Medium, one attempt can use up the whole store bound. **Lead:** an L1-only `attempt_seconds` (Lead (proposed) 120 s). `client.get` gets `min(store deadline, attempt start + attempt_seconds)`, and each timed-out attempt is labelled `ended` = `read_timeout|attempt_bound|store_bound`. The runner sets none.
5. High for the diagnosis, the 30 s read timeout (the research reads used 90 s). **Lead:** `WooClient(read_seconds=READ_SECONDS)`, accepted only from 30 to 120 and set only by L1's `--read-seconds`. Test that no app caller sets it and that Test connection is unchanged. This widens the brief's one allowed `woocommerce.py` change (the lead's decision).
6. Low, missing fixed-word facts. **Lead:** add a `content_type` word (`json|html|other|none`), whether `cf-mitigated` and `retry-after` are present, which origin-hint header names are present (from a fixed list), and `waited_ms` per attempt.
7. Low. **Lead:** L1's `--per-page` is restricted to 25, 50 or 100; the reader keeps 25–100.
8. Low. **Lead:** `FactsTransport.handle_request` refuses a non-GET itself.
9. m3.1 §7 is on `main`. **Lead:** handled at integration (not the builder's).
- **The lead's earlier decision stands:** with `--per-page` below 100, L1 scales the store bound to 600 s × 100 / per_page (answers open question 1).

## 3. Builder report

## 4. Review

## 5. Integration notes

## 6. Handover
_(lead, 2026-11-17, about 23:05 IST)_ Brief written on `feat/t9-l1-diagnostics`; the builder starts on it. **Next:** its early report, the analyst's check, the rest, the review; then PW reads by the owner, one setting at a time, each with the owner's go-ahead.
