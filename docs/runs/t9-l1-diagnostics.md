Status: open (approved 2026-11-18; PR to follow)
Tier: B (12 §2: catalog), plus `security-review` by the reviewer (it touches `apply/`, 09 §3)
Usage: lead `claude-opus-5-5/high` [start-session] (PC): 5-h 15 % at the brief (2026-11-17, about 23:05 IST). builder `claude-opus-5-5/high` [none; Context7 for httpx, a tool] (five rounds: to the early check, the analyst's additions and item 3, review 1 fixes, review 2 fixes, the re-check's low); analyst `claude-opus-5-5/high` [none: no 09 §3 skill fits an early check]; reviewer `claude-opus-5-5/high` [code-review, security-review] (+ its read-only `general-purpose` helper) (review 1); a new reviewer `claude-opus-5-5/high` [security-review, code-review] (+ helper) (review 2 and two re-checks). 5-h 15 → 23 % before the 00:00 IST reset, then 2 → about 12 %; weekly (all models) 82 → 85 %. From `node tools/model-audit.mjs 2026-11-17`: every run Opus 5.5 at high; the "no skill loaded" flags are the builder and the analyst, for whom no 09 §3 skill fits; one agent at a time throughout, the owner asleep from about 23:15 IST ("keep working")

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

### Builder (Opus 5.5 high), 2026-11-18: the analyst's findings 1–8 and item 3

**Skills and tools:** as in §2. For the stream and trace questions I read httpx 0.28.1 and httpcore 1.0.9 in `.venv`: `_models.py` (`iter_raw` and `close` use `self.stream`), `_client.py` (the client itself replaces `response.stream` with `BoundSyncStream` right after `handle_request`), `_transports/default.py` 247, and httpcore's `_trace.py`, `_sync/connection.py` and `_sync/http11.py` (the event names). No skill applies beyond §2's.

