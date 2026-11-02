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
_(designer, `claude-opus-5-5/high`, 2026-11-02; branch `design/t2-storage-test-screen` cut from `feat/t2-storage-test-screen` at `ac7fef6`, own worktree, nothing pushed)_

**Skills and tools:** `frontend-design` was loaded first, before any file was read. It changed three things: (1) a plan before code, with one bold element only: the three steps as an ordered list with a rail between the marks that turns dashed below a step that didn't pass; (2) a self-critique pass on screenshots, which moved the S3 guide button (below); (3) restraint: no per-step milliseconds, no new card heading. `dataviz` wasn't loaded: there is no chart, KPI tile or report here. Context7 wasn't needed (the TanStack Query and React APIs used are the ones the page already uses). Browser: the built-in pane only.

**What was built**
- **The Test card** (`StorageTestCard`) replaces m2.5b's dashed "Testing the bucket arrives…" note, as a card of its own under the keys, because the Test checks both cards above it. It holds: Test connection (plug icon) and its line; under them, the unsaved-changes note, the three steps, the left-behind warning, then the 13 §6 cost hint beside the S3 access policy guide (which opens the Help panel's `s3-policy` guide).
- **Can't test:** the button stays focusable with `aria-disabled` and `aria-describedby` pointing at the reason, shown where the result goes: 13's `storage_not_set` line while the saved region or bucket is empty, else 13's `keys_missing` line while either saved pair is "Not set". "Couldn't be read" keys are left to the server (`secrets_unavailable` or `keys_missing`).
- **Unsaved edits:** the Test tests what is saved, and says so under the button while the settings form is dirty (proposed string below).
- **Running:** spinner on the button, `aria-busy`, the progress line; nothing else is blocked. The run is kept per tab in `lib/storageTest.ts` (like `storeTests`), so leaving the page and coming back keeps it, and a second click sends nothing.
- **Result:** "Passed in <n> ms." (thousands separators, tabular numbers) or "Failed at the <step> step: <reason>" for the first failed step, plus 13's "Tested <date> at <time> <zone>." Each step: "Write a test file / Read it back / Delete it" + "with the <read and write / read-only> key" (mockup) + "Passed" / "Failed: <aws_code>" / "Not run". Reasons use the failed step's own key word and the region the test ran against; null `aws_code` and null `http_status` each have a form.
- **Left behind:** the warning alert with the key in IBM Plex Mono (it wraps anywhere).
- **Errors:** 409 `busy` (info tone), `storage_not_set`, `keys_missing`, 503 `secrets_unavailable` (the shared line), any other refusal, and no answer.
- **Stale answers:** a save that changes the endpoint, region or bucket, and any key save or removal, forget the last answer. Changing only the files to keep or the template doesn't.
- **Pure and tested:** `planStorageTest(saved, formDirty)`, `testedValuesChanged`, `testAnswerView`, `testFailureLine`, `storageTestView` in `screens/settings/storageTestModel.ts`; no logic in the components.
- **Deviation from the mockup (for the reviewer):** the guide sits beside the cost hint, not in the button's row. In the first pass it shared the row, and the ERR-03 line was squeezed into a column about 270 px wide over four lines (seen in the pane). With the guide in the foot, the line gets the card's width. Tab order is still Test, then guide.

**Files**
- New: `frontend/src/lib/storageTest.ts`, `frontend/src/lib/storageTest.test.ts`, `frontend/src/screens/settings/storageTestModel.ts`, `frontend/src/screens/settings/storageTestModel.test.ts`.
- Edited: `frontend/src/api/storage.ts` (`testStorage`, `StorageTest` types), `frontend/src/screens/settings/StoragePage.tsx`, `StorageView.tsx` (the note is gone, `StorageTestCard` added), `storageModel.ts` (`testLines` removed), `storageWording.ts` (`testLater` and `testNeeds` removed; the Test's strings, each tagged with its source), `storageModel.test.ts`, `storageBackupViews.test.ts`, `frontend/src/styles/storage-backup.css` (`.storage-note` replaced by the Test card's rules, tokens only), `docs/13-content.md` (Storage rows only), this file.
- Not touched: `backend/`, `packaging/`, `testenv/`, `tools/`, `tests/`, `pyproject.toml`, `uv.lock`, `10-status.md`, `CHANGELOG.md`.

**Commands** (in `frontend/`; heavy ones through `bash tools/heavy.sh --log t2-<name>`)
| Command | Result |
|---|---|
| `npm ci` (the worktree had no `node_modules`) | 146 packages, from the lock |
| `UV_PYTHON_DOWNLOADS=never uv sync --locked` (for the harness) | the locked set; no package added |
| `npm run lint` (`t2-lint`) | `biome ci`: 130 files, no fixes |
| `npm run typecheck` (`t2-typecheck`) | pass |
| `npm test` (`t2-test`) | **32 files, 1048 tests passed** |
| `npm run build` (`t2-build`) | built |
| `npm run schema:check` (`t2-schema`) | `schema.d.ts` is current |

