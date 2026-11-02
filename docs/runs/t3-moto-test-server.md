Status: closed (merged as #43, 2026-11-02)
Tier: B (12 §2: the test stack); the analyst's early check was skipped by the lead's error, recorded in 11
Usage: lead `claude-opus-5-5/high` (PC, orchestrator): 5-h 78 % at the brief; builder `claude-opus-5-5/high` [aws-sdk-python-usage]; reviewer `claude-opus-5-5/high` [code-review] (+ its built-in read-only helper, Opus 5.5 high), review and re-check; no analyst early check (the Tier C mistake, §6) (from `node tools/model-audit.mjs 2026-11-02`; per-agent 5-hour readings weren't kept, the night's readings are in 10's Usage)

# T3: the moto S3 server for the test stack (m2.8, the moto part)

T3 of the 2026-11-02 parallel plan ([11](../11-decisions.md)). The test stack is [07 §5](../07-testing.md) and [04 §10](../04-architecture.md) (`testenv/`): a LocalWP site with WooCommerce and the owner's Amazon S3 Storage extension, its "User defined" endpoint pointing at moto server (04-A V6–V8). The LocalWP site, WooCommerce and the extension are the owner's (m2.8's other half); this task builds only the moto side, so it's ready when the owner sets up LocalWP. moto 5.2.4 (`moto[s3]` + flask + flask-cors) is locked (#37).

## 1. Brief

### PRD IDs
None directly; it serves 07's integration tests (M5) and the M2 exit test ("the test stack tests green").

### What to build
1. **`testenv/moto_s3.py`**: one command that starts moto's S3 server for the test stack and keeps it running until Ctrl+C:
   - bound to **127.0.0.1 only** (never `0.0.0.0`, moto's default), on a fixed port given by `--port` (propose a default that isn't ShelfSync's 47615 and isn't commonly taken; say why);
   - creates the test bucket (`--bucket`, a default such as `shelfsync-test-stack`) with an optional `--region`;
   - prints the endpoint (`http://127.0.0.1:<port>`), the region and the bucket, and states that any key pair works (moto without IAM), so the owner can paste them into ShelfSync's Settings › Storage and the extension;
   - state is in memory only (says so); nothing is written outside a `--data` folder if you add one (only if moto supports it cleanly; otherwise in memory and say so).
   Run it with `UV_PYTHON_DOWNLOADS=never uv run python testenv/moto_s3.py`.
2. **V8, presigned URLs:** a pytest test (in `tests/`) that starts `ThreadedMotoServer` on 127.0.0.1 port 0, puts an object, makes a presigned GET URL with a plain boto3 client **in the test only** (ShelfSync's own client never presigns, m2.7 L-rules), and fetches it with httpx: 200 and the bytes; an expired or tampered URL: refused (or record that moto doesn't check, as m2.7 did for Content-MD5). Update 04-A V8's row to close or record it, with the date and the test.
3. **A test of the script itself** (start it in a thread or subprocess on port 0 or a free port, check the bucket exists and that it listens on 127.0.0.1 only, then stop it).
4. **Runbook** `docs/runbooks/test-stack.md` (new): how to start moto (the command, what it prints, how to stop it), how to set ShelfSync's Settings › Storage to it and run the Storage Test, and a placeholder section "LocalWP and the S3 extension (the owner's, m2.8)" that names the open question in [runs/m2.0-plan.md](m2.0-plan.md) §3 Q3 (WooCommerce over HTTPS on LocalWP) without deciding it. Add the runbook to `docs/runbooks/README.md`'s list.

### Rules
- No live AWS, bucket or store call. The conftest `no_outbound_network` guard stays on (loopback is allowed).
- `UV_PYTHON_DOWNLOADS=never` for every uv command; heavy runs through `bash tools/heavy.sh --log t3-<name> …` (the lock is shared; wait).
- Is `testenv/` linted? It's not under `backend/` or `tests/`; keep the script clean with ruff and mypy anyway, and say whether `pyproject.toml`'s ruff `src`/`extend-exclude` cover it (don't change `pyproject.toml` without saying why in the report; a one-line `extend-exclude` or `src` change is allowed if needed).

### Files
`testenv/**`, the new tests under `tests/`, `docs/runbooks/test-stack.md`, `docs/runbooks/README.md` (one line), 04-A's V8 row, this run file. **Never touch:** `backend/**`, `frontend/**` (T2 works there now), `packaging/**`, `uv.lock`, `docs/10-status.md`, `CHANGELOG.md`.

### Done
The full `uv run pytest`, `ruff check`, `ruff format --check`, `mypy`, `mypy --platform linux` pass; the script was run for real on this PC once (output in the report) and the Storage Test against it passes through ShelfSync's own client in a test (the m2.7 V8 test already does this with `ThreadedMotoServer`; reuse it if it fits); the builder report (§3) lists commands with results and what's not verified.

### Out of scope
LocalWP, WooCommerce, the S3 extension and V6 (the owner's); the one-script LocalWP setup with sample products (later in m2.8, after the owner's LocalWP choice).

## 3. Builder report
_(builder, `claude-opus-5-5/high`, 2026-11-02; branch `t3/moto-test-server-build` from `feat/t3-moto-test-server` @ `a8a2d11`; commits `f88957e` code and tests, `f5454a5` docs, this report)_

### Skills and tools loaded
- **`aws-sdk-python-usage`** (09 §3, S3 code and the moto endpoint): loaded; its S3 reference set the presign call (`generate_presigned_url("get_object", Params=..., ExpiresIn=...)`), closing every `StreamingBody`, and the `main()`/exit-code shape of the script (no `sys.exit` outside `__main__`).
- **Context7** (`/getmoto/moto`, server mode): `ThreadedMotoServer(ip_address, port=0)`, `get_host_and_port()`, moto's `0.0.0.0` warning, the reset API; it says nothing on persistence or presigned checks, so those were read from moto 5.2.4's source in the locked venv (`moto/s3/responses.py` `_key_response`, `moto/iam/access_control.py`, `moto/core/authorization.py`, `moto/settings.py`) and then measured (below).
- Not used: `aws-iam` (no IAM policy written; the test's one inline policy only makes moto's IAM path run), `security-review` / `code-review` / `simplify` (the reviewer's), `run` (no app change), the browser pane (the designer has it; nothing visual here), `frontend-design` (no screen).

### Files
- `testenv/__init__.py`, **`testenv/moto_s3.py`** (new): `start(port, bucket, region) -> MotoS3`, `main(argv, wait)`, `s3_client(...)`, `banner(...)`. moto's own WSGI app (`DomainDispatcherApplication(create_backend_app)`, what `ThreadedMotoServer` runs) in a werkzeug `ThreadedWSGIServer` subclass bound to **127.0.0.1**, with `SO_EXCLUSIVEADDRUSE` on Windows (`SO_REUSEADDR` there would let a second socket bind the same port; `ThreadedMotoServer` would also hang forever on a busy port, as its ready event is never set). A busy port raises `PortUnavailable` (main: message, exit 1) instead of werkzeug's `sys.exit`. Its request log drops the query string (a presigned URL's holds the key ID) and unprintable characters. The bucket is made with a botocore client that ~~reads no `~/.aws` file, `AWS_*` variable or proxy~~ (only partly true, review finding 2: since the fix it's ShelfSync's own `make_client`, §5). Output goes through `sys.stdout.write` (ruff's T20 applies outside `tests/`).
  - **Default port 47630:** outside ShelfSync's 47615-47624 (SET-06), below Windows' ephemeral range 49152-65535 (no outgoing connection ever holds it), not moto's/Flask's 5000, and outside this PC's only excluded TCP range (50000-50059, `netsh interface ipv4 show excludedportrange protocol=tcp`). Not checked against LocalWP's own site ports (LocalWP isn't installed yet).
  - **Defaults:** bucket `shelfsync-test-stack`, region `us-east-1` (no `LocationConstraint`; any other region gets one). `--port 0` takes any free port (the tests use it).
  - **No `--data`:** moto 5.2.4 has no state file (its recorder replays requests; it isn't a store), so in memory only, and the script and runbook say so.
- **`tests/test_testenv_moto_s3.py`** (new, 14 tests): binds 127.0.0.1/AF_INET only and makes the bucket (region checked with a random made-up key pair: any pair works); default region; on Windows a `SO_REUSEADDR` socket can't share the port; a busy port is reported (both `start` and `main`, exit 1), not hung; `main` prints endpoint/region/bucket/keys/127.0.0.1/in-memory lines and stops on Ctrl+C (KeyboardInterrupt), port closed after; bad `--port`/`--region` refused; a bucket name botocore refuses is reported (exit 1); the request log has no query string or control character; **ShelfSync's own Storage Test passes against the script's server** (127.0.0.1 and localhost, through `make_storage_rig`, the real API and `make_client`; nothing left in the bucket); **the real command** in its own process (`python -I testenv/moto_s3.py --port 0`): banner read from stdout, bucket checked, then ended (`terminate` on Windows; off Windows SIGINT and "Stopped." with exit 0).
- **`tests/test_moto_presigned_v8.py`** (new, 4 tests): `ThreadedMotoServer(ip_address="127.0.0.1", port=0)`; plain boto3 presigning client in the test only.
- `docs/runbooks/test-stack.md` (new): start, what it prints (the real output), stop; Settings › Storage values and made-up key pairs that pass ShelfSync's key shape check; the Storage Test and the four requests it shows (`PUT` 200, `GET` 200, `DELETE` 204, `HEAD` 404, seen in a test's log); a warning that saving the test endpoint and keys replaces the real ones; the LocalWP/S3 extension placeholder naming m2.0-plan §3 Q3 without deciding it.
- `docs/runbooks/README.md`: the `test-stack.md` row moved from "Added when their milestone is built" into the main list (one row out, one in).
- `docs/04-architecture-appendix/A-stack-verification.md`: V8 row, presigned URLs closed with the date, tests and differences.
- Not touched: `backend/**`, `frontend/**`, `packaging/**`, `uv.lock`, `pyproject.toml`, `docs/10-status.md`, `CHANGELOG.md`.

### V8, presigned URLs: what moto 5.2.4 does (measured, then pinned in tests)
| Case | Real S3 | moto 5.2.4 server (no IAM checks, the default) |
|---|---|---|
| Good presigned GET | 200 + bytes | **200 + bytes** |
| Signed 2 h ago, `ExpiresIn=60` (botocore's signing clock moved back) | 403 | **200 + bytes** (expiry not checked) |
| One character of `X-Amz-Signature` changed | 403 | **200 + bytes** (signature not checked) |
| Same query, path pointed at another key | 403 | **200 + the other file** |
| Any presigned GET with IAM checks on (`INITIAL_NO_AUTH_ACTION_COUNT=0`) | as above | **500** (KeyError on `Authorization`; a signed SDK GET still works) |

So the test stack can show a store's download link works (V6 can be tried) but can't prove expiry or tamper refusal; recorded in V8 for M5/M6, as m2.7 recorded `Content-MD5`.

### Commands and results
- `UV_PYTHON_DOWNLOADS=never uv sync --locked` (new worktree venv): OK, no lock change.
- While working: `uv run pytest tests/test_testenv_moto_s3.py tests/test_moto_presigned_v8.py tests/test_s3_moto_v8.py --no-cov`: **22 passed** (60 s; the `localhost` Storage Test case takes about 8.6 s against 0.8 s for `127.0.0.1`, so the runbook says to use `127.0.0.1`; the cause, presumably `::1` tried first, isn't verified).
- `bash tools/heavy.sh --log t3-pytest uv run pytest`: **2611 passed, 18 skipped, 52 deselected** in 325 s, exit 0; coverage TOTAL 93 % (coverage measures `backend/shelfsync` only, so `testenv/` isn't in it).
- `bash tools/heavy.sh --log t3-mypy uv run mypy`: no issues in 75 files. `... --log t3-mypy-linux uv run mypy --platform linux`: no issues in 75 files.
- `uv run mypy testenv` and `uv run mypy --platform linux testenv` (strict, from `pyproject.toml`): no issues in 2 files. `uv run mypy --platform linux --follow-imports=silent` on the two new test files: no issues.
- Final lint, once: `bash tools/heavy.sh --log t3-lint uv run ruff check`: all passed; `uv run ruff format --check`: 176 files formatted.
- **`pyproject.toml` coverage of `testenv/`:** ruff **does** lint and format it (`ruff check --show-files` lists `testenv/__init__.py` and `testenv/moto_s3.py`; it's not in `extend-exclude`, and `src` only affects import sorting: `testenv` sorts as third-party in tests). **mypy does not** (`packages = ["shelfsync"]`), so it was run by hand as above. No `pyproject.toml` change; adding `testenv` to mypy's `packages` (one line) would make CI check it: the lead's call.

### The script, run for real on this PC (once)
`UV_PYTHON_DOWNLOADS=never uv run python testenv/moto_s3.py` (defaults), stdout:
```text
ShelfSync test stack: moto S3 server (moto 5.2.4)
  Endpoint  http://127.0.0.1:47630
  Region    us-east-1
  Bucket    shelfsync-test-stack
  Keys      any made-up access key ID and secret work: this server checks no keys.
            Never type real AWS keys here.
Listening on 127.0.0.1 only: nothing outside this PC can reach it.
Everything is kept in memory only: stopping the server removes the bucket and every file in it.
Press Ctrl+C to stop.
```
A probe from another process (made-up keys `made-up-id`/`made-up-secret`): `head_bucket` 200, region `us-east-1`; put/get/delete of `probe.txt` worked, 0 keys after. `netstat -ano -p TCP`: `TCP 127.0.0.1:47630 0.0.0.0:0 LISTENING` (the only listener on that port: nothing on `0.0.0.0`). stderr, the request log: `"PUT /shelfsync-test-stack" 200`, `"HEAD /shelfsync-test-stack" 200`, `"PUT .../probe.txt" 200`, `"GET .../probe.txt" 200`, `"DELETE .../probe.txt" 204`, `"GET /shelfsync-test-stack" 200`. Then the process was ended with `Stop-Process` (not Ctrl+C).

### Not verified
- **Ctrl+C in a real console.** Covered in-process (`main` with a wait that raises `KeyboardInterrupt`) and, off Windows only, by SIGINT to the real process in `test_the_script_run_as_a_command` (CI). On Windows a test can't send Ctrl+C to one child process, and the real run above was ended with `Stop-Process`. The owner's first run of the runbook checks it.
- **The Storage Test from the running app's screen** (Test connection): T2 is building it; proven through the API and ShelfSync's own client in tests only.
- **V6** (the S3 extension against moto) and everything LocalWP: the owner's, m2.8.
- Whether LocalWP's own ports ever use 47630.

### Open questions (for the lead)
1. Add `testenv` to mypy's `packages` in `pyproject.toml` so CI type-checks it? (I didn't; the brief allows only a ruff `src`/`extend-exclude` line.)
2. The runbook names the button "Test connection" from T2's brief; if T2 lands with other wording, `docs/runbooks/test-stack.md` §2 step 6 needs that one line changed.

## 5. Review
_(reviewer `claude-opus-5-5/high`, `code-review` (applied by hand to the worktree diff) and `security-review`'s method by hand, 2026-11-02, on `a8a2d11..7c3a08f`)_ **APPROVE**, 8/10, with medium findings 1–4 and lows 5–10 below; its run: 18 passed. **Re-check of the fix diff** (`7c3a08f..d723485`): **APPROVE**, 9/10; the Host check holds against near-miss hosts, trailing dots, case, IPv6 and a missing Host (an absolute-form request line can set the host, but only a local process sends one, and a local process can already do anything); its run: 24 passed, mypy and `mypy --platform linux` clean on 77 files. Three new lows: the ruff `src` entry for `testenv` had no effect, two near-miss hosts weren't pinned by a test, and the CORS switch is process-wide (harmless).

_(reviewer, via the lead, 2026-11-02)_ **APPROVE 8/10**, medium findings to fix before merge. A re-check of the fix diff follows.

| # | Sev. | Finding | Resolution (builder, 2026-11-02) |
|---|---|---|---|
| 1 | medium | moto's `create_backend_app` turns CORS on for every origin unless disabled, and the dispatcher sends any Host to S3: any web page (or a DNS-rebinding page) could read, write or `/moto-api/reset` the server | **Fixed.** `start()` sets `moto.moto_server.werkzeug_app.DISABLE_GLOBAL_CORS = True` (verified for 5.2.4: that module copies `moto.settings.DISABLE_GLOBAL_CORS` at import, so setting `moto.settings` afterwards does nothing; the copy is read in `create_backend_app` when the S3 app is made at the first request). The app is wrapped in `_LoopbackHostOnly`: 403 unless `Host` is `127.0.0.1:<port>` or `localhost:<port>`. Tests: `Host: evil.example`, `evil.example:47630`, `127.0.0.1` without the port and no Host all get 403, `/moto-api/reset` too (the bucket survives); a GET and an OPTIONS preflight with an `Origin` get no `Access-Control-Allow-Origin`; a recorded test shows plain moto 5.2.4 does send it. Runbook §1 and 04-A V6 note the extension's links must be navigations (V6 to confirm, the owner's) |
| 2 | medium | `s3_client` only partly isolated (`AWS_USE_FIPS_ENDPOINT`/`AWS_USE_DUALSTACK_ENDPOINT` and other `AWS_*` read) | **Fixed.** `s3_client` now puts `backend/` on `sys.path` (when run as a script) and returns ShelfSync's own `shelfsync.apply.s3.make_client` client (session-variables table, `use_fips_endpoint=False`, `use_dualstack_endpoint=False`, built-in Loader only). Docstring and the §3 claim corrected |
| 3 | medium | Runbook: "write your real settings down … Replace keys" can strand the real keys (ShelfSync never shows a saved secret; AWS shows it once) | **Fixed.** §2 now says: only while no real AWS keys are saved; endpoint, region and bucket can be noted; secret keys can't be put back; never write a secret down; if real keys are saved, skip the section or plan new keys afterwards with `key-rotation.md` |
| 4 | process (lead) | Tier should have been B (12 §2 names the test stack) | Tier line changed as the lead asked; the lead adds the 11 row |
| 5 | low | Expired-URL premise not asserted | **Fixed.** `signed_two_hours_ago` asserts the URL's `X-Amz-Date` is at least 1 h before now |
| 6 | low | `log_error` not overridden ("Bad request syntax" line keeps `?…`) | **Fixed.** `log_error` and `log_message` go through `scrub()` (query strings become `?...`, unprintables `?`, 300 characters max); the log test sends a malformed request line with a query and checks no line holds it |
| 7 | low | Runbook: two commands in one block | **Fixed.** `$env:UV_PYTHON_DOWNLOADS='never'` and `uv run python testenv/moto_s3.py` are separate blocks |
| 8 | low | Test name says moto refuses the bucket and the server stopped; botocore refuses it and the stop isn't checked | **Fixed** by renaming it `test_a_bucket_name_botocore_refuses_is_reported` |
| 9 | low | Cleanup `setup_client("s3")` and the `iam` client not closed | **Fixed.** Both closed in `finally` |
| 10 | ruling | Add `testenv` to ruff `src` and mypy `packages` | **Done.** `pyproject.toml`: `src = ["backend", "tests", "testenv"]`, `packages = ["shelfsync", "testenv"]` |

**Commands after the fixes:**
- `uv run pytest` on the two new test files while working: 24 passed.
- `bash tools/heavy.sh --log t3-pytest-fix uv run pytest`: **2617 passed, 18 skipped, 52 deselected**, exit 0 (6 more than before: the 4 Host cases and the 2 CORS tests).
- `bash tools/heavy.sh --log t3-mypy-fix uv run mypy`: no issues in **77** files (testenv now included).
- `bash tools/heavy.sh --log t3-mypy-linux-fix uv run mypy --platform linux`: no issues in 77 files.
- `bash tools/heavy.sh --log t3-lint-fix uv run ruff check`: all passed. `uv run ruff format --check`: 176 files formatted.

**Not verified by the fixes:** the script wasn't run for real again on this PC after them (the subprocess test runs the real command with `--port 0` and passed, including the Host check, since botocore sends `Host: 127.0.0.1:<port>`). Whether the S3 extension's requests send a matching `Host` (they should, for an endpoint of `http://127.0.0.1:47630`) is part of V6.

## 6. Integration notes
_(lead, 2026-11-02)_ Integrated on `feat/t3-moto-test-server-int` (the builder's four commits plus the lead's):
- The re-check's lows 1 and 2, fixed by the lead: `pyproject.toml` drops `testenv` from ruff's `src` and names it in `[tool.ruff.lint.isort] known-first-party` (so `from testenv import moto_s3` sorts first-party); the Host test gains `127.0.0.1:<port>.evil` and `localhost.:<port>`, filled with the server's real port (6 passed).
- **Tier:** this task should have been Tier B (12 §2 names the test stack), with the analyst's early check; the lead set it to C by mistake. Recorded in 11; the two reviews (8/10, then 9/10) found what an early check would have.
- **Open, the owner's:** V6 (whether the S3 extension works against this server, with CORS off and the Host allowlist), Ctrl+C in a real console, and the LocalWP half of m2.8 (m2.0-plan §3 Q3).

## 7. Handover
_(lead, 2026-11-02)_ Brief written. Next: the builder.

_(lead, 2026-11-02, 08:20 IST)_ Merged on green as [#43](https://github.com/techaust/shelf_sync/pull/43). Its worktree and branch are removed from git; the folder `.claude/worktrees/agent-a61cf7b116d52998a` stays on disk (paths too long for `git worktree remove` to delete, and the app blocks a long-path delete), harmless, for the owner to delete in File Explorer. Task closed.
