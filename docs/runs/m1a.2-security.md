Status: open
Tier: A
Usage: `analyst claude-opus-5-5/high` (brief draft; no skill: `security-review` and `code-review` need a diff, none existed); lead at Opus 5.5 high for the final brief (12 §3, key step 1); 5-h 23 % at the start of the draft

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
    - Run them with `bash tools/heavy.sh --log m1a.2-windows-checks uv run pytest -m windows`.
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

## 3. Builder report
_(Interim, up to the early-check stop; the final report is written when the builder finishes.)_

**Skills:** none of the 09 §3 skills fits the builder here: `security-review` and `code-review` are the reviewer's; `aws-sdk-python-usage` and `aws-iam` (no S3 or IAM code); `frontend-design`, `dataviz`, `artifact-design` (no screens); `run` (no browser or running-app check needed). Context7 was used for every library in the brief.

**Item 1 evidence:** `tests/test_server.py::test_socket_is_bound_to_loopback_never_all_interfaces` (M1a) plus `tests/test_startup_security.py::test_the_uvicorn_config_host_is_loopback`.

**Packages:** `uv lock` added exactly `keyring 25.7.0`, `jaraco-classes 3.4.0`, `jaraco-context 6.1.2`, `jaraco-functools 4.6.0`, `more-itertools 11.1.0`, `pywin32-ctypes 0.2.3`; `uv export` shows each with `; sys_platform == 'win32'`.

**Item 13, covered so far** (C7 = Context7, E = checked by running it on the pinned versions):
- Starlette 1.7.0 (C7 lists 1.0.0 and 1.8.0, not 1.7.0; behaviour checked on 1.7.0 itself): the docs recommend pure ASGI middleware (BaseHTTPMiddleware breaks contextvars propagation and is awkward for SSE), so the guard and the headers are pure ASGI. `ServerErrorMiddleware` is always the outermost layer, so a user middleware's headers do not reach its 500 (C7, E). 404, 405 and 422 do pass through user middleware and get the headers (E). Raw `host` headers come from `scope["headers"]`, a list of `(bytes, bytes)` with duplicates kept (C7).
- FastAPI 0.143.0: the default 422 body includes `input` (C7 example, E). `set_cookie(key, value, max_age, expires, path, domain, secure, httponly, samesite)` defaults give no Domain, Expires, Max-Age or Secure (C7, E; output `HttpOnly; Path=/; SameSite=strict`). `add_exception_handler` for `ApiError`, `RequestValidationError` and `Exception`; the `Exception` one is what `ServerErrorMiddleware` calls (C7, E). `app.routes` holds `_IncludedRouter` objects (E, source read).
- uvicorn 0.54.0 / h11 0.16.0 (E, raw sockets against a real server): see the early-check point 4. With `log_config=None` and no handler, h11's "Invalid HTTP request received." (a `uvicorn.error` WARNING) goes to stderr through `logging.lastResort`; with our file handler on the root logger nothing reaches stdout or stderr. INFO records don't reach `lastResort`.
- TestClient (Starlette 1.7.0 with httpx 0.28.1): default host `testserver` (E), `base_url="http://127.0.0.1:<port>"` works, the cookie jar keeps `shelfsync_session` for the IP host (E). It prints a `StarletteDeprecationWarning` asking for `httpx2` (not installed; no package may be added here).
- stdlib: `hmac.compare_digest("é", "é")` raises `TypeError: comparing strings with non-ASCII characters is not supported` (E), hence bytes. `logging.lastResort`, `captureWarnings`, `sys.excepthook`, `threading.excepthook`: item 9, not yet.
- coverage 7.16.2 (C7, docs for file patterns): a pattern ending `/*` is treated as `/**`, so `--include=backend/shelfsync/secure/*` also matches subfolders.
- keyring 25.7.0: the Windows backend's `get_password` returns `None` for a missing entry; `delete_password` raises `PasswordDeleteError` when nothing matched; errors derive from `KeyringError` (`InitError`, `NoKeyringError`, `PasswordDeleteError`, `PasswordSetError`); the package ships `py.typed` (E, file present).
- mypy (C7): by default it takes `sys.platform` from the running system and treats a `sys.platform == "win32"` block as unreachable on Linux. Verified: with the keyring package hidden, `mypy --platform linux` passes and `--platform win32` fails with import errors. No per-module override is needed.
- uv: the lock has the six packages only under `sys_platform == 'win32'` (see Packages).
- WooCommerce key format (C7 `/woocommerce/woocommerce-rest-api-docs`): shows `ck_…` and `cs_…` placeholders only; the "40 hex" length is **not** stated there, so the pattern accepts any run of 20 or more letters and digits. GitHub prefixes (C7 `/github/docs`, "About authentication to GitHub"): `ghp_`, `github_pat_`, `gho_`, `ghu_`, `ghs_`, `ghr_`.

**Coverage** (`coverage report --include="backend/shelfsync/secure/*"`): `headers.py` 26/0/10/0 100 %, `middleware.py` 74/0/30/0 100 %, `redact.py` 30/0/6/0 100 %, `sessions.py` 61/0/14/0 100 %, `token.py` 37/0/2/0 100 %, `__init__.py` 0 stmts; total 228 statements, 62 branches, 100 %.

**Commands so far:** `uv lock`, `uv sync --locked`; `bash tools/heavy.sh --log m1a.2-mypy uv run mypy` (exit 0, 26 files); `bash tools/heavy.sh --log m1a.2-pytest uv run pytest` (351 passed); `bash tools/heavy.sh --log m1a.2-bandit uv run bandit -r backend -q` (exit 0; two `# nosec B105` on names that only contain the word "token", each with its reason on the line above); `uv run ruff check backend tests` and `ruff format` clean.

## 4. Designer report
_(none: no screens)_

## 5. Review
_(empty)_

## 6. Integration notes
_(empty)_

## 7. Handover
_(lead, 2026-10-27)_ Final brief written at Opus 5.5 high from the analyst's draft. The owner said yes to keyring in M1a.2, to its exact pins (keyring 25.7.0 and five Windows-only dependencies) and to in-memory sign-ins (2026-10-27). Next step: once merged, start the `builder` (Sonnet 5.5, high) in its worktree on `feat/m1a.2-security`.