**Checked in the pane:** the real app (`create_app`, in-memory stores) and a local `ThreadedMotoServer` on 127.0.0.1 with bucket `sample-t2-bucket`, plus a 127.0.0.1 port that accepts and never answers. The harness is `.logs/t2/harness.py`, git-ignored. All values are made-up sample values; nothing pointed at AWS or a store. Every Test shown is a real Test against these local endpoints:
- passed (52 ms, moto);
- failed at write, `bucket_missing` (`sample-t2-missing-bucket`, ERR-03);
- the silent port gave `timeout` at the write step **with a real `left_behind`**;
- a reload during that run, then a second Test, gave a real **409 `busy`**;
- disabled with the bucket saved empty, and with the read-only pair removed;
- the unsaved-changes note.

Keyboard pass: Remove keys → Test connection (visible ring) → S3 access policy guide; Enter opens the Help panel on the S3 guide, and Escape returns the focus to the guide button. Console: no CSP or script errors. The only entries are a 404 from my own mistyped non-hash URL and the two deliberate 409 `busy` answers. Fixed after the pass: a space so the live region reads "…answer. Tested …" instead of running the two sentences together.

**Shots** (`.logs/shots/t2/`, not committed; the pane's own captures, about 800 px wide; 1280 × 900 unless the name says 1024 × 768; transitions settled and the pointer off the controls, except `03-running-light`, where it rests on the busy button):
- `01-disabled-keys-missing-{light,dark}-1280.jpg`: the read-only pair removed; 13's `keys_missing` line (it wins over the unsaved note).
- `02-never-tested-{light,dark}-1280.jpg`: "Not tested yet.".
- `03-running-{light,dark}-1280.jpg`: busy button and progress line.
- `04-passed-{light,dark}-1280.jpg`: Passed in 52 ms, three passed steps.
- `05-unsaved-note-{light,dark}-1280.jpg`: the note under the button, last result kept.
- `06-failed-write-bucket-missing-{light,dark}-1280.jpg`: ERR-03, "Failed: NoSuchBucket", two "Not run".
- `07-busy-409-{light,dark}-1280.jpg`: "A test of the bucket is already running.".
- `08-timeout-left-behind-{light,dark}-{1280,1024}.jpg`: timeout at write, the step word "Failed" (no code, no status), the left-behind key in Plex Mono.
- `09-disabled-bucket-empty-{light,dark}-1280.jpg`: 13's `storage_not_set` line; the old answer forgotten.

**New strings (proposed, in 13's Storage Test row and in `storageWording.ts` as "proposed (T2)")**
1. Running: "Testing the bucket. This can take up to a minute." (after the stores' line; the Test's limit is 30 s plus 5 s grace).
2. Unsaved edits: "The test uses the saved settings. Save your changes to test them."
3. A failed step with no code: "Failed: HTTP <status>"; with no status either: "Failed". 13's "Failed: <aws_code or reason>" would otherwise show a code like `timeout`, and the line above already gives the reason in words.
4. A failed step with no reason: "Failed at the <step> step.".
5. `refused` without a status: "the storage service refused it (<code>)." / "the storage service refused it."; `server_error` without a status: "the storage service had an error. Try again in a few minutes."
6. No answer: "ShelfSync didn't answer, so the test may not have finished. Test again to check." The stores' "Reload this page to check" doesn't fit: nothing about a storage test is kept to reload.
7. Reused from 13 M2.5a (stores): "Not tested yet.", "Tested <date> at <time> <zone>.", "The test failed.", "ShelfSync refused the test (HTTP <status>)."

**13 edits:** removed m2.5b's "Test row (until m2.7)" line. The M2.3 "Before the Test" line now points to the Storage Test row's `storage_not_set`, which replaced it. The on-screen strings above are appended to the Storage Test row.

**Not verified**
- Playwright plus axe: they run in CI only.
- Windows High Contrast.
- A screen reader's actual announcement: I read the DOM and the attributes only.
- Real AWS: by design.
- `secrets_unavailable` and the "Couldn't be read" keys in the pane: the in-memory store can't fail. Both are covered by unit tests.
- `wrong_region`, `access_denied` and the other reasons in the pane: moto without IAM doesn't produce them. They are covered by the model tests, all 16 reasons plus the null forms.
- A save made while a test is running doesn't forget that test's answer (`forget()` never acts mid-run). That answer then describes the old settings. It's a rare edge, left as is; flagged here for the reviewer.
- The rail is 1 px and short (about 8 px at this type size); in dark it's faint by design (`--color-border-control`).

**Open questions:** none blocking. The guide's new place (above) and the proposed strings are for the lead to accept or change.

## 5. Review

**Reviewer verdict (as relayed by the lead):** APPROVE, 8.5/10. The guide button's new place and all seven proposed strings were accepted. Five findings; a re-check of the fix diff follows.

| # | Severity | Finding | Resolution (designer, `daa5d7d`) |
|---|---|---|---|
| 1 | medium (reproduced in the pane by the reviewer) | A save made while a test runs leaves the old answer on screen: `forget()` returned early while running. Saving bucket B during a timeout run on bucket A showed, 30 s later, A's left-behind key under B's settings, and a "Passed" from the old bucket would read as the new settings passing. | **Fixed** with the reviewer's recommended option. `StorageTestEntry` has a `stale` flag. `forget()` during a run marks it (once); the answer, or a refusal, lands with the mark; a new run clears it, and a later `forget()` drops the stale answer like any finished one. The view keeps the answer and adds a warning-icon note, inside the result's live region so it is announced with the answer: "This test used the settings from before your last save. Test again to check them." (proposed, added to 13's Storage Test row). A refusal never gets the note: it says nothing about the settings. Tests in `lib/storageTest.test.ts`: forget() during a run marks the answer when it lands, for both a result and a refusal; a second forget() changes nothing; a new run clears the mark. More in `storageTestModel.test.ts` and `storageBackupViews.test.ts`. Pane: the reviewer's case, reproduced and fixed (below). |
| 2 | low | `docs/runbooks/README.md:32` | Left to the lead, as asked; not touched. |
| 3 | low | The stores' shared `TestResult` runs its two sentences together in the live region. | **Fixed:** the one-line space in `components/StoreTest.tsx`, with a test in `storesViews.test.ts`. The stores' existing tests pass unchanged. The shared-component refactor stays a follow-up. |
| 4 | low | No test proves a settings save, a key save and a key removal call `forget()`. | **Fixed:** the page now calls two pure hooks in `storageTestModel.ts`, `afterStorageSaved(run, before, after)` and `afterKeysChanged(run)`. Tests with a fake run show: an endpoint, region or bucket change calls `forget()` once; a files-to-keep, template or no-change save doesn't; a key save or removal always does. The page has no DOM in these tests, so a source-level test (read with Vite's `?raw`, as `chunkBoundary.test.ts` does) checks the wiring: `afterKeysChanged(storageTestRun)` right after `saveS3Keys` and after `removeS3Keys`, `afterStorageSaved(storageTestRun, storage, saved)` after `saveStorage`, and no direct `storageTestRun.forget(` left in the page. |
| 5 | low | `StorageView.tsx`: a spinner beside the "can't test" reason while a test still runs. | **Fixed:** `spinning = running && !blocked` drives the line's icon and `is-running`, with a test. The button keeps its own busy spinner, because the test is still running. |

**Commands after the fixes** (in `frontend/`, through `bash tools/heavy.sh --log t2-<name>`):
| Command | Result |
|---|---|
| `npm run lint` | `biome ci`: 130 files, no fixes |
| `npm run typecheck` | pass |
| `npm test` | **32 files, 1058 tests passed** (10 new) |
| `npm run build` | built |
| `npm run schema:check` | `schema.d.ts` is current |

**Pane check of finding 1:** the same harness (real app, in-memory stores, local moto, a silent 127.0.0.1 port; sample values only), restarted, then stopped afterwards.
- Saved the silent endpoint with `sample-t2-bucket-a` and both sample key pairs, then started the Test.
- While it ran, saved the bucket as `sample-t2-bucket-b` ("Storage settings saved.").
- About 30 s later the answer landed and was kept: "Failed at the write step: the storage service took too long to answer.", A's left-behind key, and the steps.
- Under the answer, inside `role="status"`, the stale note: "This test used the settings from before your last save. Test again to check them."
- Console: nothing new.

**Shots:**
- `.logs/shots/t2/10-stale-after-save-light-1024-crop.jpg`
- `.logs/shots/t2/10-stale-after-save-light-1280-crop.jpg`

**Not verified:** a full-width capture of this case. Midway through the pane check the pane stopped scaling its captures: at any emulated size it now returns a 1:1 crop of the top-left of the page, about 640 × 450 CSS px. The two shots are therefore crops. They show the button, the start of the answer line, the time, the start of the stale note and the steps; the right edge is cut. The full texts above were read from the DOM in the same state. The note's box was 479 px wide and 41 px tall at 1024, so it wraps to two lines inside the result column. The lead may want a full-width shot in its own pane.

## 6. Integration notes


## 7. Handover
_(lead, 2026-11-02)_ Brief written. Next: the designer.
