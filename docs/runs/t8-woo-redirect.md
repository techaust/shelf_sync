Status: open
Tier: A (12 §2: `apply/`, the store client)
Usage: lead `claude-opus-5-5/high` (PC, side session started by the m2.8 lead): 5-h 5 % at the start; analyst `claude-opus-5-5/high` [none] (brief: Context7 isn't in its tools, so it read httpx 0.28.1 and idna 3.20 from `.venv`)

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

## 3. Builder report

## 5. Review

## 6. Integration notes

## 7. Handover
