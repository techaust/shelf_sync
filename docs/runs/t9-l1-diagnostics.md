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

## 3. Builder report

## 4. Review

## 5. Integration notes

## 6. Handover
_(lead, 2026-11-17, about 23:05 IST)_ Brief written on `feat/t9-l1-diagnostics`; the builder starts on it. **Next:** its early report, the analyst's check, the rest, the review; then PW reads by the owner, one setting at a time, each with the owner's go-ahead.