**Commits** (after §2's `7a5c9fb`, `96b9d6d`, `a5e680a`; not pushed):

| Commit | What |
|---|---|
| `6e53a0e` | `docs(runs)`: the analyst's findings and the lead's decisions in §2 |
| `c67a641` | `feat(catalog)`: the stage of a stall, the shape of a trickle, the attempt bound, the read timeout, more facts, and `FactsTransport`'s own GET check (findings 1–6, 8) |
| `484ef02` | `feat(catalog)`: L1's `--trace`, `--no-meta`, `--per-page`, `--read-seconds` and the timing summary (item 3, finding 7) |

**Files changed in this round:** `backend/shelfsync/apply/catalog_read.py`, `backend/shelfsync/apply/woocommerce.py` (finding 5 only: `read_seconds`), `backend/shelfsync/catalog/report.py`, `tests/test_catalog_diagnostics.py` (44 tests in all, 116 cases), `tests/test_catalog_report.py` (11 new tests, 22 cases), `tests/report_harness.py`, this file. Nothing else; `uv.lock` unchanged.

**How each finding was done**
1. **The stage of a stall.** `FactsTransport.handle_request` sets `request.extensions["trace"]` to a per-request `_WireRecorder.trace(name, info)`.
   - It never reads `info`. It splits the name into `<base>.<phase>`, keeps only bases in a fixed six-entry table (httpcore's `connection.connect_tcp`, `connection.start_tls`, `http11.send_request_headers|body`, `http11.receive_response_headers|body`) and phases `started|complete|failed`, and notes the time.
   - `started` or `failed` sets `stage`. `connect_tcp.started` sets `new_connection`. `receive_response_headers.complete` sets `headers_ms`. `receive_response_body.complete` sets `stage done`.
   - `error` comes from the exception the transport or the body stream caught (its class only, through a fixed table), never from `info["exception"]`.
   - Tested: the mapping directly, through a fake that fires httpcore-named events (MockTransport fires none); unknown or malformed names are ignored; and `info` is never kept (a weak reference to the `info` object is dead after the calls, and no repr holds the key, the secret or the address).
2. **The shape of a trickle.** `FactsTransport` replaces `response.stream` with `_CountingStream`, which passes every chunk on as it is and records `first_byte_ms`, `longest_gap_ms`, `received` and `declared_bytes` (`Content-Length` as a number, None when absent or not plain digits). This works in httpx 0.28.1: the client wraps the stream once more in `BoundSyncStream`, and `iter_raw` and `close` use `self.stream`. Tested: the reader gets the same result through it, and the bytes counted equal the bytes read.
3. **A dropped connection's bytes.** The counting stream counts what came. With a `FactsTransport`, `Attempt.body_bytes` and `Attempt.headers` come from the `Wire`, so an `unreachable` mid-body reports its bytes and `headers yes`. `woocommerce.py` has no further change for this.
4. **The attempt bound.** `read_catalog(attempt_seconds=None)`. With a value, the session reads the clock and gives `client.get` the earlier of the store's deadline and the attempt's start plus `attempt_seconds`. A timed-out attempt gets `ended` by comparing the clock with those deadlines: `store_bound`, `attempt_bound`, else `read_timeout`. With None (the app), there is no extra clock read and the deadline is unchanged. Tested: a trickle ends at the attempt bound and the retry reads on; the bound is the deadline the client gets (read timeout 20 s at `attempt_seconds=20`); a plain read timeout; the store's bound; the slack; and `attempt_seconds ≤ 0` refused.
5. **The read timeout.** `WooClient(read_seconds=READ_SECONDS)` takes 30–120 (`READ_SECONDS_RANGE`, else `ValueError`) and uses it in place of the constant. Tested: 30, 90 and 120 accepted (the request's read timeout is that value), 29.9 and 121 refused. An AST scan of `backend/shelfsync` finds `read_seconds=` and the L1 options passed only by `catalog/report.py`; the reader only hands its own on. The Test connection tests are unchanged and pass.
6. **More facts.** `ResponseFacts` gains:
   - `content` (`json` for `application/json` or `application/…+json`, `html` for `text/html`, else `other`, `none` when absent);
   - `cf_mitigated` and `retry_after` (present or not);
   - `hints`, the names present from the fixed list of seven, in that order.

   `Attempt` gains `waited_ms` (measured around the wait before it: the spacing, a back-off or a `Retry-After`), `ended`, and `wire` (the whole `Wire`).
7. **`--per-page`** accepts only 25, 50 or 100 (argparse `choices`); the reader keeps 25–100.
8. **`FactsTransport` refuses a non-GET itself** (`NonGetRefused`) before anything is recorded or sent.

**Item 3 (`catalog/report.py`)**
- **Settings.** `Settings` is built from the arguments (`settings_from`): `ListingShape(per_page, 4,000 // per_page, not --no-meta)` (`_Shape` became the public `ListingShape`), the store's bound at 600 × 100 / per_page, `read_seconds`, `ATTEMPT_SECONDS = 120` (Lead (proposed)), and `trace`.
- **The plan lines** start with a `Settings:` line: per page, most pages, fields, the store's bound, the attempt bound, the read timeout, and whether `--trace` is on. The products request comes from `shape.params(1)` (`listing_params`), and the read is given the same shape's values.
- **The read.** Every store is read through `FactsTransport(inner)` (the real `httpx.HTTPTransport()`, or a test's) with an observer. With `--trace`, the observer prints one line per attempt as it ends: local `HH:MM:SS`, the store code, `#n` (the request number in that store's read), what and page, the try, the outcome and status, `ended`, `stage` and `error`, the connection (`new`, `reused`, or `unknown` when no trace event came), the headers, first-byte and longest-gap times, bytes received of declared, the time taken, the wait, and the facts.
- **`--no-meta`** prints `meta not asked (--no-meta)` in place of the meta counts.
- **The timing summary** comes after the cross-store lines, one block per store read:
  - requests, the median and slowest attempt, the largest page;
  - timeouts after the headers and before them or not known;
  - the request number of the first stall;
  - timeouts by stage and by what ended them.
- **Tests:**
  - a fresh-process run with every option, where the harness fires trace events whose `info` holds the request, an address with both keys in its query and the `Authorization` value, and every answer carries marked cookie values, a hashed WordPress cookie name, a `cf-ray`, a server and a cache text. No marker, host, key, `Authorization` value, `consumer_` or `LHR` appears, no trace line holds `? = / @ &`, and one trace line is matched in full;
  - in process: the list shown is what is sent, for four option sets; each store gets the run's settings (a spy: store bound 600, 1,200 or 2,400; most pages 40, 80 or 160; `attempt_seconds` 120; a `FactsTransport`; the client's read timeout 30 or 90);
  - argument ranges; the trace lines' order and request numbers; no trace lines without `--trace`; no timing line for a store without keys;
  - `trace_line` and `timing_lines` exactly, on built attempts.

**Choices I made (Lead (proposed) if the lead keeps them)**
1. `BOUND_SLACK_SECONDS = 0.25`: a timeout within 0.25 s of a bound is labelled by the bound, for a system timer that wakes a little early. `read_timeout` also covers a connect timeout before any bound; the `error` word tells them apart.
2. `headers_ms` comes from the trace's `receive_response_headers.complete` when it fires, else the moment `handle_request` returned (the connection pool returns right after the headers), so test transports have it too.
3. `longest_gap_ms` counts the wait from the last chunk to the body's end or failure, so a final stall shows (the loopback probe's trickle: 1,013 ms for a 1 s timeout). The wait from the headers to the first byte isn't a gap: it is `first_byte_ms − headers_ms`. An empty chunk isn't a byte.
4. `Attempt.wire` carries the whole `Wire` rather than flattening its fields into `Attempt`; `Attempt.facts` stays for §2's callers.
5. The trace table holds HTTP/1.1 names only: `WooClient` doesn't turn HTTP/2 on.
6. L1 always reads through `FactsTransport` with the observer and the 120 s attempt bound, so the timing summary prints on every run; `--trace` only adds the per-attempt lines. The app never does either.
7. `connection unknown` when no trace event came (a test transport), since `new_connection False` alone can't tell "reused" from "not traced".
8. "First stall" means the first attempt whose outcome is `timeout`.
9. `--read-seconds` takes whole seconds; `WooClient` takes any number from 30 to 120.

**Commands run and their results** (all with `UV_PYTHON_DOWNLOADS=never`, `--locked`)
- While working: `pytest --no-cov` on `test_catalog_report`, `test_catalog_diagnostics`, `test_catalog_read`, `test_woocommerce_client`, `test_catalog_runner` and `test_stores_api`: 534 passed. Two mutation checks, reverted afterwards: keeping `info` in the trace callback, and a slack of 0, each made its test fail; the slack test first used the constant itself and didn't catch it, so it now uses a literal 0.1 s. `ruff check`, `ruff format` and `mypy` on each changed file: clean.
- A loopback probe (127.0.0.1 only, a scratch script, not committed) with `FactsTransport(httpx.HTTPTransport())` on a real httpcore connection:
  - a first request opens a new connection, and the next reuses it (`stage done`);
  - a trickle ends `stage body`, `read_timeout`, 4 of 50 bytes, longest gap 1,013 ms;
  - a silent server ends `stage headers`, `read_timeout`, no facts;
  - a connection dropped mid-body keeps its 5 bytes, with `stage body` and error word `protocol_error` (httpx raises `RemoteProtocolError` there; `WooClient` maps it to `unreachable`).
- Through `bash tools/heavy.sh --log t9-fix-<name>`, each exit 0:
  - `uv run pytest` (`t9-fix-pytest`): **3212 passed, 19 skipped, 58 deselected** in 391 s. Coverage 94 % in total. `apply/catalog_read.py` 99 %: of the new code only the branch for a non-sync body stream (434→436) isn't taken, which a sync client never gives; 580, 745, 1029 and 1037 were uncovered before t9. `apply/woocommerce.py` 99 % (228, uncovered before). `catalog/report.py` 92 %: its missed lines are the lock-error, no-store and `__main__` paths, uncovered before t9.
  - `uv run mypy` (`t9-fix-mypy`) and `uv run mypy --platform linux` (`t9-fix-mypy-linux`): no issues in 96 source files.
  - `uv run bandit -r backend` (`t9-fix-bandit`): no issues; still the 17 `nosec` skips from before t9.
  - `uv run ruff format --check` (`t9-fix-ruff-format`): 209 files already formatted. `uv run ruff check` (`t9-fix-ruff`, the one full lint): all checks passed.

**Not verified**
- Against TLS and a real store: the probe ran over plain HTTP on loopback, so `start_tls` events, the real stores' headers, and how PluginWay stalls are for the owner's L1 runs.
- The real `datetime.now().astimezone()` zone name: L1 prints `HH:MM:SS` local time with no zone, as the brief's example does.
- `pytest -m windows`, pip-audit (no package changed), the release build (the lead's, at integration: `backend/shelfsync` ships).
- L1 against the real installed database and Credential Manager (the owner's step, outside Claude).

**Open questions**
1. The summary prints on every L1 run, and the 120 s attempt bound always applies in L1 (choice 6). If the lead wants a plain run to match m3.1's L1 exactly (no attempt bound), that would need a flag; I didn't add one unasked.
2. The trace lines go to stdout as the read runs. The read's own log line still goes to stderr, so with `Tee-Object` both reach the log only if the owner's command captures both streams. L1's command for the owner isn't on this branch (m3.1 §7 is on `main`), so I couldn't check it: it should end `2>&1 | Tee-Object …`, as the repo's other owner commands do (`runbooks/m1b-exit-test.md`). I changed no docs outside the brief's files.

### Fixes after review 1 (builder, Opus 5.5 high, 2026-11-18)
Worked from the lead's rebase (`c5b107d`). Commits: `80f214d` (review 1 in §4), `c69d32f` (every fix with its tests), and this report.

| # | Fix | Tests |
|---|---|---|
| 1 | `_Session._ended(tried, wire)` follows the lead's rule. It names a bound only when `WooClient`'s own between-chunks check fired (a `timeout` whose `Wire.error` is None) or when the timeout fired within `BOUND_SLACK_SECONDS` of the deadline `client.get` was given (on either side). The bound named is that deadline's: `store_bound` when it was the store's, else `attempt_bound`. Otherwise it is `read_timeout`. Without a `facts` transport only the slack test can be made (documented). No `woocommerce.py` change for this. The Settings line now reads "… at most N s for each store's read and 120 s for one request, each plus up to the read timeout after the last byte …". | `test_catalog_diagnostics.py`: both reviewer probes, each a byte every 10 s then a stall: read 30 s to 110 s then 30 s, and read 90 s to 40 s then 90 s. Both give `read_timeout`, error `read_timeout`, gap 30,000 or 90,000 ms, took 140,000 or 130,000 ms. The same stall past a 100 s store bound gives `read_timeout`, and the read then ends between requests. The client's own check gives `attempt_bound` with the attempt bound and `store_bound` without one; without facts it gives `read_timeout`. Slack: 0.1 s and 0 s early give the bound, 0.5 s early gives `read_timeout`, with and without facts. Restoring the old rule failed four of these tests. The reviewer's own probes now print `ended= read_timeout`. |
| 2 | Each store's timing lines are printed right after its counts. Ctrl+C during a store's read prints its summary from the attempts so far (`read stopped by Ctrl+C`), then stops as before. | `test_catalog_report.py`: `…summary_follows_its_counts_before_the_next_store` (GF's summary before PW's counts, PW's before "Across"); `test_ctrl_c_during_a_store_prints_what_was_gathered_so_far` (GF's summary, PW's partial summary with 1 request, the three trace lines already printed, exit 1, "Stopped. Nothing was saved."). |
| 3 | `read_ended(attempts, result)` puts how the read ended at the head of the summary: `ok`, the reason, `stopped by Ctrl+C`, or for a `timeout` the reader's own checks raised, `timeout, between requests at the store's bound`. A timeout ended by an attempt itself (its fourth try, or the one that auto-paused the store) stays `timeout`. | `test_how_the_read_ended_names_a_timeout_between_requests` (8 cases), and `test_a_read_ended_by_the_wait_before_a_request_is_reported_between_requests` (the real reader: `store_seconds=0.5`, the spacing wait passes it, `observe` saw one `ok`, and the summary says between requests). |
| 4 | The Settings line ends "times are local, <zone>" (`now().astimezone().tzname()`, "zone unknown" if None). `Settings` gains `zone`. | `test_the_settings_line_names_the_local_zone_and_the_bounds_truthfully`; the fresh-process test matches the whole line. |
| 5 | `_read_one` closes the `FactsTransport` (and so the inner transport) when `WooClient` refuses its arguments, then re-raises. | `test_the_transport_is_closed_when_the_client_refuses_its_arguments` (an `http://` address: `ValueError`, transport closed). |
| 6 | `FactsTransport.seen()` removed: only tests used it, and `_emit` uses the `Wire`. `Attempt.what` and `Attempt.facts` are now properties derived from `page` and `wire`. `woocommerce.declared_length` (plain ASCII digits, else None; more than 18 digits reads as `DECLARED_MAX` = 10^18) is shared by `WooClient.get`'s cap check and `Wire.declared_bytes`. The cap behaves as before, except that a `Content-Length` over 4,300 digits now gets `bad_response` where the old `int()` raised a `ValueError` out of the read (checked: Python 3.15 refuses to convert more than 4,300 digits). | `test_woocommerce_client.py`: `test_the_shared_content_length_reading` (12 cases) and `test_the_cap_on_a_declared_length_is_unchanged` (at the cap, over it, 19 and 5,000 digits, not a number). The diagnostics tests adapted: no `seen()`, a 20-digit length reads as `DECLARED_MAX`, `" 5"` reads as None. |

**Choices in this round (Lead (proposed) if kept)**
- The slack applies on both sides of the deadline: a timer that wakes a little early or a little late.
- A partial summary is printed only on `KeyboardInterrupt`, as decided. Any other exception still loses only the store being read; every earlier store's summary is already printed.
- "Largest page" in the summary is now the largest products answer read `ok` among the attempts, so a partial summary has it too. Before, it was `CatalogRead.largest_page_bytes`; the two agree for a read that worked.

**Commands run and their results** (all with `UV_PYTHON_DOWNLOADS=never`, `--locked`)
- While working: `pytest --no-cov` on the report, diagnostics, reader, client, runner and stores-API tests: 574 passed. The mutation check above. The reviewer's two probes. `ruff check`, `ruff format` and `mypy` on each changed file: clean. mypy's note on `tests/test_woocommerce_client.py` line 367 (an unused `type: ignore`) was there before t9; tests aren't in the project's mypy set.
- Through `bash tools/heavy.sh --log t9-fix2-<name>`, each exit 0:
  - `pytest`: **3252 passed, 19 skipped, 58 deselected** in 371 s. Coverage 94 % in total.
    - `apply/catalog_read.py` 99 %: the only new code not covered is the non-sync-stream branch; the other missed lines were uncovered before.
    - `apply/woocommerce.py` 99 %: line 243, uncovered before.
    - `catalog/report.py` 93 %: the lock-error, no-store and `__main__` paths, uncovered before.
  - `mypy` and `mypy --platform linux`: no issues in 96 files.
  - `bandit -r backend`: no issues (17 `nosec` skips, unchanged).
  - `ruff format --check`: 209 files formatted. `ruff check` (the one full lint): all checks passed.
- No background job is left running; `uv.lock` unchanged; no network beyond loopback.

**Not verified:** as before (TLS and real stores; `-m windows`; pip-audit; the release build at integration). The zone name is what Windows' `tzname()` gives (for example "India Standard Time"); it was checked only against this PC's own zone in the tests.

### Fixes after review 2 (builder, Opus 5.5 high, 2026-11-18)
Commits: `6fd0872` (review 2 in §4), `6305400` (the fixes and their tests), `26482f6` (a stale test comment), `319fc22` (one more test), and this report.

| # | Fix | Tests |
|---|---|---|
| 1 | `_Session._ended` now decides from facts, never from how far the clock is from the deadline. `WooClient.get` sets its timeouts once, from the deadline it is given: read, write and pool at `min(read_seconds, remaining)`, connect at `min(10 s, remaining)`. So the deadline (`store_bound` when it was the store's, else `attempt_bound`) is named when (a) WooClient's own between-chunks check fired (`Wire.error` None), or (b) the deadline shortened the timeout (`deadline - started < read_seconds`) and the error isn't `connect_timeout`. Otherwise it is httpx's own timeout, by its word. **The slack is gone:** nothing compares the clock with a deadline any more, so `BOUND_SLACK_SECONDS` and its test were removed. The session reads the client's read timeout from `WooClient._read_seconds`, the one private read (commented); `woocommerce.py` itself is unchanged for this. | `test_identical_stalls_on_new_and_kept_alive_connections_get_one_label`: the reviewer's probe, four stalls alternating a new TLS connection (0.6 s) with a kept-alive one. Read 120 s with bound 120 s gives `read_timeout` ×4 (120 isn't below 120); read 30 s with bound 120 s gives `read_timeout` ×4; read 120 s with bound 60 s gives `attempt_bound` ×4. `test_a_stall_whose_timeout_the_store_bound_shortened_is_store_bound`: new and kept-alive connections both give `store_bound`. Mutation checks: `<` to `<=`, and dropping the connect exception, each failed a test. The reviewer's two probes now print one label each. |
| 2 | `ENDED_WORDS` = `connect_timeout`, `read_timeout`, `write_timeout`, `pool_timeout`, `attempt_bound`, `store_bound`. httpx's own timeout is named by its word (`read_timeout` when there is no `Wire`, or for a timeout httpx didn't name). The summary gains `by error:` (every attempt's error word, timeouts and others alike). | `test_a_connect_timeout_is_ended_connect_timeout` (far from the bound, and with the bound shortening it); `test_httpxs_other_timeouts_are_their_own_words` (write, pool, unnamed); `test_without_a_wire_a_timeout_is_read_timeout_unless_the_bound_shortened_it`; `test_the_timing_summary_counts_timeouts_by_stage_by_what_ended_them_and_by_error` (with a `connect_timeout` trace line); the fresh-process test checks `by error: none`. |
| 3 | On Ctrl+C, `_read_one` prints one line for the request in flight from `FactsTransport.take_in_flight()` (its `Wire` so far and how long it has run): `GF #2 in flight when stopped: stage …, 320 of 9,000 bytes, longest gap 4,000 ms, 10.5 s so far`. The store's partial summary follows. With no request in flight there is no line. | `test_ctrl_c_inside_a_body_prints_the_request_in_flight` (an interrupt raised inside the body stream), `test_ctrl_c_during_a_wait_has_no_request_in_flight`, and `test_a_request_in_flight_gives_its_wire_so_far_once`. |
| 4 | `DECLARED_MAX`'s comment above it; `trace_line` uses `Attempt.what`; `ERROR_WORDS` built from `_ERROR_CLASSES` plus `"other"`; one `ms_between(later, earlier)` helper for every millisecond difference (`_WireRecorder`, `_emit`, the wait before an attempt). There is no slack test to extend, since the slack is gone. | `test_the_words_are_built_from_one_table` (the word tables and `ms_between`). |
| 6 | No change, as decided. The cap is unchanged but refuses slightly more: a `Content-Length` of more than 18 digits reads as `DECLARED_MAX`, so one made of leading zeros (a small number written long) is now refused where the old `int()` would have read it as small. A value over 4,300 digits is refused where it used to raise. | (review 1's `test_the_cap_on_a_declared_length_is_unchanged`) |

**Commands run and their results** (all with `UV_PYTHON_DOWNLOADS=never`, `--locked`)
- While working: `pytest --no-cov` on the report, diagnostics, reader, client, runner and stores-API tests: 582 passed, then 57 report tests after the last test was added. The mutation checks above. The reviewer's `read120_probe.py` and `connect_probe.py`. `ruff check`, `ruff format` and `mypy` on each changed file: clean.
- Through `bash tools/heavy.sh --log t9-fix3-<name>`, each exit 0:
  - `pytest` on `6305400`'s code (`t9-fix3-pytest`): 3260 passed, 19 skipped, 58 deselected. Coverage 94 %; `catalog_read.py` 99 % (only the non-sync-stream branch is new and uncovered), `woocommerce.py` 99 %, `report.py` 93 %. Its one new partial branch, Ctrl+C with no request in flight, is covered by `319fc22`'s test.
  - `pytest` on the final tree (`t9-fix3-pytest-final`): **3261 passed, 19 skipped, 58 deselected** in 377 s. Coverage 94 %; `report.py` 93 %, its missed lines all uncovered before t9 (the in-flight branch is now covered).
  - `mypy` and `mypy --platform linux`: no issues in 96 files. `bandit`: no issues (17 `nosec` skips, unchanged). `ruff format --check`: 209 files formatted. `ruff check` (the one full lint): all checks passed.
- No background job is left running; `uv.lock` unchanged; no network beyond loopback.

**Not verified:** as before (TLS and the real stores; `-m windows`; pip-audit; the release build at integration).

### Fix after the re-check of review 2 (builder, Opus 5.5 high, 2026-11-18)
- **The silence still open** (`0dfbd58`). `FactsTransport.take_in_flight` now returns an `InFlight`: the `Wire` so far, `so_far_ms`, and `quiet_ms` since `quiet_since` (`last byte`, else `headers`, else `request start`), all on the recorder's clock. L1's line reads `GF #2 in flight when stopped: stage unknown, 320 of 9,000 bytes, longest gap 4,000 ms, 6,000 ms since the last byte, 10.5 s so far`, the longest gap unchanged. Tests: the Ctrl+C-inside-the-body test now expects 6,000 ms; `test_ctrl_c_before_any_body_byte_counts_the_silence_from_the_headers` (headers, then 8 s with no byte: `8,000 ms since the headers`); and `test_a_request_in_flight_with_no_byte_yet_counts_its_silence_from_the_headers_or_its_start` (5,000 ms since the headers; 3,000 ms since the request's start for Ctrl+C inside `handle_request`).
- **The optional `WooClient.read_seconds` property: not taken.** `test_a_client_that_is_asked_to_write_cannot` pins WooClient's public members to exactly `get` and `close` ("nothing else until M5"), and a new public name fails it. Widening that GET-only contract is the lead's call, not mine, so the session keeps the commented read of `client._read_seconds`. If the lead wants the property, the contract test's set needs `read_seconds` added in the same change.
- Commands (all with `UV_PYTHON_DOWNLOADS=never`, `--locked`):
  - Targeted: `pytest --no-cov` on the report, diagnostics, reader, client, runner and stores-API tests: 585 passed. `ruff format --check`, `ruff check` and `mypy` on the changed files: clean.
  - Through `bash tools/heavy.sh --log t9-fix4-<name>`, each exit 0:
    - `pytest`: **3263 passed, 19 skipped, 58 deselected** in 368 s. Coverage 94 %; `catalog_read.py` 99 % (only the non-sync-stream branch is new and uncovered), `woocommerce.py` 99 %, `report.py` 93 % (missed lines all uncovered before t9).
    - `mypy` and `mypy --platform linux`: no issues in 96 files. `bandit`: no issues (17 `nosec` skips, unchanged). `ruff format --check`: 209 files formatted. `ruff check`: all checks passed.
  - No background job left running; `uv.lock` unchanged; no network beyond loopback.

## 4. Review

### Review 1, reviewer (Opus 5.5 high): SEND BACK
1 high, 1 medium, 4 low; the security review found nothing. Pasted by the builder from the lead's message, one line per finding with the lead's decision:
1. High: `ended` mislabels plain read timeouts after a bound. httpx's read timeout restarts on every socket read, so a body that trickles and then stalls near the end of an attempt fails `read_seconds` after its last byte, past the deadline, and `_ended` names the bound. Reviewer's probes: read 30 s, bound 120 s, a chunk every 10 s to 110 s, then a stall: `attempt_bound`, took 140,000 ms; `--read-seconds 90`, trickle to 40 s, then a stall: `attempt_bound`, took 130,000 ms. **Lead:** label a bound only when the timeout fired within `BOUND_SLACK_SECONDS` of that deadline (the httpx timeout was cut short by it), or when WooClient's own between-chunks deadline check fired (a `timeout` whose `Wire.error` is None); otherwise `read_timeout`. No further `woocommerce.py` change. Word the Settings line truthfully ("120 s for one request, plus up to the read timeout after its last byte"). Tests for both probe cases and the same case at the store bound.
2. Medium: Ctrl+C or an exception loses every timing summary. **Lead:** print each store's timing lines straight after its store lines; on `KeyboardInterrupt` print the attempts gathered so far for the store being read (summary lines; the trace lines are already printed as they happen). Test both.
3. Low: timeouts from the reader's own bound checks (`_pause`, the deadline check before a request) never reach `observe`. **Lead:** one summary word saying the read ended between requests at the store's bound (the `CatalogRead` reason next to the counts), with a test.
4. Low: trace times have no zone name. **Lead:** print the zone once on the Settings line (`astimezone().tzname()`), per CLAUDE.md.
5. Low: `_read_one` builds the transport before `WooClient` checks its arguments. **Lead:** close the transport when construction fails, with a test.
6. Low, cleanups. **Lead:** remove `FactsTransport.seen()` if only tests use it; make `Attempt.facts` and `what` derived where they repeat `wire.facts` and `page`, if that stays simple; share one `Content-Length` parsing helper between `_declared` and WooClient's cap check (`woocommerce.py` only calls the shared helper; behaviour unchanged, tested).

### Review 2 (second full review), new reviewer (Opus 5.5 high): APPROVE
2 medium, 4 low; review 1's high confirmed fixed. Pasted by the builder from the lead's message, one line per finding with the lead's decision:
1. Medium: `ended` differs for identical stalls when the deadline shortened the timeout. `WooClient.get` sets `min(read_seconds, remaining)` once and httpx applies it per phase, so with `--read-seconds 120` a stall before the headers fires at the deadline plus the connect and TLS time: past the 0.25 s slack on a new connection, within it on a reused one (probe: `read_timeout, attempt_bound, read_timeout, attempt_bound`). **Lead (the reviewer's first option):** the session knows `started`, the deadline it passed and the client's read timeout, so it can tell whether the deadline shortened the timeout (`deadline - started < read_seconds`). Label by that bound when WooClient's own between-chunks check fired (`Wire.error` None), or when the timeout was shortened by it and the error isn't `connect_timeout`; otherwise the error word (item 2). This replaces the slack guess for that case; keep the slack only where it is still needed, and say where. No further `woocommerce.py` change. Tests: the probe's new/reused alternation gives one label; the same near the store bound.
2. Medium: a connect timeout is reported as `ended read_timeout`. **Lead:** for httpx's own timeouts `ended` is the error word itself (`connect_timeout`, `read_timeout`, `write_timeout`, `pool_timeout`), and `read_timeout` when there is no `Wire`. Update `ENDED_WORDS`, the trace and the summary, and their tests; add a `by error:` line to the summary.
3. Low: Ctrl+C during an attempt loses that attempt. **Lead:** on `KeyboardInterrupt` also print one line for the request in flight from `facts.take()`: stage, bytes, longest gap, how long so far. Test with an interrupt raised inside the body stream.
4. Low, cleanups. **Lead:** put `DECLARED_MAX`'s comment above it; `trace_line` uses `Attempt.what`; build `ERROR_WORDS` from `_ERROR_CLASSES` plus `"other"`; one helper for the repeated `max(0, round((a - b) * 1000))`; the slack test covers late cases too if the slack remains.
5. The owner's command ends `2>&1 | Tee-Object …`. **Lead:** the lead's (not the builder's).
6. A `Content-Length` longer than 18 digits with leading zeros is now refused. **Lead:** no change; note it in §3 under "cap unchanged, refuses slightly more".

#### Re-check of review 2's fix diff, same reviewer (Opus 5.5 high): APPROVE
One new low. **Low:** the in-flight line leaves out the silence still open when Ctrl+C is pressed (`KeyboardInterrupt` isn't an `Exception`, so `_CountingStream` never calls `body_ended`); the builder's own test showed `longest gap 4,000 ms, 10.5 s so far` after a 6 s final silence. **Lead:** `take_in_flight` also measures the wait since the last byte (or the headers, or the request's start when no byte came) on the recorder's clock, and the line prints it as `N ms since the last byte`, the longest gap kept as is; update the test to expect 6,000 ms and add the no-byte-yet case. Optional: a read-only `WooClient.read_seconds` property used by the session in place of `_read_seconds`.

## 5. Integration notes
_(lead, 2026-11-18)_
- **How it came together:** the builder worked in `worktree-agent-a893c6c188f430cb7`; the lead rebased its first rounds onto `main` once #66 had merged (so the run file sits beside m3.1 §7), and fast-forwarded the later rounds.
- **Reviews:** analyst CHANGE (findings 1–8 accepted, widening the brief: httpcore's `trace` extension, a counting body stream, an L1-only 120 s attempt bound, `WooClient(read_seconds=30)` accepting 30–120 set only by L1); review 1 SEND BACK (1 high: `ended` named a bound for a plain read timeout firing after it), fixed; review 2 by a new reviewer APPROVE (2 medium: `ended` differed for identical stalls when the deadline shortened the timeout, and a connect timeout read as `read_timeout`), fixed; two re-checks APPROVE (the last added "N ms since the last byte" to the Ctrl+C line).
- **The lead's decisions beyond the brief:** the store bound scales to `600 s × 100 / per_page`; `--per-page` only 25, 50 or 100; `Content-Length` kept as a number; `ended` is the timeout's own word unless the deadline shortened it or WooClient's own check fired; no `WooClient.read_seconds` property (it would widen the GET-only contract test); every L1 run now goes through the facts transport with the 120 s attempt bound, so a plain L1 no longer matches m3.1's run 1 exactly (a single request can't hold a store for 8 minutes any more).
- **Checks:** the builder's last full run (`heavy.sh --log t9-fix4-…`): pytest 3263 passed, 19 skipped, 58 deselected, coverage 94 %; mypy and `mypy --platform linux` clean (96 files); ruff check and format clean; bandit clean. The lead: `npm run build`; the release build rehearsal (`.logs/t9-release-build.log`): passed (build, smoke test, installer tests, manifest).
- **Not verified:** TLS and the real stores' headers and stalls (the owner's PW reads); the zone name on another PC; `-m windows`.
- **Follow-ups:** none new beyond m3.1 §5's.

## 6. Handover
_(lead, 2026-11-17, about 23:05 IST)_ Brief written on `feat/t9-l1-diagnostics`; the builder starts on it. **Next:** its early report, the analyst's check, the rest, the review; then PW reads by the owner, one setting at a time, each with the owner's go-ahead.

_(lead, 2026-11-18, about 00:45 IST)_ **t9 approved** (the run above); pushed and its PR opened, merging on green. **Next, the owner's PW diagnostic reads**, one setting changed at a time, each with the owner's go-ahead, run in Windows PowerShell outside Claude with ShelfSync quit from the tray:
1. **Read A, the baseline with a trace:** `uv run python -m shelfsync.catalog.report --store PW --trace --yes 2>&1 | Tee-Object -FilePath .logs\l1-pw-a.txt` (default settings: 100 a page, meta asked, 30 s read timeout, 120 s for one request). Its stall line shows the stage (connect, TLS, headers or body), whether the connection was new, the facts (Cloudflare or not, cookies set, content type) and the trickle's shape.
2. **Then one change, chosen from A:** `--no-meta` if the stall is a slow body (slow pages with `meta_data`); `--read-seconds 90` if nothing came within 30 s on a reused connection (a slow origin); `--per-page 25` to see whether the stall follows the request count (about 13–16) or the products; nothing new if A reads in full (load, chance).
3. The lead reads each log, records it here, and once the cause is clear writes m3.2's brief with the reader settings it implies.
