Status: open
Tier: C (a screen from existing parts; the designer at high effort)
Usage: lead `claude-opus-5-5/high` (PC, orchestrator): 5-h 78 % at the brief

# T2: the Test button on Settings › Storage

T2 of the 2026-11-02 parallel plan ([11](../11-decisions.md)). The route it uses, `POST /api/storage/test`, is merged with m2.7 (#41); its brief and builder report are in [m2.7-s3.md](m2.7-s3.md).

## 1. Brief

### PRD IDs
UI-SET Storage, SET-02 (the Test), ERR-03 (the Test fails with the AWS reason).

### Agent and skills
- **`designer`**, Opus 5.5 at high, in its own worktree from `main` after #41. It never pushes. Load `frontend-design` first. Context7 for React or TanStack Query if an API is unclear.
- **Screenshots:** the built-in browser pane only (CLAUDE.md rule 10). No other agent uses a browser while the designer runs.

### Read first
- The approved mockup, `docs/05-design-system-appendix/mockup/js/screens-b.js`: `storagePage()` (line 530: the `test-row`, the result line, the S3 guide button, the cost hint) and `s3Steps()` (line 554: the three steps, each naming its key).
- [13](../13-content.md) §3, the row **"Storage Test (M2.7, proposed; shown in T2)"**: every API error, result line, step word, reason (with the forms for a null `aws_code`) and the left-behind line. Use them as written; propose any new string in the report.
- [m2.7-s3.md](m2.7-s3.md) §1 "The 3-step Test, exactly" (the response shape) and §6 "For T2"; `frontend/src/api/schema.d.ts` for the exact types.
- The existing Storage screen: `frontend/src/screens/settings/StoragePage.tsx`, `StorageView.tsx`, `storageModel.ts`, `storageWording.ts`, `frontend/src/api/storage.ts`, `frontend/src/styles/storage-backup.css`, and the store Test connection on Settings › Stores for the shared pieces (m2.5a).

### What to build
1. **The Test button** ("Test connection", the plug icon) in a `test-row`, in place of today's "Testing the bucket arrives…" line (remove `testLater` and its text from 13 if it's there):
   - It sends `POST /api/storage/test` (no body) through `api/storage.ts`.
   - It's disabled, with 13's `storage_not_set` line beside it, while the saved region or bucket is empty; and with the `keys_missing` line while either saved key pair is "Not set". Unsaved edits: test what's saved, and say so if the form has unsaved changes (propose the wording).
   - While it runs: busy state on the button, nothing else blocked.
2. **The result:** "Passed in <n> ms." or "Failed at the <write/read/delete> step: <reason>" (the first failed step), and the **three steps** list as in the mockup, each naming its key, with "Passed" / "Failed: <aws_code or reason>" / "Not run". The reason lines use the row's `<read and write / read-only>` key word and `<region>` from the saved settings; handle a null `aws_code` and a null `http_status`.
3. **Left behind:** when `left_behind` is set, the warning line with the key in IBM Plex Mono.
4. **Errors:** 409 `busy`, `storage_not_set`, `keys_missing`; 503 `secrets_unavailable` (the shared line), each from 13.
5. **The cost hint** under the row, as in the mockup ("about 4 small S3 requests, a tiny AWS charge"), and the S3 guide button that opens the Help panel's guide (m2.5a).
6. A pure, tested `planStorageTest(...)` (or similar) that turns the saved settings and keys into "can test / why not", and a pure formatter from the response to the lines, per CLAUDE.md "Screen code layers" (no logic inside the component).

### Checking it in the pane
Run the real app with in-memory stores and a local moto server as the endpoint, so the Test really runs: a script like `C:\Users\r4rup\AppData\Local\Temp\claude\D--BUSINESS-3--CHILD-PROJECTS-1--GPL-PROJECTS-OTHER-ASSETS-SOFTWARE-shelf-sync\4623b6b4-245e-4d34-8d4e-5dcbed53d755\scratchpad\harness.py` (the real `create_app`, `MemorySecretStore`, a fresh single-use sign-in link written to a file every 45 s; copy it into your worktree's `.logs\` and extend it) plus `moto.server.ThreadedMotoServer(ip_address="127.0.0.1", port=0)` with one bucket made. Set the endpoint to `http://127.0.0.1:<port>` (the settings allow `http` only to 127.0.0.1 or localhost), any region, the bucket, and any key pairs (moto without IAM accepts them). Cases to show, in light and dark at 1280: never tested; passed; failed at write (a bucket that doesn't exist → `bucket_missing`); the button disabled (empty bucket; a key pair not set); busy (409, two clicks); left behind (if you can't produce it for real, cover it in a unit test and say so). Never point it at a real AWS bucket. Turn transitions off in captures, and keep the pointer off the page (hover changes colours).

### Files
- Screens only: `frontend/src/screens/settings/**` (Storage files), `frontend/src/api/storage.ts`, `frontend/src/styles/storage-backup.css`, their tests; `docs/13-content.md` (only the Storage rows); this run file.
- **Never touch:** `backend/**`, `packaging/**`, `testenv/**` and `tools/**` (T3 works there now), `pyproject.toml`, `uv.lock`, `docs/10-status.md`, `CHANGELOG.md`.

### Done
- In `frontend/`: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npm run schema:check` pass (through `bash tools/heavy.sh --log t2-<name> …`).
- The cases above shown in the pane, shots in `.logs/shots/t2/`, the console clean (no CSP error).
- The designer report (§4): files, commands and results, shots, any new strings, confirmation that `frontend-design` was loaded first.

### Out of scope
- The wizard's Test row (UI-WIZ, M3). A shell S3 health chip and "uploads are held" (M5).

## 4. Designer report

## 5. Review

## 6. Integration notes

## 7. Handover
_(lead, 2026-11-02)_ Brief written. Next: the designer.
