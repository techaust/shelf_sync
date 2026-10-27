# 03: Product requirements (PRD)

| | |
|---|---|
| **Phase** | 2, Project documentation (**approved by the owner 2026-10-25**); corrected after the 2026-10-25 independent review |
| **Date** | 2026-10-25 |
| **Inputs** | [02 plan](02-plan.md) · [01 audit](01-audit.md) · [04-A verification](04-architecture-appendix/A-stack-verification.md) |
| **Used by** | Tests and commits cite these IDs (`feat(match): edition-word penalty [MAT-05]`). The **M** column is the milestone that builds it ([08](08-roadmap.md)); every ID has one |

> **How to read this.** Each requirement has an ID, the rule, how we'll know it's met ("Accept"), and its milestone. "Owner" is the one user. **(setting)** means the default can be changed in Settings. Unfamiliar words are explained in the [glossary](13-content.md#5-glossary). Nothing here writes to a live store before M6.
>
> **Lead proposals** (defaults not in the approved plan; each has a Lead row in [11](11-decisions.md), accepted with the Phase 2 docs on 2026-10-25): CAT-03 near-miss rule · INS-01 ZIP limits · INS-04 and MAT-08 the definitions of "disagreement" and "version family jump" · INS-06 scan behaviour when Defender can't run · SYNC-03 snapshot time and 30-day retention · APL-07 the safe-delete check and one retention pass after the queue drains · APL-08 and APL-14 the target-file check · APL-12 0.15 s spacing and the 10-failure pause · APL-13 the definition of "agree" · SYS-03 the single-use sign-in ticket · SYS-04 start with Windows on · SYS-05 notifications on · SYS-06 the 14-day token-expiry warning · SET-06 port 47615 · ERR-04 the 2 GB free-space threshold · NFR-3 speed targets · LOG-01 log retention 30 days · BAK-01 7 daily database backups.

## 0. Product decisions (decided; never re-asked)
Recorded in [11-decisions.md](11-decisions.md).

| # | Decision |
|---|---|
| D-1 | Product name **ShelfSync**; folder and GitHub repo **`shelf_sync`** (public during development, [11](11-decisions.md)) |
| D-2 | Single user, this PC only, Windows only; no login screen |
| D-3 | ZIPs come in by drag-and-drop in the browser |
| D-4 | Any number of stores, one S3-compatible bucket |
| D-5 | Start clean from the live stores; nothing is imported from OmniSync |
| D-6 | Certain matches auto-apply after a 50-ZIP trust ramp; everything else goes to Review |
| D-7 | Downgrades held; only the main item is updated; bundled items never touch another product; one previous file kept |
| D-8 | A product must be linked on every active store before it can be updated |
| D-9 | "Teach from current files" on first run is on by default (can be skipped) |
| D-10 | One per-user `Setup.exe` (**NSIS**), embedded signed Python, tray icon, in-app updates; no code-signing certificate |
| D-11 | Python + FastAPI + SQLite backend; React + TypeScript (Vite) UI; light and dark following Windows |
| D-12 | A TecHaust product (Patina) with a new ShelfSync logo; store colours as small identifiers only |
| D-13 | $0 tools and services only |
| D-14 | Every ZIP is scanned with Windows Defender before upload; a detection holds it |
| D-15 | Releases are signed with the owner's offline key |

## 1. Catalog and sync (`CAT`, `SYNC`)

| ID | Requirement | Accept | M |
|---|---|---|---|
| CAT-01 | On first run, read every product returned by `downloadable=true`, `status=any` on every store (read-only) and build catalog items. Refuse a store below WooCommerce 5.8 with a clear message | The count per store equals that store's `X-WP-Total` for the same query at test time; no write request is sent (contract test) | M3 |
| CAT-02 | Link twins by identical product URL slug | Every slug present on all active stores is linked (2395 on 2026-10-25's data) | M3 |
| CAT-03 | Suggest near-miss twins: slug edit distance ≤ 2 or a WordPress `-N` suffix, **and** the same normalised title. Never link silently | The 3 pairs in [01-A §2](01-audit-appendix/A-store-data-checks.md) appear in Cleanup as suggestions; none is linked until the owner clicks | M3 |
| CAT-04 | Each item has a canonical slug, initially the shared URL slug and editable. S3 objects are `<slug>-<version>.zip`; an existing object with different content gets `-r2`, `-r3`… and is never overwritten | Renaming the slug changes only future names; a forced same-version upload creates `-r2` | M3 (slug), M5 (naming) |
| CAT-05 | Download slots: one main slot (button name from the store setting, default `Download`) and optional extra slots, each with its WooCommerce download ID per store | The multi-download products show all their slots with the right IDs | M3 |
| CAT-06 | Attachment check: each slot's current file is inspected (range read) and must fit the product's type and name | Jupiter X's `js-composer-theme-7.9.zip` is flagged "file doesn't fit product" | M4 |
| CAT-07 | Cleanup finds: twin missing on a store, duplicate products, file mismatch, stale `latest_version_<slug>` meta, changed outside ShelfSync, deleted or trashed outside ShelfSync | Each issue shows its reason and a suggested fix | M3 (M4 for file mismatch) |
| CAT-08 | Link a near-miss pair, mark "not the same", or dismiss an issue, each recorded in Activity | Each action is reversible from Activity | M3 |
| SYNC-01 | Incremental sync every 15 min (setting) and right before any change: `modified_after` sent as GMT with `dates_are_gmt=true` | An edit made in WP admin shows in Cleanup within 15 minutes | M3 |
| SYNC-02 | A product changed outside ShelfSync offers **accept** (adopt the store's state) or **restore** (put ShelfSync's state back) | Both are recorded in Activity with before/after | M3 (accept), M5 (restore) |
| SYNC-03 | Nightly snapshot at 02:00 **Windows local time** (setting) of every product's slots, downloads and version fields on every store, trashed products included (`include_status=any,trash`; variations too if any appear, V30); if the PC was off or asleep, it runs at the next start or wake; kept 30 days (setting) | "Restore to date" lists the snapshot dates for a product | M3 |
| SYNC-04 | The nightly snapshot also lists every product ID per store, including trash, to find products deleted or trashed outside ShelfSync | A product trashed on the test stack shows in Cleanup after the next snapshot | M3 |
| SYNC-05 | "Sync now" button | Starts an incremental sync and shows its progress | M3 |

## 2. Inspect, scan and match (`INS`, `MAT`)

| ID | Requirement | Accept | M |
|---|---|---|---|
| INS-01 | Walk the ZIP, including nested ZIPs, within the limits in [06 §4](06-security.md): 2 GB total unpacked per upload, 300 MB per nested ZIP, depth 3, 20 000 entries | A theme package with an inner theme ZIP and a `plugins/` folder lists every installable with its depth; an over-limit ZIP **fails** with the limit named (it can't be inspected safely, so there is no Apply anyway) | M4 |
| INS-02 | Find themes (`style.css` with `Theme Name`) and plugins (a `.php` file **at the root of a plugin folder** with `Plugin Name` in its first 8 KB, as WordPress does) | Header fields (name, version, author, URIs, text domain, `Template`) are read; a library's PHP file deeper in a plugin isn't taken as a plugin | M4 |
| INS-03 | Main-item rule: the top-level theme or plugin; items under `plugins/`, `includes/plugins/`, `inc/plugins/` or a TGM folder (editable list) are bundled; a child theme is never chosen over its parent | Business Lounge → the theme is main; WPBakery 9.0.1 is bundled | M4 |
| INS-04 | Version from the main item's header; readme `Stable tag`, `package.json` and filename are cross-checks. **Disagreement** = two numeric versions that differ; `trunk`, a missing tag, or a readme tag older than the header is not one. Disagreement → Review | A header 3.0 with filename 3.1 goes to Review with both shown; header 3.0 with readme 2.9 doesn't | M4 |
| INS-05 | Safe reading ([06 §4](06-security.md)): no path traversal, symlinks ignored, size, ratio, entry and depth limits, nothing executed, temp folders removed after each job and at start-up | The fuzz corpus never writes outside the job's temp folder or crashes the worker | M4 |
| INS-06 | **Windows Defender scan** of every uploaded ZIP before any S3 or store step (`MpCmdRun.exe -Scan -ScanType 3 -File … -DisableRemediation`, output parsed). A detection holds the job with the threat name and can **only be discarded** (owner, 2026-10-25): no approve, no Apply anyway. A saved file that disappears, or stays locked after retries for 5 s (real-time protection removing or holding it), counts as a detection. If the scan can't run (Defender off, another antivirus, timeout 120 s), the job is held as "not scanned" with **Apply anyway** | The EICAR test file inside a ZIP is held as a detection and offers only Discard; with the scan forced to fail, the job is held as "not scanned" with Apply anyway | M4 |
| MAT-01 | Score every catalog slot of the same type against the main item with the signals in [02 §4](02-plan.md) | Each candidate has a score and its reasons with points | M4 |
| MAT-02 | Type mismatch rules a candidate out | A theme ZIP never lists a plugin product | M4 |
| MAT-03 | Confirmed fingerprint or an approved filename → **Certain** | Re-uploading an approved filename is Certain | M4 |
| MAT-04 | Bands Certain / Likely / Unsure / No match, with cut-offs from calibration ([07 §3](07-testing.md)) | The shipped cut-offs equal the calibration report's | M4 |
| MAT-05 | Edition words (editable list: `pro`, `premium`, `plus`, `ultimate`, `extended`, `addon`/`add-on`, `lite`, `free`, `core`, `child`) that differ between ZIP and product → penalty and **never auto**, never ruled out | A ZIP whose main plugin header is "WPForms" scored against the product "WPForms Pro" → Likely, held in Review | M4 |
| MAT-06 | Vendor prefixes (editable list, e.g. `YITH`, `Jet`) and edition words are removed before name matching | Header "YITH WooCommerce Wishlist Premium" matches the product "WooCommerce Wishlist" when `YITH` is a vendor prefix | M4 |
| MAT-07 | "Why?" shows every signal and its points in plain words | Available on every match in Upload, Review and Activity | M4 (logic), M5 (screens) |
| MAT-08 | Guards hold a job even when Certain: downgrade; same version, different MD5; version disagreement; version family jump (first number down, or up by more than 1); not linked on every active store; slot fails the attachment check; changed outside ShelfSync; Defender detection (discard only) or not scanned | Creote 4.3.0 → 3.0.4 is held with "Downgrade"; 7.9 → 4.62 with "Version family jump" | M4 |
| MAT-09 | Learning: approving a Likely/Unsure match saves the fingerprint "confirmed by you · date"; teach-from-current-files saves "learned from current file" | The product page shows each fingerprint and its source | M4 |
| MAT-10 | Unlearning: removing a fingerprint lists the past jobs that matched through it | The list links to each Activity entry | M5 |

## 3. Apply, rollback and safety (`APL`)

| ID | Requirement | Accept | M |
|---|---|---|---|
| APL-01 | A change plan is built before any write: the S3 key, and each store's slot from current to new file | The writes sent equal the plan (contract test) | M5 |
| APL-02 | Upload with a **single** `put_object` carrying `ContentMD5` (S3 rejects a mismatch), never multipart; then `head_object` to confirm the size. The ETag isn't relied on | A corrupted body is rejected; the job retries, then fails without touching the stores | M5 |
| APL-03 | Edit check: re-read the product right before writing; changed since the plan → back to Review | A simulated outside edit on the test stack sends the job to Review | M5 |
| APL-04 | Update the slot inside the **same download ID**; other slots untouched | Read-back shows the same ID with the new file ([04-A V3](04-architecture-appendix/A-stack-verification.md)) | M5 |
| APL-05 | Read-back check after each store write | A slot that doesn't show the new file marks that store failed, naming possible causes (including Approved Download Directories, V5) | M5 |
| APL-06 | Partial: any failed store makes the job **partial** with Retry for that store; nothing is deleted | Retry finishes the job; the dashboard count clears | M5 |
| APL-07 | Keep the previous file (setting: 1) for rollback. **Kept** = each slot's current file plus its most recently replaced file(s), so after a rollback the file rolled back **from** is kept and can be rolled forward again; older files become **delete candidates** only after every store succeeded. **Safe delete**, in one retention pass after the job queue drains: a fresh read of every store (active **and paused**, any product status including trash, **variations of variable products included**) must find no download that points at the object. A download points at it when its file field contains the key in any form (shortcode, direct or presigned URL, URL-encoded); an unparseable one counts as a reference; if one does, the delete is skipped and the reason logged. Objects ShelfSync didn't upload itself are never deleted automatically; they are offered in Cleanup | Activity records each deletion as "Rule: keep 1"; after a rollback and a retention pass, rolling forward again still works; on the test stack, a **paused** store's product keeps its file through two updates on the other store, and the skipped delete shows in Activity with its reason | M5 |
| APL-08 | Rollback: one click points every store back at the previous file, with read-back. The change plan first checks (`head_object`) that the target file still exists in S3; if it doesn't, the job is blocked with the reason and **Set file manually** (APL-15) is offered | Works on the test stack and in the canary ([07 §5](07-testing.md)); with the previous object removed from moto, the rollback is blocked before any store write | M5 |
| APL-09 | Metadata: set `latest_version` per product; remove stale `latest_version_<old-slug>` keys, or empty them if the REST API can't remove them (V4) | Jupiter X's stale key is removed (or emptied, and Cleanup says so) | M5 |
| APL-10 | Crash-safe steps: each recorded before and after; after a restart, unfinished steps are resumed by checking the real state first | Killing the process mid-job and restarting completes it once, with no duplicate write | M5 |
| APL-11 | Brake: pause auto-apply after 3 failures in a row, or more than N auto-applies in 10 min (setting, default 30); "Pause everything" always visible; resuming is a click | Both triggers pause and notify; a 50-file Certain batch pauses at 31 | M5 |
| APL-12 | Per store: 0.15 s between requests (setting); retry 429, 5xx and 520–527 up to 3 times with backoff; pause a store after 10 failures in a row | Contract tests replay a 524 and a 429 | M3 |
| APL-13 | Trust ramp: auto-apply stays off for the first 50 live ZIPs that ShelfSync rates **Certain with no guard**; each goes to Review showing "would apply to X". **Agree** = the owner approves exactly that action. A disagreement resets the count to 0 and flags a cut-off review. ZIPs not rated Certain neither advance nor reset it | The strip shows "Trust ramp 37 / 50"; one disagreement shows "0 / 50" and a notice | M5 (logic), M6 (live) |
| APL-14 | Restore to date: put a product's slots and version fields back to a nightly snapshot, with a change plan and read-back. The plan checks (`head_object`) every file it would point a store at; a missing one blocks the job with the reason and offers Set file manually (APL-15) | Works for changes made outside ShelfSync; a snapshot whose file is gone from S3 is blocked before any store write | M5 |
| APL-15 | Set file manually: pick an S3 object or upload a file for a slot, through the same plan → scan → write → read-back path | Recorded in Activity as "set manually by you" | M5 |

## 4. Screens (`UI`)
Layout: [05 §6](05-design-system.md); wording: [13](13-content.md). Every screen works fully by keyboard, meets WCAG 2.2 AA in light and dark, passes axe ([07 §4](07-testing.md)), and has designed **loading, empty and error states** (§7).

| ID | Screen | Must show / do | Accept | M |
|---|---|---|---|---|
| UI-SHELL | App shell | Side nav (Dashboard, Upload, Review + count, Catalog, Cleanup + count, Activity, Settings); store and S3 health; "Pause everything"; status strip (auto-apply, trust ramp, last sync, next snapshot); theme follows Windows, with a manual override | Counts update live | M1a (shell), M5 (live counts) |
| UI-DSH | Dashboard | Needs-you tiles (Review, Partial, Cleanup), applied today (auto vs you), connections with latency, 14-day chart, drop zone, latest updates | Every tile links to its screen | M5 |
| UI-UPL | Upload | Drop one ZIP or fifty; each row shows inspect → scan → match → S3 → each store, live, with band and product; held rows link to Review | 50 files queue without the page freezing | M5 |
| UI-REV | Review | Queue + detail: inside the ZIP (main, child, bundled), scan result, version vs current, top candidates with reasons, the change plan, actions (approve, pick another, paste URL, discard, apply anyway for held, except a Defender detection, which offers only Discard); bulk "approve all Likely with one candidate"; shortcuts | Every action works by keyboard alone; each decision is recorded | M5 |
| UI-CAT | Catalog | Every product with store links, slots, version, last update, health; search (name, slug, file, product ID); filters; CSV export | Search returns in under 200 ms on 2398 items (§8) | M3 (read-only), M7 (CSV) |
| UI-PRD | Product detail | Canonical slug (edit), store links with "in step" state, slots with current and previous file, fingerprints with source and Remove, history, stale store data; Roll back, Restore to date, Set file manually | Each action shows its change plan first | M3 (read-only), M5 (actions) |
| UI-CLN | Cleanup | Issues grouped by kind, each with reason and suggested fix; bulk "apply suggested fixes"; help | "Link all 3" links the near-miss twins in one go | M3 |
| UI-ACT | Activity | Searchable log of every change to a store or S3: time (local, with zone), what, where, before → after, who or what approved it; filters; CSV export | Every write in the contract tests appears here | M5 (log), M7 (CSV) |
| UI-SET | Settings | Stores, Storage, Rules, Updates, Backup, App (§6) | Secrets are masked and never sent to the browser | M2 (Stores, Storage, Backup), M5 (Rules), M1b (Updates, App) |
| UI-WIZ | First-run wizard | Stores → storage → test → build catalog → Cleanup → teach from current files; resumable | A fresh install reaches the dashboard without a terminal | M3 (to catalog), M4 (teach step) |
| UI-HELP | Built-in help | Short help on Review and Cleanup; the Shop Manager key and IAM policy guides; "What does this word mean?" from the glossary | Reachable from each screen's header | M2 (guides), M5 (help) |
| UI-TRAY | Tray menu | Open ShelfSync, Pause everything / Resume, View logs, Quit; icon shows normal / paused / needs attention | Quit waits for a running upload | M1a |

## 5. System (`SYS`, `LOG`, `BAK`)

| ID | Requirement | Accept | M |
|---|---|---|---|
| SYS-01 | Per-user `Setup.exe` (NSIS, no admin), embedded official Python, desktop icon and Start-menu entry (with an AppUserModelID for notifications); opens the wizard | Installs on a second, clean Windows account with Defender on; Smart App Control state recorded | M1b |
| SYS-02 | Tray icon (pystray) with the UI-TRAY menu | The 3 icon states show correctly on light and dark taskbars | M1a |
| SYS-03 | Single instance: the launcher reads the port from `runtime.json`, checks `GET /api/health`, and if ShelfSync answers it asks for a single-use ticket and opens the browser with it. Sign-in uses a **single-use ticket**, never the install token itself, in the address bar ([06 §2](06-security.md)) | Double-launch never starts a second server and the new tab is signed in; a used or 60-second-old ticket is refused | M1a |
| SYS-04 | Start with Windows (setting, default on) through `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` | Survives a reboot; turning it off removes the value | M1a |
| SYS-05 | Windows toast notifications (windows-toasts) when Review needs the owner or a job goes partial (setting, default on); clicking one opens the right screen | The click opens Review or Activity | M5 |
| SYS-06 | In-app updates: check GitHub Releases, with the owner's read-only token if one is set (optional while the repo is public; owner, 2026-10-27); download through the app; verify the Ed25519 signature and checksums ([06 §6](06-security.md)); install beside the current version; switch; switch back automatically if the health check fails; "Roll back app". With no token set, checks go to the public repo without one; an expired or refused token shows "Can't check for updates: token expired" with a link to the guide; **14 days before** the token expires (read from GitHub's `github-authentication-token-expiration` response header, [04-A V26](04-architecture-appendix/A-stack-verification.md)) a notice says so | Updates itself from a signed test release; refuses an unsigned or tampered one; a test response with an expiry 10 days away shows the notice; checks work with no token set | M1b |
| SYS-07 | Database migrations take a backup first; a failed migration restores it | Proven on a copy of the previous release's database | M1b |
| SYS-08 | Data in `%LOCALAPPDATA%\ShelfSync`. Uninstall removes `%LOCALAPPDATA%\Programs\ShelfSync` completely, including version folders added by updates; data is kept unless "remove my data" is ticked | After uninstall the program folder doesn't exist; reinstall finds the old catalog | M1b |
| LOG-01 | Logs in `%LOCALAPPDATA%\ShelfSync\logs\shelfsync.log`, one JSON line per event (UTC time, level, job ID, step, message), rotated daily, kept 30 days (setting); secrets redacted | The redaction test finds no secret in any log line | M1a |
| BAK-01 | Automatic database backup daily (SQLite online backup) to `%LOCALAPPDATA%\ShelfSync\backups\`, keeping 7, plus one before each migration | Seven files after eight days; a restore from one passes the integrity check | M2 |

## 6. Settings (`SET`)

| ID | Group | What can be changed | M |
|---|---|---|---|
| SET-01 | Stores | Add, remove, pause a store; URL; consumer key and secret; identifier colour and code; request spacing; main button name; Test connection; Shop Manager guide | M2 |
| SET-02 | Storage | S3-compatible endpoint, region, bucket, keys (read/write and a separate read-only key for calibration), Test; download link template (today `[amazon_s3 object="{key}"]`); previous files to keep (1) | M2 |
| SET-03 | Rules | Auto-apply on/off; brake limits; edition words; vendor prefixes; bundled-folder names; downgrade rule (hold); ZIP limits; sync interval; Defender scan on/off (default on; turning it off needs a confirmation) | M5 |
| SET-04 | Updates | Check now; read-only GitHub token (optional); install now or later; roll back the app | M1b |
| SET-05 | Backup | Export/import settings + catalog as one file (secrets only with a passphrase); snapshot retention; database backups kept | M2 |
| SET-06 | App | Port (default **47615**; if it's taken at start, the next free port up to 47624 is used and saved; if all are taken, a notification explains it); theme (system, light, dark); start with Windows; notifications; log retention; "Reset access token" | M1a |

## 7. Errors and empty states (`ERR`)
Every one has a designed screen state with the wording in [13 §3](13-content.md).

| ID | Situation | What the owner sees | M |
|---|---|---|---|
| ERR-01 | A store can't be reached or returns 401/403 at first run or later | The store's health chip turns red with the reason and "Test connection"; jobs for it wait | M2 |
| ERR-02 | A store returns 0 products, or WooCommerce below 5.8 | The wizard stops at that store with the reason | M3 |
| ERR-03 | S3 access denied or bucket missing | Storage test fails with the AWS reason; uploads are held | M2 |
| ERR-04 | Disk space under 2 GB free on the data drive | A banner; new uploads are refused until space is freed | M5 |
| ERR-05 | The PC sleeps or ShelfSync quits mid-job | On wake or restart the job resumes from its last finished step (APL-10) | M5 |
| ERR-06 | Port in use | SET-06 behaviour | M1a |
| ERR-07 | Empty Review, empty Cleanup, empty Activity, no stores yet | A calm empty state that says what will appear here and the next action | M3 (no stores, Cleanup), M5 (Review, Activity) |

## 8. Non-functional (`NFR`)

| ID | Requirement | M |
|---|---|---|
| NFR-1 | **Offline-capable UI:** every font, icon and script bundled; no CDN at run time | M1a |
| NFR-2 | **Accessibility:** WCAG 2.2 AA in both themes; full keyboard use; visible focus; status never by colour alone | M1a onward |
| NFR-3 | **Performance on this PC** (Intel i3-1115G4, 2 cores / 4 threads, 7.8 GB RAM, [09 §1](09-tooling.md)): first view under 1 s; inspecting a 75 MB package under 10 s; catalog search under 200 ms on 2398 items | M5 (tests in [07 §1](07-testing.md)) |
| NFR-4 | **Reliability:** no lost or duplicated store write across crashes (APL-10); every write logged | M5 |
| NFR-5 | **Privacy:** no telemetry; outbound only to the stores, the S3 endpoint and GitHub | M1a |
| NFR-6 | **Cost:** $0 tools and services (D-13), with the AWS request-charge exception stated in [02 §11](02-plan.md) | all |
| NFR-7 | **Maintainability:** plain, well-known parts; one database file; one log folder | all |
| NFR-8 | **Time:** stored in UTC (ISO 8601); shown in Windows local time with the zone name (e.g. "12:22 IST"); schedules in local time | M1a |
