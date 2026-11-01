Status: open
Tier: C (test tooling: nothing shipped, no live system; builder → reviewer)
Usage: lead `claude-opus-5-5/high` (PC, orchestrator): 5-h 78 % at the brief

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

## 5. Review

## 6. Integration notes

## 7. Handover
_(lead, 2026-11-02)_ Brief written. Next: the builder.
