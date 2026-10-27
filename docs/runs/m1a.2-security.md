Status: merged (PR #7)
Tier: A
Usage: `analyst claude-opus-5-5/high` (brief draft; no skill: `security-review` and `code-review` need a diff, none existed); lead at Opus 5.5 high for the final brief and the review triage (12 §3); `analyst opus/high` early check (`security-review`); `builder claude-sonnet-5-5/high`, fix round `sonnet/medium`; `reviewer opus/high` (`code-review`, `security-review`); re-check `reviewer opus/medium` (same skills). From `node tools/model-audit.mjs 2026-10-27`; 5-h 23 % at the start, 51 % late in the day

# M1a.2: Security base

## 1. Brief
_(analyst draft, Opus 5.5 high; final by the lead, Opus 5.5 high, 2026-10-27)_

**Roadmap:** M1a, the security base ([08](../08-roadmap.md) M1a row; [06 §9](../06-security.md) M1a row). It builds on M1a.1 (merged, PR #2). M1a.3 (shell) and M1a.4 (tray, launcher) code to the contract in item 11.

**PRD IDs** ([03](../03-prd.md)):
- SYS-03, the sign-in part only: ticket and session on the server. The launcher is M1a.4.
- SET-06, "Reset access token" logic only. Its screen is M1b.
- LOG-01: redaction.
- NFR-5: 127.0.0.1 only, no outbound calls.
- Design: [06 §2–3](../06-security.md), [ADR 0005](../adr/0005-localhost-only.md).

**Who:** the `builder` (Sonnet 5.5, **high**: Tier A, [12 §3](../12-models-and-usage.md)), in its own git worktree on the branch `feat/m1a.2-security`, cut from `main` once this brief's PR has merged. Commit there; **never push**. The lead integrates. No designer: this task has no screens.

**Order** ([12 §4](../12-models-and-usage.md)):
1. builder, up to the early-check stop
2. `analyst` early check (Opus high): GO or CHANGE, appended to §2
3. builder finishes
4. `reviewer` (Opus high) with **`code-review` and `security-review`**
5. lead triage at high
6. fixes (builder at medium, or high if any finding is critical)
7. re-check (reviewer at medium)

**Early-check stop:** once `secure/` (token, sessions, middleware, headers, redact), `platform/secrets.py` and `api/session.py` are committed and wired into `create_app`, with their unit tests passing. That is before item 9 (output paths), the Windows checks and the final full run. Write "Ready for early check" with a short summary in §2 and end the turn.

**Writes only to:**
- `backend/shelfsync/secure/` (new, flat: no subfolders): `__init__.py`, `redact.py`, `token.py`, `sessions.py`, `middleware.py`, `headers.py`
- `backend/shelfsync/api/`: `app.py` (changed), `session.py` (new), `errors.py` (new)
- `backend/shelfsync/platform/secrets.py` (new): the `SecretStore` protocol, a `MemorySecretStore` fake and the `KeyringSecretStore` Windows adapter
- `backend/shelfsync/logs.py`, `server.py`, `__main__.py` (wiring only)
- `pyproject.toml` (keyring, ruff `T20`) and `uv.lock`
- `tests/`: new tests, plus updates to existing tests the Host check breaks (`tests/test_api_health.py` uses TestClient's default host `testserver`)
- §2 (the stop line only) and §3 of this file

The lead owns `docs/` (except the parts of this file named above), `CLAUDE.md`, `CHANGELOG.md`, `.gitignore` and `.github/workflows/`: suggest changes there in §3. The CI coverage step turns on for `secure/` by itself once it has code.

**Skills and tools** ([09 §3](../09-tooling.md)):
- No 09 §3 skill fits the builder; `security-review` and `code-review` are the reviewer's. Say so in §3.
- **Context7** before writing code that uses FastAPI 0.143.0, Starlette 1.7.0, uvicorn 0.54.0 (h11 0.16.0), pydantic 2.14.1, hypothesis 6.169.0, pytest 9.1.1, coverage 7.16.2 and keyring 25.7.0. docs.python.org for `secrets`, `hmac`, `hashlib`, `logging` (`lastResort`, `captureWarnings`), `sys.excepthook` and `threading.excepthook`. List in §3 what you looked up and what it said for each point in item 13.
- Heavy commands only through `bash tools/heavy.sh --log m1a.2-<name> <command>`; read the logs with grep.
- No browser is needed.

**Owner decisions that bind this task** ([11](../11-decisions.md)):
- The ticket design ([06 §2](../06-security.md)): token → single-use 60 s ticket → session cookie; the ticket route refuses any `Origin`; the token never in a URL.
- Reset access token ends every open session.
- Bind to 127.0.0.1 only; no telemetry, no outbound calls.
- **keyring added in M1a.2** (owner, 2026-10-27): only these, at exactly these versions, all with `sys_platform == "win32"` (see item 2). Nothing else may be added; if something is missing, stop and report it.
  - `keyring==25.7.0` (2025-11-16, MIT), in `[project] dependencies` with the marker `; sys_platform == "win32"`
  - it pulls in, on Windows: `jaraco-classes 3.4.0`, `jaraco-context 6.1.2`, `jaraco-functools 4.6.0`, `more-itertools 11.1.0`, `pywin32-ctypes 0.2.3` (all MIT except pywin32-ctypes, BSD-3-Clause). Confirm the lock resolves to exactly these; Linux gets none of them.
- **Sign-ins last until the browser or ShelfSync closes** (owner, 2026-10-27): tickets and sessions live in memory only, nothing about them on disk, no idle timeout.
- The 14-day cutoff (`exclude-newer`) and its security exceptions stay as they are.
- `secure/` reaches ≥ 90 % coverage in CI.

**Work** (each item lists its tests; every test lives in `tests/` and names its PRD ID in the docstring):

1. **Bind address (NFR-5).** Already built (`server.HOST`, `_try_bind`); keep it. Add a test that the uvicorn config's host is `127.0.0.1`. Cite the existing `test_socket_is_bound_to_loopback_never_all_interfaces` in §3 as the M1a evidence.

2. **Secret store and install token** (`platform/secrets.py`, `secure/token.py`):
   - `SecretStore` protocol: `get(name) -> str | None`, `set(name, value)`, `delete(name)`. Service name `ShelfSync`.
   - `MemorySecretStore`: the fake, used by every test outside the `windows` marker and on Linux CI.
   - `KeyringSecretStore`: the Windows adapter. Import keyring **inside an `if sys.platform == "win32":` block** (or lazily inside the class), so Linux CI, where keyring isn't installed, still imports the module and mypy skips the Windows branch. Verify in Context7/the mypy docs that mypy treats that block as unreachable on Linux; if it doesn't, use a per-module mypy override for `keyring` and say why. Errors from keyring become one `SecretStoreError`, with no secret value in its message.
   - `load_or_create_install_token(store) -> str`: `secrets.token_urlsafe(32)`, stored under the name `install-token`, created only when absent.
   - `reset_install_token(store) -> str`.
   - `verify_install_token(presented: str, expected: str) -> bool`: `hmac.compare_digest` on UTF-8 **bytes**, so a non-ASCII header gives `False`, never a 500.
   - Start-up loads the token **before** the port is bound. A store failure exits with code 3 and the existing `messages.START_FAILED` notice; no port is held.
   - The token is registered with `redact` (item 8) when loaded and when reset.
   - Tests:
     - created once, then the same value on a second load; reset gives a new value
     - non-ASCII, empty and very long presented tokens → `False`
     - `runtime.json` never contains the token
     - a store that raises → exit 3, the fixed notice, no port held, and the log has no secret

3. **Tickets and sessions** (`secure/sessions.py`, thread-safe, clock injected):
   - In-memory maps keyed by the **SHA-256 digest** of each ticket or session id; raw values aren't held.
   - `issue_ticket() -> str`: valid while `now < issued + 60` on `time.monotonic()`. At most 32 outstanding (oldest dropped).
   - `redeem_ticket(t) -> str | None` (the new session id): single use, removed under a lock.
   - `check_session(sid) -> bool`. At most 64 sessions (oldest dropped).
   - `end_all()`: clears every ticket and session.
   - `sign_in_url(port, ticket) -> str` gives `http://127.0.0.1:<port>/#t=<ticket>`. M1a.4 (launcher) and M5 (toast click) use it with `issue_ticket()`; nothing builds that URL by hand.
   - Tests:
     - redeem at 59.999 s → ok; at 60.000 s → refused
     - a second redeem → refused
     - two threads redeeming the same ticket at once → exactly one succeeds
     - unknown, empty and 10 KB tickets → refused
     - both caps hold
     - after `end_all()` old sessions and tickets are refused
     - `sign_in_url` holds the ticket and never the token

4. **Routes** (`api/session.py`; the contract is in item 11):
   - `POST /api/session/ticket`
     - refused (403) if **any** `Origin` header is present, ShelfSync's own included
     - needs `Authorization: Bearer <install token>` (scheme case-insensitive; no other form accepted) → 200 `{"ticket": …, "expires_in": 60}` with `Cache-Control: no-store`
     - needs no session and no `X-ShelfSync`; the Host check still applies
   - `POST /api/session`
     - JSON `{"ticket": …}`; needs ShelfSync's Origin and `X-ShelfSync: 1`
     - → 204 with `Set-Cookie: shelfsync_session=<id>; HttpOnly; SameSite=Strict; Path=/` and no `Domain`, `Expires`, `Max-Age` or `Secure`
   - `POST /api/session/reset-token`
     - needs a session, ShelfSync's Origin and `X-ShelfSync: 1`
     - rotates the token, calls `end_all()`, clears the cookie → 204
   - Abuse tests:
     - **ticket route:** with `Origin: http://127.0.0.1:<port>` → 403; with `Origin: null` → 403; no `Authorization` → 401; wrong token → 401
     - **token in the wrong place:** in the query (`?token=`), the body or a cookie → 401
     - **malformed `Authorization`:** `Bearer <token> extra` → 401; non-ASCII → 401, not 500; GET → 405, with the security headers
     - **replayed ticket** → 401; **expired ticket** → 401; garbage ticket → 401
     - **reset:** the old token is refused at the ticket route and the new one accepted; the old cookie → 401
     - **cookie attributes:** checked exactly by parsing `Set-Cookie`

5. **Host, Origin and CSRF middleware** (`secure/middleware.py`):
   - A **pure ASGI** middleware that denies by default, with an explicit exemption table (item 11). Use `BaseHTTPMiddleware` only if Context7 shows a pure one can't do something needed, and say why.
   - `create_app(port: int, secrets: SecretStore, clock=time.monotonic)` receives the bound port; `server._start` passes it (it calls `create_app()` with no arguments today). Tests use `TestClient(app, base_url="http://127.0.0.1:<port>")`.
   - Rules, in this order:
     1. **Host:** exactly one `host` header, equal to `127.0.0.1:<port>` or `localhost:<port>` (lowercase, exact). Checked on **every** request, including `/api/health` and paths outside `/api`.
     2. **Origin:** if present on any request, it must equal `http://` + that request's Host.
     3. **Methods:** every method except GET and HEAD is state-changing and needs ShelfSync's Origin and `X-ShelfSync: 1` (exactly), except the ticket route.
     4. **Session:** every path under `/api` needs a valid session cookie, except the three in item 11.
     5. **No CORS:** no `Access-Control-*` header on any response; OPTIONS under `/api` is refused.
   - **Wrong-Host tests (DNS rebinding):**
     - `evil.example:<port>` on GET `/api/health` → 403
     - the same Host on the ticket route with the correct token → 403
     - `127.0.0.1:<port>.evil.example`, `127.0.0.1:<port+1>`
     - `127.0.0.1` and `localhost` with no port
     - `[::1]:<port>`, `0.0.0.0:<port>`
     - an empty Host; two Host headers (say what h11 does, item 13)
   - **Cross-origin tests**, each against POST, PUT, PATCH and DELETE:
     - `http://evil.example`
     - **`http://127.0.0.1:3000`**: another local server, which `SameSite` doesn't stop
     - `http://localhost:<port>` while Host is `127.0.0.1:<port>`
     - `https://127.0.0.1:<port>`
     - `null`
     - also a foreign Origin on GET → 403
   - **Missing-CSRF tests:**
     - POST with cookie and Origin but no `X-ShelfSync` → 403
     - `X-ShelfSync: 0` or `true` → 403
     - a state-changing request with no Origin (other than the ticket route) → 403
   - **Session tests:**
     - **route-table test:** walk `app.routes`; every `/api` route outside the exemption table must refuse a request with no cookie (401). It keeps catching new routes in later milestones.
     - a forged cookie → 401
     - a path outside `/api` (404 today) is never 401
   - Refusals are logged with the check's name, the method and the path only, never header values.

6. **Security headers** (`secure/headers.py`), added to **every** response: 200, 204, 401, 403, 404, 405, 422, 500:
   - `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: no-referrer`
   - `Cross-Origin-Resource-Policy: same-origin`
   - `Cache-Control: no-store` on `/api`
   - Test: the exact header strings on each status code, including a test-only route that raises (500). Verify (item 13) whether a 500 from Starlette's outermost error middleware still gets the headers; if it can't, say so at the early check.

7. **Error bodies** (`api/errors.py`): fixed JSON that never echoes input:
   - 403 `{"error":"forbidden"}`
   - 401 `{"error":"signed_out"}`, `{"error":"bad_token"}` or `{"error":"bad_ticket"}`
   - 422 `{"error":"invalid_request"}`, replacing FastAPI's default body (verify whether that echoes `input`)
   - 500 `{"error":"internal"}`, no traceback; `debug` stays off
   - Every body passes through `redact`.
   - Tests:
     - a malformed `/api/session` body holding the token → the 422 body has no token
     - the 500 body is fixed
     - the log holds the redacted traceback

8. **Redaction (LOG-01; M1a.1 review #11)** (`secure/redact.py`; `shelfsync.logs.redact(text) -> str` stays the named hook and delegates to it):
   - **Patterns:**
     - `ck_` and `cs_` followed by at least 20 characters
     - AWS key IDs (`AKIA` / `ASIA` + 16)
     - `aws_secret_access_key=…`, `X-Amz-Signature=…`, `X-Amz-Credential=…`
     - GitHub `github_pat_…` and `gh[pousr]_…`
     - `Authorization: …` and `Bearer …`
     - `shelfsync_session=…`, `#t=…`, `"ticket": "…"`
     - `consumer_secret=…`, `oauth_signature=…`
   - **Registry:** `register_secret(value)` for exact values of at least 16 characters, thread-safe. The install token is registered on load and reset; M2 registers keyring secrets when read.
   - **Mask:** the label kept, then `[redacted]`.
   - **Never masked:** ISO times, file names (`jupiterx-4.61.0.zip`), 32-hex MD5s, version strings.
   - `job_id` and `step` go through `redact` too (`logs.py`, the JSON fields).
   - **Tests:**
     - one per pattern family; registered values masked
     - hypothesis: random text with a secret inserted anywhere → the secret never survives; `redact` is idempotent; text with no secret comes out unchanged
     - the whole flow (ticket, session, reset) with `redact` patched to do nothing: the log and captured stdout/stderr hold **no token, ticket or session value**. This proves they're never logged at all, not just masked.

9. **Every output goes through `redact` (M1a.1 review #11):**
   - `install_output_guards()`, called first in `server.main()`:
     - replace `logging.lastResort` with a redacting stderr handler (it does nothing when `sys.stderr` is `None`, as under pythonw in M1a.4)
     - `sys.excepthook` and `threading.excepthook` log through the redacting logger
     - `logging.captureWarnings(True)`
   - Turn on ruff `T20` (no `print`) for `backend/`.
   - **Known gaps today:**
     - `server.py` around lines 155–160: `_log.exception` before the handler exists goes to `lastResort`, unredacted
     - around 168–169: records after `remove_logging` do the same
     - around 172–174: `resolve_data_paths()` is outside the `try`, so the default excepthook writes to stderr. M1a.4 still moves it inside the `try` ([11](../11-decisions.md)); this task's guard covers it until then.
   - **Test, one secret per path; none may appear unmasked:**
     - the message and its args; an exception message and traceback
     - `extra` fields
     - `uvicorn.error` records
     - a warning
     - a record before logging is set up, and one after it's removed
     - an uncaught exception in the main thread and in another thread
     - the `LogNotifier`
     - the 422 and 500 bodies
     - `run()` with a start-up exception whose message holds the token

10. **Windows checks** (`windows` marker; skipped on Linux):
    - `KeyringSecretStore`: set, get and delete one throwaway entry (`ShelfSync-test-<random>`), always removed in `finally`. Nothing else in Credential Manager is read or touched.
    - `load_or_create_install_token` twice through a throwaway service name gives the same value; cleaned up afterwards.
    - A missing entry returns `None`.
    - Run them with `bash tools/heavy.sh --log m1a.2-windows-checks uv run pytest -m windows --no-cov`.
    - `platform/` is measured by the Windows checks, not the CI gate ([07 §1](../07-testing.md)).

11. **Contract for M1a.3 and M1a.4** (record it in §3 as built; the lead copies it into their briefs):

    | Route | Session | Origin | `X-ShelfSync: 1` | Other |
    |---|---|---|---|---|
    | `GET /api/health` | no | if present, must be ShelfSync's | no | Host check |
    | `POST /api/session/ticket` | no | **must be absent** | no | `Authorization: Bearer <install token>` |
    | `POST /api/session` | no | ShelfSync's, required | required | JSON `{"ticket"}` |
    | every other `/api` route | required | ShelfSync's; required on writes | required on writes | |
    | paths outside `/api` (static UI) | no | if present, must be ShelfSync's | no | Host check, headers |

    - **For the page (M1a.3):**
      - read `#t=` and remove it with `history.replaceState` before any other request
      - POST it to `/api/session`; send `X-ShelfSync: 1` on every write
      - on 401 `signed_out`, show the signed-out state ([13 §3](../13-content.md))
      - no inline scripts or styles; no `data:` images unless the lead widens `img-src`
      - the Vite dev server must use the built files or a proxy that rewrites Origin; **no setting or environment variable loosens any check**, not even in development
    - **For the launcher (M1a.4):** `issue_ticket()` in-process, or the ticket route from a second process, then `sign_in_url()`. Before sending the token to a running copy, it checks the copy is really ShelfSync's (R1 in the lead's notes below; [06 §10](../06-security.md)).

12. **Coverage:** `secure/` ≥ 90 % in the CI per-folder step (lines and branches). Paste its per-file table from the local run. Aim to cover every branch of the middleware's decision table.

13. **Verify before relying on it** (none of these is in [04-A](../04-architecture-appendix/A-stack-verification.md); report each with its source):
    - Starlette 1.7.0:
      - pure ASGI middleware compared with `BaseHTTPMiddleware` (SSE comes later)
      - whether a user middleware's headers reach 404, 405 and 422 responses, and 500s from `ServerErrorMiddleware`
      - reading the raw `host` headers from the scope
    - FastAPI 0.143.0:
      - the default `RequestValidationError` body (does it echo `input`?)
      - `set_cookie` arguments and output (no `Domain`)
      - overriding the exception handlers
    - uvicorn 0.54.0 / h11 0.16.0: a missing Host, a duplicate Host, an absolute-form request target; does anything reach stdout or stderr with `log_config=None`?
    - TestClient: the default Host (`testserver`), `base_url="http://127.0.0.1:<port>"`, cookies kept for an IP host
    - stdlib: `logging.lastResort`, `captureWarnings`, `sys.excepthook`, `threading.excepthook`; `hmac.compare_digest` with non-ASCII `str` (expected `TypeError`, hence bytes)
    - coverage 7.16.2: does `--include=backend/shelfsync/secure/*` match files in subfolders? (`secure/` stays flat either way.)
    - keyring 25.7.0: the Windows backend, what a missing entry returns, its error types, whether it ships type hints (`py.typed`)
    - uv: the lock gives keyring and its five dependencies only on Windows, and `uv export` plus pip-audit still pass on Linux
    - the WooCommerce key format (`ck_` / `cs_` + 40 hex) through Context7 `/woocommerce/woocommerce-rest-api-docs`; GitHub token prefixes from docs.github.com

**Done means** (everything through `tools/heavy.sh`, results pasted in §3):
- `uv sync --locked`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` (strict), `uv run pytest`, the CI coverage step for `secure/` (≥ 90 %), `uv run bandit -r backend` (any `# nosec` with its reason), and `uv export … && pip-audit …` all pass on this PC.
- Every test in items 1–10 exists and passes, including the abuse tests: replayed ticket, expired ticket, wrong Host, DNS rebinding, cross-origin, missing CSRF header, token in URL, body or cookie, and no token, ticket or session value in any log or output.
- The Windows checks pass on this PC and leave nothing behind in Credential Manager.
- The brand tests still pass (221).
- CI: say "not run on GitHub yet".

**Out of scope** (owned elsewhere):
- **M1a.3:** the page's `#t=` exchange, the signed-out screen, serving `frontend/dist` (mounted *inside* this middleware), the Vite build settings for the CSP, Playwright failing on CSP violations.
- **M1a.4:** the launcher and single instance (SYS-03, launcher part); moving `resolve_data_paths()` inside the start-up `try`; `runtime.json` clean-up; the toast click; the check that a running copy is really ShelfSync's (R1); pythonw's stderr.
- **M1b:** Settings › App with Reset access token; after an in-app update, the restarted app opens a fresh signed-in tab (sessions are in memory, so open tabs are signed out).
- **M2:** store, S3 and GitHub secrets in Credential Manager, registered with `redact` when read; stripping signatures and auth headers from store and AWS errors ([06 §3](../06-security.md)), tested with recorded responses; backup crypto.

**Report in §3:** files changed, every command and its result, the resolved lock versions for keyring and its dependencies, what Context7 and the docs said for each point in item 13, the coverage table, anything not verified, and open questions.

### Lead's notes on the draft
- **R1, port squatting (for the M1a.4 brief).** If ShelfSync isn't running and another program (for example another Windows user's) listens on the port in `runtime.json` and answers `/api/health` like ShelfSync, the launcher would send it the install token. The ticket contract stays as decided. M1a.4's launcher checks, before sending the token, that the listening socket belongs to a process running as the **same Windows user** (and ShelfSync's executable), using the Windows API to look up a socket's owner (to verify in 04-A, V33). M1a.1's note "the launcher checks `/api/health` identity, never the PID" is about not trusting `runtime.json`'s PID alone; this check asks Windows who owns the socket, which is different. Recorded in [06 §10](../06-security.md).
- **R2, merging with M1a.3.** Both touch `api/app.py` (the static mount). M1a.2 is integrated first, and M1a.3 mounts the static files inside the middleware.
- **R3, SameSite doesn't separate ports.** Other servers on 127.0.0.1 are same-site, so the cookie goes with their requests; the Origin and `X-ShelfSync` checks are what stop them. 04-A row V32 holds the browser behaviour this relies on.
- **R4.** Starlette's outermost error middleware may answer 500s without the headers (item 6); this may only show at the early check.
- **R5.** AWS secret keys have no prefix, so no pattern can catch them; from M2 every secret read from Credential Manager is registered with `redact`.

## 2. Early check
**Ready for early check** (builder, Sonnet 5.5 high, branch `feat/m1a.2-security`, not pushed). Done: `secure/` (token, sessions, middleware, headers, redact), `platform/secrets.py`, `api/session.py`, `api/errors.py`, wired into `create_app(port, secrets, clock)` and `server._start` (token loaded before the bind; failure exits 3). Not done yet, as the brief says: item 9 (output guards, T20 is already on), item 10 (Windows checks), the final full run, `uv export` + pip-audit, §3 report. State: 351 tests pass, ruff, mypy (strict) and bandit clean, `secure/` coverage 100 % lines and branches.

Points for the analyst:
1. **R4 confirmed by test.** A 500 from Starlette's outermost `ServerErrorMiddleware` skips every user middleware. Fixed by adding the headers in the `Exception` handler (`api/errors.py`); `tests/test_headers_errors.py` fails without that line.
2. **FastAPI 0.143 `app.routes` is not flat.** `include_router` leaves one lazy `_IncludedRouter` in it, so the route-table test walks `fastapi.routing.iter_route_contexts(app.routes)` (the function FastAPI's own OpenAPI builder uses). A plain walk would have checked zero routes.
3. **FastAPI's default 422 body does echo `input`** (checked); replaced by `{"error":"invalid_request"}`.
4. **uvicorn/h11:** two Host headers, a missing Host (HTTP/1.1) and an absolute-form target without Host get 400 from h11 before the app; HTTP/1.0 with no Host and an empty Host reach the app and get 403. Those 400s carry no security headers (below ASGI).
5. **Cookie:** Starlette writes `SameSite=strict` in lower case (valid, case-insensitive); the test compares case-insensitively.
6. **Session cookie and other local servers (R3 follow-on):** cookies aren't port-scoped, so the browser also sends `shelfsync_session` to any other server on `127.0.0.1` the owner visits; such a server could replay it with its own Origin and `X-ShelfSync` headers. Not fixable in this task; raised for 06 §10.
7. **Choices inside the brief:** exemption is by path (so GET on the ticket route reaches 405, as item 4 wants); WebSockets are refused outright until someone adds one; a stored token under 32 characters is replaced; `register_secret` ignores values under 16 characters and returns False; `X-Amz-Security-Token` is masked too; `KeyringSecretStore` errors carry the exception type name only.

**Early check verdict (analyst, Opus high): CHANGE.** No critical or high findings. Findings and how the builder fixed them (commit `b3b7a1c`, then `05f89ae` and `028c1af` for items 9 and 10):
1. *Medium, race between the ticket route and Reset access token.* `InstallToken` now holds one lock across "check the presented token and issue the ticket" (`run_if_matches`) and across "new token and `end_all()`" (`reset(then=...)`); lock order is always token, then sessions. Test `tests/test_reset_race.py` slows `issue_ticket` until a reset has run on another thread; it fails against the old code (ticket still valid, 204) and passes now.
2. *Medium, token loaded twice.* `_start` builds `InstallToken` once, before the bind, and passes it to `create_app(port, secrets, clock, install_token=None)`. `tests/test_single_token_load.py`: a store whose reads after the first one fail is read exactly once and the server starts (the second read no longer exists); a store that fails on the first read stops start-up before any bind.
3. *Medium, route-table test only looked at `/api`.* `tests/test_guard.py` now also fails on a route outside `/api` that is not in `ALLOWED_OUTSIDE_API` (empty), on a route under `/api` without methods, and on a route with no path; the exempt set is pinned as `{GET /api/health, POST /api/session/ticket, POST /api/session}`.
4. *Low, "nothing happened" checks.* After a refused write the test now asks a protected path (404 from the router, not 401) and compares the token with its value before.
5. *Low, `logs._redacted_field`.* Only text is redacted; `None`, `bool`, `int` and `float` pass through; any other object becomes text and is redacted.
6. *Low, layering.* `error_response`, `forbidden`, `signed_out` and `ErrorCode` live in `secure/headers.py`; `api/errors.py` re-exports them; a test checks `secure/` never mentions `shelfsync.api`.
7. *Low, `KeyringSecretStore`.* Uses its own `WinVaultKeyring()` instance (class path `keyring.backends.Windows.WinVaultKeyring`, Context7), typed through `KeyringBackend`.
8. *Low, redaction.* The keyword form `ticket=...` and `ticket='...'` is masked; one hypothesis test per pattern family with neighbours made only of separators (19 families); the left-guard trade-off is documented in `redact.py` and tested.
9. *Low, test comments.* The two-thread test now says it checks the contract, not the lock (the GIL makes `pop` atomic); the 60 s route test moves the clock by whole seconds (the exact 59.999 / 60.000 boundary stays in `test_sessions.py`).

## 3. Builder report
_(Final, builder Sonnet 5.5 high. The first part below was written at the early-check stop; the changes made after the early check are listed in §2 and in "After the early check" below.)_

**Skills:** none of the 09 §3 skills fits the builder here: `security-review` and `code-review` are the reviewer's; `aws-sdk-python-usage` and `aws-iam` (no S3 or IAM code); `frontend-design`, `dataviz`, `artifact-design` (no screens); `run` (no browser or running-app check needed). Context7 was used for every library in the brief.

**Item 1 evidence:** `tests/test_server.py::test_socket_is_bound_to_loopback_never_all_interfaces` (M1a) plus `tests/test_startup_security.py::test_the_uvicorn_config_host_is_loopback`.

**Packages:** `uv lock` added exactly `keyring 25.7.0`, `jaraco-classes 3.4.0`, `jaraco-context 6.1.2`, `jaraco-functools 4.6.0`, `more-itertools 11.1.0`, `pywin32-ctypes 0.2.3`; `uv export` shows each with `; sys_platform == 'win32'`.

**Item 13** (C7 = Context7, E = checked by running it on the pinned versions):
- Starlette 1.7.0 (C7 lists 1.0.0 and 1.8.0, not 1.7.0; behaviour checked on 1.7.0 itself): the docs recommend pure ASGI middleware (BaseHTTPMiddleware breaks contextvars propagation and is awkward for SSE), so the guard and the headers are pure ASGI. `ServerErrorMiddleware` is always the outermost layer, so a user middleware's headers do not reach its 500 (C7, E). 404, 405 and 422 do pass through user middleware and get the headers (E). Raw `host` headers come from `scope["headers"]`, a list of `(bytes, bytes)` with duplicates kept (C7).
- FastAPI 0.143.0: the default 422 body includes `input` (C7 example, E). `set_cookie(key, value, max_age, expires, path, domain, secure, httponly, samesite)` defaults give no Domain, Expires, Max-Age or Secure (C7, E; output `HttpOnly; Path=/; SameSite=strict`). `add_exception_handler` for `ApiError`, `RequestValidationError` and `Exception`; the `Exception` one is what `ServerErrorMiddleware` calls (C7, E). `app.routes` holds `_IncludedRouter` objects (E, source read).
- uvicorn 0.54.0 / h11 0.16.0 (E, raw sockets against a real server): see the early-check point 4. With `log_config=None` and no handler, h11's "Invalid HTTP request received." (a `uvicorn.error` WARNING) goes to stderr through `logging.lastResort`; with our file handler on the root logger nothing reaches stdout or stderr. INFO records don't reach `lastResort`.
- TestClient (Starlette 1.7.0 with httpx 0.28.1): default host `testserver` (E), `base_url="http://127.0.0.1:<port>"` works, the cookie jar keeps `shelfsync_session` for the IP host (E). It prints a `StarletteDeprecationWarning` asking for `httpx2` (not installed; no package may be added here).
- stdlib: `hmac.compare_digest("é", "é")` raises `TypeError: comparing strings with non-ASCII characters is not supported` (E), hence bytes. Context7 `/websites/python_library` (3.12): `logging.lastResort` is a `StreamHandler` on `sys.stderr` at WARNING, used when no handler is found on a logger or its ancestors, and can be set to `None`; `captureWarnings(True)` sends warnings, formatted with `warnings.formatwarning()`, to the `py.warnings` logger at WARNING; `sys.excepthook(type, value, traceback)` is called for an uncaught exception other than `SystemExit`; `threading.excepthook(args)` gets `exc_type`, `exc_value` (may be None), `exc_traceback`, `thread` (may be None), ignores `SystemExit` by default and, if it raises, `sys.excepthook` handles that. Checked by running (E): inside pytest the root logger always has pytest's handlers, so a record only reaches `lastResort` from a logger with `propagate=False` and no handler (the tests use one); `logging.Handler.handleError` prints the message and arguments to stderr unredacted, so the redacting handler overrides it to do nothing.
- coverage 7.16.2 (C7, docs for file patterns): a pattern ending `/*` is treated as `/**`, so `--include=backend/shelfsync/secure/*` also matches subfolders.
- keyring 25.7.0: the Windows backend's `get_password` returns `None` for a missing entry; `delete_password` raises `PasswordDeleteError` when nothing matched; errors derive from `KeyringError` (`InitError`, `NoKeyringError`, `PasswordDeleteError`, `PasswordSetError`); the package ships `py.typed` (E, file present).
- mypy (C7): by default it takes `sys.platform` from the running system and treats a `sys.platform == "win32"` block as unreachable on Linux. Verified: with the keyring package hidden, `mypy --platform linux` passes and `--platform win32` fails with import errors. No per-module override is needed.
- uv: the lock has the six packages only under `sys_platform == 'win32'` (see Packages).
- WooCommerce key format (C7 `/woocommerce/woocommerce-rest-api-docs`): shows `ck_…` and `cs_…` placeholders only; the "40 hex" length is **not** stated there, so the pattern accepts any run of 20 or more letters and digits. GitHub prefixes (C7 `/github/docs`, "About authentication to GitHub"): `ghp_`, `github_pat_`, `gho_`, `ghu_`, `ghs_`, `ghr_`.

**Coverage** (`coverage report --include="backend/shelfsync/secure/*"`): final run, statements / missed / branches / partial / cover: `headers.py` 38/0/10/0 100 %, `middleware.py` 73/0/30/0 100 %, `redact.py` 30/0/6/0 100 %, `sessions.py` 61/0/14/0 100 %, `token.py` 43/0/6/0 100 %, `__init__.py` 0 stmts; total 245 statements, 66 branches, 100 %. The CI step (`--fail-under=90`) exits 0.

**After the early check:**
- *Item 9 (output guards):* `logs.install_output_guards()` is the first call in `server.main()`. It replaces `logging.lastResort` with `RedactingStderrHandler` (silent when `sys.stderr` is None; never reports its own failures), sends `sys.excepthook`, `threading.excepthook` and (added, same purpose) `sys.unraisablehook` through the logger `shelfsync.uncaught`, and turns on `logging.captureWarnings(True)`. `remove_output_guards()` puts everything back (tests). `tests/test_output_guards.py` has one distinct key-shaped secret per path: message and args, exception and traceback, `extra` fields, `uvicorn.error`, a warning, a record before logging is set up, one after it is removed, an uncaught exception in the main thread (a real child process, also with `sys.stderr = None`), in another thread, an unraisable one, `LogNotifier`, the 422 and 500 bodies, and `run()` with a start-up exception that holds the install token. A control test shows that without the guards Python's own handler of last resort does print the key. Ruff `T20` is on for `backend/` (tests exempt); no `print` exists.
- *Item 10 (Windows checks):* `tests/test_windows_keyring.py`, five tests, each under its own one-off service `ShelfSync-test-<random>`, entries deleted in `finally`. `bash tools/heavy.sh --log m1a.2-windows-checks uv run pytest -m windows --no-cov`: 7 passed (these five and the two M1a Windows tests in test_paths.py and test_server.py; 411 deselected). Afterwards `cmdkey /list:ShelfSync-test-*` and `cmdkey /list:*@ShelfSync-test-*` (these filters read only entries with that name) both show `* NONE *`. Nothing else in Credential Manager was read or listed. Two of the tests do write a throwaway entry (set and get, and the install token under a second throwaway service name), one at a time; the real `ShelfSync` service was never used.
- *Linux branch of `platform/secrets.py`:* `tests/test_secrets_not_windows.py` (skipped on Windows). I checked the same two assertions here by setting `sys.platform = "linux"` before importing the module: it raises `SecretStoreError` and does not import `keyring`. mypy never checks the Windows branch on Linux (mypy skips a `sys.platform == "win32"` block there); it is checked on this PC, and with keyring hidden `--platform linux` passes.

**Final run** (everything through `tools/heavy.sh` where it is heavy; logs in `.logs/m1a.2-final-*.log`):
- `uv sync --locked`: ok. `uv run ruff check`: all checks passed. `uv run ruff format --check`: 52 files already formatted.
- `bash tools/heavy.sh --log m1a.2-final-mypy uv run mypy`: exit 0, no issues in 26 files (strict).
- `bash tools/heavy.sh --log m1a.2-final-pytest uv run pytest`: **418 passed** (includes the five real Credential Manager tests).
- `uv run coverage report --include="backend/shelfsync/secure/*" --fail-under=90`: 100 %, exit 0 (table above).
- `bash tools/heavy.sh --log m1a.2-final-bandit uv run bandit -r backend`: no issues; two `# nosec B105` (on `INSTALL_TOKEN_NAME` and `RESET_TOKEN_PATH`, names that only contain "token"; the reason is on the line above each).
- `uv export --locked --no-emit-project --format requirements-txt` then `bash tools/heavy.sh --log m1a.2-final-pipaudit uv run pip-audit --require-hashes --disable-pip -r .logs/locked.txt`: "No known vulnerabilities found" (the export holds the six Windows-only packages with their marker).
- Brand tests (221): **not run**. This worktree has no `brand/node_modules`, `brand/` is the designer's, and the branch changes nothing under `brand/` (`git diff main --stat` lists no `brand/` file). CI: not run on GitHub yet.

**Contract for M1a.3 and M1a.4 (as built):**

| Route | Session | Origin | `X-ShelfSync: 1` | Other |
|---|---|---|---|---|
| `GET /api/health` | no | if present, must be ShelfSync's | no | Host check |
| `POST /api/session/ticket` | no | **must be absent** (any Origin, ShelfSync's included, is 403) | no | `Authorization: Bearer <install token>` (one header, scheme in any case, one token) |
| `POST /api/session` | no | ShelfSync's, required | required | JSON `{"ticket": "<string>"}` |
| `POST /api/session/reset-token` | required | ShelfSync's, required | required | 204; new token, every session and ticket ended, cookie cleared |
| every other `/api` route | required | ShelfSync's; required on writes | required on writes | |
| paths outside `/api` (static UI) | no | if present, must be ShelfSync's | no | Host check, headers |

- **Writes outside `/api` also need Origin and `X-ShelfSync`:** the CSRF rule is by method, not by path. Any method except GET and HEAD, on any path, needs ShelfSync's Origin and `X-ShelfSync: 1` (the ticket route is the only exception).
- Host: exactly one `Host` header, `127.0.0.1:<port>` or `localhost:<port>` (lowercase, exact), on every request. If Origin is present it must be `http://` + that request's Host. Errors are fixed JSON: 403 `{"error":"forbidden"}`; 401 `{"error":"signed_out"}` (no or unknown session), `{"error":"bad_token"}` (ticket route), `{"error":"bad_ticket"}` (sign-in); 422 `{"error":"invalid_request"}`; 500 `{"error":"internal"}`.
- Cookie: `shelfsync_session=<id>; HttpOnly; SameSite=strict; Path=/`, no Domain, Expires, Max-Age or Secure; cleared with `Max-Age=0` on reset.
- Every response has the four security headers; `Cache-Control: no-store` under `/api`; no `Access-Control-*` header ever; OPTIONS under `/api` is 403; WebSockets are refused until someone adds a route and decides how it is checked.
- For the page (M1a.3): read `#t=` and remove it with `history.replaceState` before any other request; POST it to `/api/session`; send `X-ShelfSync: 1` on every write; on 401 `signed_out` show the signed-out state; no inline scripts or styles and no `data:` images (CSP `img-src 'self'`); no setting loosens any check, also in development. A static mount goes **inside** `GuardMiddleware`, and its path must be added to `ALLOWED_OUTSIDE_API` in `tests/test_guard.py` in the same change. The route-table test walks `fastapi.routing.iter_route_contexts(app.routes)`, because FastAPI 0.143's `app.routes` holds a lazy `_IncludedRouter`, not a flat list.
- For the launcher (M1a.4): `SessionStore.issue_ticket()` in-process (but a reset must go through `InstallToken.reset(then=sessions.end_all)`), or `POST /api/session/ticket` from a second process, then `sign_in_url(port, ticket)`. Before sending the token to a running copy it must check the copy is really ShelfSync's (R1, 06 §10). `create_app(port, secrets, clock, install_token=None)`; `server.run(paths, notifier, serve, retry_seconds, secrets=None)`.

**Recorded as decided by the lead:**
- The `StarletteDeprecationWarning` ("Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead") shows in every test run. `httpx2` was not added (no new package without the owner's yes).
- Responses that uvicorn or h11 write before the app runs (400 for two Host headers, a missing Host on HTTP/1.1, an absolute-form target without Host, garbage) carry no security headers; accepted.
- The left guard in the key patterns (`ck_`, `cs_`, `AKIA`, `ghp_`...): a prefix glued to a letter or digit (`xck_...`) is not masked by shape. That keeps words like `block_...` intact. A registered secret (the install token, and from M2 every keyring secret) is still masked in any position. Tested.
- The cookie reaching other local servers (06 §10): known residual risk; `sign_in_url` stays on `127.0.0.1`.
- `SameSite=strict`: Starlette's lower case is kept; the test compares case-insensitively.
- Windows Credential Manager persistence: keyring's default for `WinVaultKeyring` is `CRED_PERSIST_ENTERPRISE` (stays local on a PC outside a domain). Not changed.

**Not verified:**
- Linux CI and GitHub CI: nothing ran there. The Linux-only stub tests ran only through the `sys.platform` simulation described above; `uv export` and pip-audit ran on Windows (markers keep the six Windows-only packages out of a Linux install, shown by `uv export`, but pip-audit was not run on Linux).
- Brand tests (221): not run (see above).
- The `coverage report --include` pattern on subfolders is from the coverage docs; `secure/` has no subfolders.
- Browser behaviour of the cookie, CSP and `SameSite` (04-A V32) is not tested here; no browser was used.
- `KeyringSecretStore` error mapping for real keyring failures (locked profile, quota) was only checked with a fake backend; real failures weren't produced.
- The analyst's item 2 wording ("a store whose second `get` raises: the server never starts, and `get` is called exactly once") cannot hold literally after the fix (there is no second `get`, so the server starts). I tested the intent: `get` is called exactly once and the server starts; and a first-read failure stops start-up before the bind.

### Fix round 1
_(builder, Sonnet 5.5 medium, after the review and triage in §5; rows 6 and 8d are not mine.)_

- **1 (handleError):** `logs.RedactingFileHandler` (the file handler `configure_logging` returns) overrides `handleError` to write one fixed line, "A log line couldn't be written (<exception type>)", through `RedactingStderrHandler`; nothing from the record. Tests: `test_output_guards.py::test_a_failed_log_write_prints_one_fixed_line_and_nothing_from_the_record` (with guards, `capfd`, a mismatched-args call holding a key: fixed line, no key) and `..._is_reported_even_without_the_guards`. They use a logger that reaches only the file handler, because pytest's own capture handler on the root logger raises on bad arguments first.
- **2 (old token left behind):** `KeyringSecretStore.set` deletes the existing entry first (`contextlib.suppress(PasswordDeleteError)`), then writes. Windows test `test_replacing_a_value_leaves_no_copy_of_the_old_one_behind`: after two sets no `<name>@ShelfSync-test-...` entry exists (`_read_credential`) and the value is the second one.
- **3 (persistence):** `backend.persist = "local machine"` after construction; docstring fixed. Windows test `test_entries_are_kept_on_this_machine_even_if_the_environment_asks_otherwise`: with `KEYRING_PROPERTY_PERSIST=enterprise` set, `Persist == 2`.
- **4 (Ctrl+C):** `_log_uncaught` hands `KeyboardInterrupt` to the original hook and logs nothing. Test `test_ctrl_c_goes_to_the_original_hook_and_is_not_logged_as_a_crash`.
- **5 (captureWarnings):** `install_output_guards` records whether capture was already on (`warnings.showwarning` is the logging module's function; the stdlib has no public query) and `remove_output_guards` restores that. Test `test_removing_the_guards_restores_the_earlier_warnings_capture` (both starting states).
- **7 (AWS labels):** the secret-key pattern is now `(aws_)?secret_?access_?key` and a new one covers `(aws_)?session_?token`, so `SecretAccessKey`, `aws_session_token` and `SessionToken` (also in the JSON form) are masked. Tests: four new families in `test_redact_families.py` (hypothesis, neighbours of separators only). I also made that file's property test `assume` the random secret is not part of the kept label: hypothesis found `shelfsync_se` inside `shelfsync_session=` (a test flaw that already existed, not a redaction gap).
- **8a:** the hand-set `Cache-Control` in `api/session.py` is gone (the headers middleware sets it on every `/api` response; the existing ticket-route test of `no-store` still passes).
- **8b:** `create_app(port, install_token, clock=time.monotonic)`; the app only gets the `InstallToken`. `server._start` passes the one it built before the bind; tests build `InstallToken(MemorySecretStore())` (`tests/support.py`, `test_api_health.py`, `test_server.py`, `test_single_token_load.py`).
- **8c:** `InstallToken.matches` removed; `tests/test_token.py` uses `run_if_matches` through a small helper.
- **9 (plain pytest skips `windows`):** `addopts` now has `-m 'not windows'`. A `-m` on the command line replaces it: `pytest -m windows` ran 9 tests and deselected 422 (the five keyring tests, the two new ones, and the two M1a Windows tests in `test_paths.py` and `test_server.py`, which a plain run now skips too; the lead may want to know for CI, where Linux skipped them anyway). **The `-m windows` run line in §3 above is now `bash tools/heavy.sh --log m1a.2-fix-windows uv run pytest -m windows --no-cov`** (`--no-cov` only keeps the run from printing a partial coverage table).

**Commands** (logs in `.logs/m1a.2-fix-*.log`):
- `uv sync --locked`: exit 0. `ruff check`: all passed. `ruff format --check`: 53 files formatted. `mypy` (strict): no issues in 26 files.
- `uv run pytest`: **420 passed, 2 skipped, 9 deselected** (the nine `windows` tests). The first run failed once on the hypothesis flaw named in row 7; fixed and re-run.
- `uv run pytest -m windows --no-cov`: **9 passed**, 422 deselected. Afterwards `cmdkey /list:ShelfSync-test-*` and `cmdkey /list:*@ShelfSync-test-*` both show `* NONE *`.
- `coverage report --include="backend/shelfsync/secure/*" --fail-under=90`: exit 0; `headers.py` 100 %, `middleware.py` 100 %, `redact.py` 100 %, `sessions.py` 100 %, `token.py` 100 % (40 statements, 6 branches), total 242 statements, 66 branches, 100 %.
- `bandit -r backend`: no issues. `uv export --locked --no-emit-project --format requirements-txt` then `pip-audit --require-hashes --disable-pip -r .logs/locked.txt`: no known vulnerabilities.
- **Not verified:** Linux CI and GitHub (nothing run there); the mypy check of the Windows branch of `secrets.py` happens only on this PC (the new `persist` assignment type-checks here); real keyring failures (locked profile) still only checked with a fake backend; the brand tests (not run, as before).

## 4. Designer report
_(none: no screens)_

## 5. Review
**Review** _(reviewer, Opus 5.5 high, `code-review` + `security-review` run by hand on the worktree diff `0720646..0b6dfb6`, 2026-10-27)_ **APPROVE**. Nothing critical or high; the `security-review` method found nothing at confidence 8 or above (no way around the token, ticket or session checks, no DNS-rebinding, CSRF or browser-secret hole). Ran: `pytest -m "not windows"` 411 passed, 2 skipped; `secure/` coverage 100 %; ruff, ruff format, mypy (Windows and `--platform linux`) clean. Read only: the keyring and win32ctypes source, the stdlib `handleError`, the Windows tests, Linux CI.

**Triage** _(lead, Opus 5.5 high, 2026-10-27)_. M2 was confirmed by the lead in keyring 25.7.0's `Windows.py` (`set_password` re-saves the existing value under `<user>@<service>` before writing the new one).

| # | Sev | Finding | Decision |
|---|---|---|---|
| 1 | M | A failed log write (bad args, lone surrogate, rollover `PermissionError`) makes the stdlib `handleError` print the raw message and args to stderr | **Fix now:** every handler ShelfSync installs (the file handler included) gets a `handleError` that writes one fixed line through the redacting stderr handler: "A log line couldn't be written (<exception type>)", nothing from the record. Not `logging.raiseExceptions = False`: that hides the failure completely. Test: guards + file handler, a mismatched-args call holding a key, `capfd` shows the fixed line and no key |
| 2 | M | Reset access token leaves the old token in Credential Manager under `install-token@ShelfSync` (keyring's re-save) | **Fix now:** `KeyringSecretStore.set` deletes the existing entry first (ignoring `PasswordDeleteError`), then writes. Crash between the two → the next start makes a new token, tabs sign in again: acceptable. Windows test: after two sets, no `<name>@ShelfSync-test-…` entry exists (read with `_read_credential`) and the value is the second one |
| 3 | L | keyring's default persistence is `CRED_PERSIST_ENTERPRISE` (roams with a roaming profile) | **Fix now:** `backend.persist = "local machine"` set after construction (after `set_properties_from_env`), so no `KEYRING_PROPERTY_*` variable changes it; fix the docstring. Windows test: `Persist == 2` read back |
| 4 | L | Ctrl+C during start-up logged as a CRITICAL crash | **Fix now:** `KeyboardInterrupt` goes to the original hook |
| 5 | L | `remove_output_guards` always turns warnings capture off | **Fix now:** restore the earlier state |
| 6 | L | First-run read-then-write race between two processes | **Follow-up, M1a.4 brief** (single instance) |
| 7 | L | Only `aws_secret_access_key` is caught by shape; `SecretAccessKey`, `aws_session_token`, `SessionToken` aren't | **Fix now:** add the three labels (cheap, same pattern family, one hypothesis case each). Registering every secret by value stays the M2 rule (R5) |
| 8a | L | Hand-set `Cache-Control` in `api/session.py` is redundant | **Fix now:** remove |
| 8b | L | `create_app` takes `secrets` and `install_token`: two token sources | **Fix now:** `create_app(port, install_token, clock=time.monotonic)`; the app gets only the `InstallToken`; tests build `InstallToken(MemorySecretStore())` |
| 8c | L | `InstallToken.matches` is a check-then-act path used only by tests | **Fix now:** remove it; tests use `run_if_matches` |
| 8d | L | The 500 half of `test_the_422_and_500_bodies` would pass with Starlette's default body | **Keep:** the exact body is pinned by `test_500_body_is_fixed_and_holds_no_traceback_or_message` (lead read it) |
| 9 | L | Every plain `uv run pytest` on this PC writes throwaway Credential Manager entries (reviewer note) | **Fix now:** `addopts` deselects `windows` by default; the Windows checks run only through `-m windows` (confirm the command-line `-m` overrides the `addopts` one, and update the `-m windows` run line in §3) |

Fixes by the `builder` at medium (no critical finding), then a re-check of the fix diff by the `reviewer` at medium.

**Re-check** _(reviewer, Opus 5.5 medium, `code-review` on `521a8e8..872dea4`, 2026-10-27)_ **APPROVE**: all ten "Fix now" rows fixed as decided, each test fails without its fix, no regression. Ran `pytest`: 420 passed, 2 skipped, 9 deselected. Six lows, decided by the lead:

| # | Finding | Decision |
|---|---|---|
| R1 | Delete-then-set leaves no stored token if the write fails after the delete (fails closed; a second launch can't sign in until the next start) | **Into the M1a.4 brief:** write first, then delete only the `<name>@<service>` leftover; M1a.4 owns second launches |
| R2 | Ctrl+C now reaches `sys.__excepthook__`, which prints the chained traceback unredacted | **Into the M1a.4 brief** (its "Ctrl+C exit 0" item): one fixed line through the redacting stderr handler |
| R3 | `X-Amz-*` pattern accepted only `=`, so the header/dict form wasn't masked | **Fixed by the lead** (`_SEP` in the pattern, one hypothesis family) |
| R4 | The `windows` marker text said "skipped on other systems" | **Fixed by the lead** (marker text says it's deselected by default) |
| R5 | §3 and the brief still showed the old `-m windows` command | **Fixed by the lead** (`--no-cov` added in both places) |
| R6 | A new stderr handler per failed write; a rollover Windows refuses loses later lines silently under pythonw | **Into the M1a.4 brief** (pythonw logging) |

## 6. Integration notes
_(lead, 2026-10-27)_
- The lead's follow-up commit (R3–R5): `pytest` 421 passed, 2 skipped, 9 deselected; ruff and format clean; `secure/` coverage 100 % (`.logs/m1a.2-lead-followups.log`).
- Not yet: push, PR and CI on GitHub (each needs the owner's yes); the brand tests (no brand file changed).
- M1a.3 was cut from `872dea4` and is rebased onto `main` after this merges.

## 7. Handover
_(lead, 2026-10-27)_ Built, reviewed (APPROVE), fixed, re-checked (APPROVE) and the re-check's small items handled. Branch `feat/m1a.2-security` is ready and **waits for the owner's yes to push, open the PR and merge on green**. Then: CHANGELOG line, status, and rebase M1a.3.
