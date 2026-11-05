Status: merged as [#61](https://github.com/techaust/shelf_sync/pull/61) (2026-11-05)
Tier: A (12 §2: `apply/`, the store client)
Usage: lead `claude-opus-5-5/high` [start-session] (PC, side session started by the m2.8 lead): 5-h 5 → 13 %; analyst `claude-opus-5-5/high` [none] (brief: Context7 isn't in its tools, so it read httpx 0.28.1 and idna 3.20 from `.venv`): 5 → 6 %; builder `claude-opus-5-5/high` [none; Context7 for httpx, a tool, not a skill] (build, then the early-check lows): 6 → 12 %; analyst `claude-opus-5-5/high` [none] (early check): 11 → 12 %; reviewer `claude-opus-5-5/high` [security-review, code-review] (+ its built-in read-only `general-purpose` helper, Opus 5.5 high): 12 → 13 %. From `node tools/model-audit.mjs 2026-11-05`: every run Opus 5.5 at high; the three "no skill loaded" flags are the analysts and the builder, for whom no 09 §3 skill fits

# t8-woo-redirect: an unreadable redirect `Location` reads as `redirected`, never as a crash

The follow-up confirmed in [m2.8](m2.8-laragon-test-stack.md) §5 ("Re-check of the fix diff"): ShelfSync's `WooClient` lets a 3xx with an undecodable IDNA `Location` escape as `idna.IDNAError`, and reads a malformed one as `unreachable`. Brief drafted by the analyst, checked by the lead.

## 1. Brief

### PRD IDs
SET-01 (Test connection) and ERR-01 (the health chip shows the reason). Every new test cites both, the same IDs as the modules it tests.

### The bug (m2.8 §3 item 5, §4, §5)
- Even with `follow_redirects=False`, httpx 0.28.1 builds `response.next_request` from `Location`: `httpx/_client.py` `_send_handling_redirects` 985-994, through `_redirect_url` 517-544.
- **`https://xn--a.test/`:** parsing succeeds, then `URL.host` calls `idna.decode` (`_urls.py:188-191`, called from `_client.py:532`), which raises `idna.IDNAError` (a `UnicodeError`). `WooClient.get` doesn't catch it, so `run_read_test` raises. `StoreService.test` (`store_service.py:461-462`) re-raises it into the request and `api/errors.py:63` answers 500 `{"error":"internal"}`. Nothing is saved.
- **`http://[::1`:** `InvalidURL` becomes `RemoteProtocolError` (`_client.py:525-528`), a `TransportError`, so it reads as `unreachable`.

### httpx 0.28.1's order of operations (read in the installed source by the analyst; V58 records it)
- `_send_handling_redirects` runs the `response` hooks (`_client.py:981-982`) before it checks `has_redirect_location` (985) and builds the redirect request (988).
- An exception raised in a hook gets `response.close()` and is re-raised unchanged (997-999); the `request_context` mapping covers only `transport.handle_request` (1013-1014). `_send_handling_auth` (942), `send` (914) and `stream` (868) let it pass.
- So a `ReadRefused` raised in the hook reaches `get` unwrapped with the response closed, and `_read_test`'s `except ReadRefused` catches it.
- `Response.has_redirect_location` (`_models.py:772-792`) is a status in {301, 302, 303, 307, 308} with a `Location` header: the same set as `_REDIRECTS`.

### Decisions (Lead (proposed), routine engineering)
1. **A response hook, not a wider `except`.** A module-level `_refuse_redirect(response)` in `woocommerce.py`, passed as `event_hooks={"response": [_refuse_redirect]}` in `WooClient.__init__`; for a status in `_REDIRECTS` it raises `ReadRefused("redirected", _redirect_host(response.headers.get("location")), response.status_code)`. Catching `UnicodeError` around `stream` can't tell a bad `Location` from a bug, and a malformed one would still arrive as `RemoteProtocolError`. Same pattern as `testenv/seed.py` (`_refuse_redirect`). The inline `_REDIRECTS` check in `get` (177-180) is dead and goes; the `get` and module docstrings say a 3xx is refused in a response hook before httpx reads `Location`.
2. **Statuses unchanged:** exactly `_REDIRECTS`. 300, 304, 305 and 306 keep going to `classify` (`bad_response` with their status); httpx builds no `next_request` for them. A guard test pins `_REDIRECTS` to httpx's set.
3. **No broad catch anywhere else.** `_redirect_host` catches `httpx.InvalidURL, ValueError` (seed's form; `ValueError` covers `UnicodeError` and `IDNAError`); its `try` only parses the store's header. `get` gains no new `except`. `store_service.py` is unchanged: an unexpected error stays a 500, never a saved health.
4. **Other callers:** `WooClient` and `run_read_test` are used only by `store_service.py` and `testenv/laragon.py`; both get the fix with no code change. `SeedClient` already uses a hook.
5. **04-A V58** (the builder adds it) and **06** line 41: after "redirects are never followed" add that a 3xx is refused in a response hook before httpx reads its address, so a malformed one still reads as `redirected` ([04-A V58]). 04 doesn't mention redirects.

### Files
- **Backend (builder):** `backend/shelfsync/apply/woocommerce.py`; `testenv/laragon.py` (remove the `try/except UnicodeError` in `run_check` and call `run_read_test` directly; `ReadOutcome` stays imported for `describe`); `tests/test_woocommerce_client.py`, `tests/test_stores_api.py`, `tests/test_testenv_laragon.py`; `docs/04-architecture-appendix/A-stack-verification.md` (V58); `docs/06-security.md`.
- **Screens (designer):** none. The `redirected` wording without a host already exists (13; m2.5a).

### Tests (failure paths first; each new one is run against the unfixed code first and the failure recorded in §3)
**`tests/test_woocommerce_client.py`** (MockTransport through `FakeWoo`):
- `test_a_redirect_to_an_unreadable_address_reads_as_redirected_with_no_host`: `https://xn--a.test/`, `http://[::1` and `https://user@:99999/`, each with 301 and 307; `(reason, detail, http_status, health) == ("redirected", None, status, "unreachable")`, exactly one request.
- `test_an_unreadable_redirect_on_the_second_get_keeps_the_first_gets_versions`: products answer 302 to `https://xn--a.test/`; `redirected`, 302, `wc_version == "9.4.1"`.
- `test_get_raises_the_hooks_refusal_unwrapped_and_closes_the_answer`: `WooClient.get` directly raises `ReadRefused` with `("redirected", None, 302)`, and a stream that records `close()` was closed.
- `test_the_refused_redirect_statuses_are_exactly_httpxs`: `{s for s in range(300, 400) if httpx.Response(s, headers={"Location": "/"}).has_redirect_location} == _REDIRECTS`.
- `test_a_3xx_httpx_does_not_follow_is_a_bad_response_even_with_an_unreadable_location`: 300 and 304 with `Location: https://xn--a.test/` give `("bad_response", status)`.
- The existing redirect tests stay and now exercise the hook.

**`tests/test_stores_api.py`:** `test_a_redirect_to_an_unreadable_address_is_saved_as_redirected_not_a_500` over the same three addresses: `POST /api/stores/1/test` answers 200 with `(ok, reason, detail, state, http_status) == (False, "redirected", None, "unreachable", 301)`, and `GET /api/stores` then shows health `("unreachable", "redirected", 301)`.

**`tests/test_testenv_laragon.py`:** `test_check_words_a_redirect_to_an_unreadable_address` keeps its assertion (docstring: `WooClient` answers `redirected` with no host); `test_check_reports_only_the_idna_error_as_a_redirect` becomes `test_check_lets_an_unexpected_error_surface`, over `ValueError` and `UnicodeError`, both raising.

### Skills and tools to load ([09 §3](../09-tooling.md))
- Builder: Context7 for httpx (event hooks) before writing.
- Reviewer: `security-review` (`apply/`) and `code-review`.
- Not needed: `aws-sdk-python-usage` (no S3 code), `frontend-design` (no screen).

### Done
- All tests above pass, with the pre-fix failures recorded; no `UnicodeError` catch left in `testenv/`.
- Through `UV_PYTHON_DOWNLOADS=never bash tools/heavy.sh --log t8-<name> …`: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run mypy --platform linux`, `uv run bandit -r backend`. At integration the lead also runs `release-build.ps1` (`backend/shelfsync` ships).
- Commits: `fix(stores): refuse a 3xx in a response hook so an unreadable Location reads as redirected [SET-01, ERR-01]` and `docs(04-A): V58 httpx runs response hooks before it builds next_request [SET-01]`.

### Out of scope (follow-ups, each its own task)
- **F1 (Tier A, read only, not run):** `normalize_url`'s `_HOST` (`store_service.py:61`) seems to accept `https://xn--a.test`; `WooClient.__init__`'s `url.host` would then raise `IDNAError` and Test connection answer 500. Refuse a host httpx can't decode at save time and in the backup import.
- **F2 (Tier A, updater, low: the hosts are allowlisted GitHub):** `update/github.py` `_api_get` (169) and `_follow` (247) have the same httpx exposure.
- **F3 (low):** seed's `_location_host` duplicates `_redirect_host`; seed could import it as it imports `_is_tls_error`.
- **For the reviewer:** whether `Client.cookies.extract_cookies` (`_client.py:1022`, before the hooks) can raise a non-httpx error on a hostile `Set-Cookie`.

### Open questions for the owner
None.

## 2. Early check

### Analyst: GO (on `6f7ea8c..8e860cc`)
The hook covers both GETs (it's client-wide), raises before `_build_redirect_request`, and its `ReadRefused` reaches `get` unwrapped with the stream closed (`_client.py:998`). Nothing new catches a programming error. The 27 t8 tests pass (`.logs/t8-analyst-tests.log`); V58's line numbers match the installed httpx 0.28.1. `https://user@:99999/` confirmed: httpx builds `next_request` without raising (kept as a regression case).

Findings, all taken by the lead and sent back to the builder:
1. **Low:** the tests call `https://user@:99999/` unreadable (`UNREADABLE_LOCATIONS`); httpx reads it. Word it as a regression case.
2. **Low:** add `//xn--a.test/` (protocol-relative IDNA). Measured without the hook: it crashes on another path (`_redirect_headers:552` → `_same_origin:89` → `URL.host:191`, `InvalidCodepoint`), so it proves the hook isn't tied to line 532. A clause in V58.
3. **Low:** V58 suggested `send`'s and `_send_handling_auth`'s close-and-re-raise blocks apply; the calls at 914, 942 and 868 sit outside them, so the exception passes unchanged.
4. **Nit:** "a 3xx is refused" (06 line 41, the module docstring) is broader than the code: a redirect status (301, 302, 303, 307, 308); 300 and 304 are `bad_response`.

**The `Set-Cookie` question:** nothing found. `extract_cookies` runs before the hooks, outside the close blocks, but Python 3.15.2's `http/cookiejar.py` `make_cookies` wraps the header parsing in `except Exception` (a warning instead); 20 hostile headers and 30,000 random ones through `WooClient.get` raised no non-httpx error (evidence, not proof). Side note, not t8: such a warning reaches the app log through `logging.captureWarnings`, with the store's cookie text.

## 3. Builder report
_(builder, `claude-opus-5-5/high`, 2026-11-05; worktree branch `worktree-agent-a0f50490d86bca832`, cut from `6f7ea8c`; commits `758044d` fix and tests, `64ec046` V58 and 06, then this report)_

**Done as §1 says.** A 3xx in `_REDIRECTS` is refused in the response hook `_refuse_redirect`, so all three unreadable addresses read as `redirected` with no host, and Test connection saves that health rather than answering 500. Every check passes: pytest 2801 passed, 19 skipped, 56 deselected; ruff; ruff format; mypy; mypy `--platform linux`; bandit 0 issues. **One difference from the brief:** `https://user@:99999/` was never a crash. The old code already read it as `redirected` with no host (details under "Pre-fix failures").

### Skills and tools loaded
- **Context7 `/encode/httpx/0.28.1`** (event hooks), loaded before writing:
  - a `response` hook is called "after the response has been fetched from the network, but before it is returned to the caller";
  - it runs "before determining if the response body should be read";
  - a hook may raise (the `raise_for_status` example).
  - The docs don't say whether hooks run before or after the redirect is built. I confirmed that order in the installed source (V58).
- **The installed source** (`.venv`, httpx 0.28.1, idna 3.20): I re-checked every line number the brief cites, and they all match. I also read `_build_redirect_request` (475-492), the close-and-re-raise in `_send_handling_auth` (958-960) and in `send` (926-928), and `request_context` (`_exceptions.py` 367-379: it only attaches the request to a `RequestError`).
- **Not loaded:**
  - `aws-sdk-python-usage`: there's no S3 code here.
  - `frontend-design`: there's no screen.
  - `security-review` and `code-review` are the reviewer's (brief §1).

### Files changed
- `backend/shelfsync/apply/woocommerce.py`:
  - **New `_refuse_redirect(response)`:** raises `ReadRefused("redirected", _redirect_host(location), status)` for a status in `_REDIRECTS`. It's wired in as `event_hooks={"response": [_refuse_redirect]}` in `WooClient.__init__`.
  - **`_redirect_host`:** now catches `httpx.InvalidURL, ValueError`.
  - **Removed:** the dead inline `_REDIRECTS` check in `get`.
  - **Docstrings:** the module, `get`, `_redirect_host` and the hook now say a 3xx is refused in a response hook before httpx reads `Location` (04-A V58).
  - `get` has no new `except`, and `store_service.py` is unchanged.
- `testenv/laragon.py`: `run_check` calls `run_read_test` directly. The `try/except UnicodeError` is gone, and no `UnicodeError` catch is left in `testenv/` (checked with grep). `ReadOutcome` stays imported for `describe`.
- `tests/test_woocommerce_client.py`: the five new tests listed in §1 (11 cases), plus a small `_ClosingStream` helper. The existing redirect tests are unchanged and now exercise the hook.
- `tests/test_stores_api.py`: `test_a_redirect_to_an_unreadable_address_is_saved_as_redirected_not_a_500` (3 cases). It uses `signed_in_client(raise_server_exceptions=False)`, so a crash shows as the 500 the app would answer.
- `tests/test_testenv_laragon.py`:
  - `test_check_words_a_redirect_to_an_unreadable_address` keeps its assertion. Its docstring now says `WooClient` answers `redirected` with no host.
  - `test_check_reports_only_the_idna_error_as_a_redirect` became `test_check_lets_an_unexpected_error_surface`, run with `ValueError` and with `UnicodeError`; both must raise.
  - Both docstrings cite SET-01 and ERR-01, because this module's docstring cites no PRD IDs.
- `docs/04-architecture-appendix/A-stack-verification.md`: new row V58, with the same columns as the other rows.
- `docs/06-security.md`, line 41: after "redirects are never followed" it now adds that a 3xx is refused in a response hook before httpx reads its address, so a malformed one still reads as `redirected` (linked to 04-A V58).

### Pre-fix failures (the new tests run against `6f7ea8c`'s code)
Result: 9 failed and 8 passed.

**Failed:**
- `…reads_as_redirected_with_no_host`, `https://xn--a.test/`, with 301 and with 307: `idna.core.InvalidCodepoint` escaped (an `IDNAError`, from `_redirect_url` 532 → `URL.host` → `idna.decode`).
- `…reads_as_redirected_with_no_host`, `http://[::1`, with 301 and with 307: wrong reason, `unreachable` where `redirected` was expected. `InvalidURL` became `RemoteProtocolError`.
- `test_an_unreadable_redirect_on_the_second_get_keeps_the_first_gets_versions`: `InvalidCodepoint` escaped.
- `test_get_raises_the_hooks_refusal_unwrapped_and_closes_the_answer`: `InvalidCodepoint` escaped, at `_client.py:532`.
  - **A bug in my first draft of this test:** with no `monotonic=` given, it used the real clock against `deadline=2000.0` and failed as `timeout`. I fixed the test by giving the client `monotonic=lambda: 1000.0` and ran it again on the unfixed code, where it failed with the `InvalidCodepoint` above.
- `test_a_redirect_to_an_unreadable_address_is_saved_as_redirected_not_a_500`:
  - `https://xn--a.test/`: answered **500 `{"error":"internal"}`**.
  - `http://[::1`: answered 200, but with `reason` `unreachable` and `http_status` None.
- `test_check_lets_an_unexpected_error_surface[UnicodeError]`: DID NOT RAISE. The old `except UnicodeError` turned it into `redirected`.

**Passed:**
- **`https://user@:99999/`, with 301 and 307 in the client test and with 301 in the API test.** This differs from the brief, which treats it as unreadable. httpx 0.28.1 parses it with an empty host (`URL.host == ""`) and builds `next_request` without raising: `_redirect_url` copies the store's host into it. So the old code already gave `redirected` with no host. I kept the address in both tests as a regression case, and V58 records the measurement.
- `test_the_refused_redirect_statuses_are_exactly_httpxs` and `test_a_3xx_httpx_does_not_follow…`, with 300 and with 304. These pin current behaviour, so they pass before and after the fix.
- `test_check_words_a_redirect_to_an_unreadable_address`: the old workaround handled it.
- `test_check_lets_an_unexpected_error_surface[ValueError]`: it raised before the fix too.

### Commands and results
- While working, without the queue: `uv run pytest --no-cov` on the four changed or related modules (`test_woocommerce_client`, `test_stores_api`, `test_testenv_laragon`, `test_testenv_seed`): 368 passed, 1 skipped (a non-Windows path), 4 deselected. `ruff check` and `ruff format --check` on the five changed Python files: clean.
- Through `UV_PYTHON_DOWNLOADS=never bash tools/heavy.sh --log t8-<name> …`, all exit 0:
  - `uv run pytest` (`t8-pytest`): **2801 passed, 19 skipped, 56 deselected** in 363 s. Coverage is 93 % in total and 99 % for `apply/woocommerce.py`. Its one missed line, 188 (`raise ReadRefused("timeout")` when the deadline has already passed before a GET), was there before and isn't touched by this change.
  - `uv run mypy` (`t8-mypy`): no issues in 80 source files (`shelfsync` and `testenv`).
  - `uv run mypy --platform linux` (`t8-mypy-linux`): no issues in 80 source files.
  - `uv run bandit -r backend` (`t8-bandit`): 0 issues at every severity. 15 findings are suppressed by `nosec` comments that were there before.
  - `uv run ruff check` (`t8-ruff`, the one full lint): all checks passed.
  - `uv run ruff format --check` (`t8-ruff-format`): 184 files already formatted.

### Not verified
- **No real store and no Laragon site.** Every result comes from `MockTransport` fakes and the loopback fake server in `test_testenv_laragon.py`. The `check` command against the real Laragon site stays the lead's (m2.8).
- **`release-build.ps1` not run:** the lead runs it at integration, as §1 Done says.
- **Not run:** `uv run pytest -m windows` and pip-audit (this change adds no package).
- The reviewer's `Set-Cookie` question (§1 "Out of scope": can `extract_cookies` raise a non-httpx error before the hooks run?) is not looked into.

### Open questions
None for the owner. For the lead:
- **Should `https://user@:99999/` stay in the tests?** It never crashed. I kept it as a regression case; another address could replace it if a third crashing example is wanted.
- **The 06 reference is a link,** `[04-A V58](…)`, like 06's other links to 04-A. Most of 06's V references are plain text, such as "(04-A V22)".

## 5. Review

### Review 1: APPROVE (`07ee302..14647dc`)
Skills: `security-review` (no vulnerability at 8/10 confidence or more; its passes run by the reviewer itself, as its Agent tool wasn't available) and `code-review` at high. No screens.

Verified: V58's order of operations and every line number in the installed httpx 0.28.1; 06 line 41. A fuzz of 20,000 random `Location` values (IDNA labels, brackets, `@`, `%`, NUL, `\xff`, non-UTF-8 bytes, protocol-relative, bad ports) with each of 301, 302, 303, 307 and 308 through a real `WooClient.get`: every one `ReadRefused("redirected", …, status)`, nothing else escaped, exactly one request each (the keys never reach a redirect target). The hook fires only on `_REDIRECTS`, the same set as the old inline check; `store_service.py` unchanged, so a real bug is still a 500. The builder's pre-fix run shows the tests catch removing the hook. Targeted tests: 371 passed, 1 skipped (`.logs/t8-review-tests.log`).

Findings (all low):
1. **Low:** the module docstring said any other 3xx "is a `bad_response`", but `classify` answers `not_woocommerce` for a `rest_no_route` body. **Fixed by the lead** (docstring only: "goes to `classify` (normally `bad_response` with its status)"). A one-line docstring change, so no further re-check (12 §4).
2. **Low, before t8:** `_redirect_host` reads `URL.host`, which IDNA-decodes, so a valid punycode target (`xn--bcher-kva.example`) is never named; and `_HOST` accepts junk like `..` or `--` as a host (React escapes it; cosmetic). **Folded into follow-up F3:** read `raw_host`, require a letter or digit label, one helper shared with seed.
3. **Low:** `docs(runs)` commits cite no PRD ID. The squash-merge keeps only the PR title, which cites `[SET-01, ERR-01]`.

Out of scope, as the reviewer sees the severities: F1 low-to-medium (the owner's own saved address; a 500, nothing lost); it also covers `testenv/laragon.py:705`'s `WooClient(site.url, …)`, which would now show a traceback for such a host, so F1's tests should include it. F2 low. The cookie-warning side note (§2) is a logging question for its own follow-up.

Not verified by the reviewer: a real store or Laragon site; the full suite, `mypy --platform linux`, bandit and `release-build.ps1` (the lead's, §6). The fuzz is evidence, not proof.

## 6. Integration notes
- The builder's commits came onto `fix/t8-woo-redirect` by fast-forward (`758044d`, `64ec046`, `8e860cc`) and one cherry-pick (the early-check lows, `14647dc`); the lead added the brief, §2, §5, this section, review low 1 (docstring) and the 11 row. The builder's worktree and branch are removed.
- **Full checks on the final tree**, each through `UV_PYTHON_DOWNLOADS=never bash tools/heavy.sh --log t8-final-<name>`, all exit 0: `uv run pytest` 2804 passed, 19 skipped, 56 deselected; `ruff check` clean; `ruff format --check` 184 files formatted; `mypy` and `mypy --platform linux` no issues in 80 files; `bandit -r backend` no issues.
- **Release build** (`backend/shelfsync` ships): `npm ci` and `npm run build` in `frontend/`, then `packaging/release-build.ps1 … -Work C:\Users\r4rup\AppData\Local\Temp\ssrb8 -Suffix -rehearsal`: passed (build, smoke test, installer checks, manifest; `.logs/t8-release-build.log`).
- Not run: `pytest -m windows` (nothing Windows-specific changed) and pip-audit (no package changed).
- **Follow-ups** (each its own task): F1 (Tier A) refuse a store host httpx can't decode, at save, in the backup import, and for `testenv/laragon.py`'s `WooClient(site.url, …)`; F2 (Tier A, low) the updater's same httpx exposure in `update/github.py`; F3 (low) one `_redirect_host` shared with seed, reading `raw_host` so a punycode target is named, and refusing junk like `..` (review low 2); a store's cookie text can reach the app log through a `http.cookiejar` warning (`logging.captureWarnings`; §2 side note).

## 7. Handover
_(lead, 2026-11-05)_ Built, early-checked (GO, four lows fixed), reviewed (APPROVE, three lows: one fixed, one folded into F3, one met by the PR title), full checks and the release build passed. **Next:** the PR merges under the automatic rule; then the run file's Status becomes merged. F1–F3 and the cookie-log question wait for their own tasks.

_(lead of m2.8, 2026-11-05, end of day)_ Merged as #61 on green (09:10 UTC). F1–F3 and the cookie-log question are in 10-status's open follow-ups, each for its own task.
