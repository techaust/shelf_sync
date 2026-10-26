# 07: Testing, calibration and going live

| | |
|---|---|
| **Phase** | 2, Project documentation (**approved by the owner 2026-10-25**); corrected after the 2026-10-25 independent review |
| **Date** | 2026-10-25 |
| **Implements** | [02 §5](02-plan.md), [03 PRD](03-prd.md) MAT-04, APL-13, INS-06, NFR-2, NFR-3 |

## 1. Test layers

| Layer | Tool | What it proves | Runs | From |
|---|---|---|---|---|
| Unit | pytest | Header parsing, version order and comparison, family-jump and disagreement rules, normalising, scoring, bands, guards, file naming (`-r2`) | Every commit (CI, Linux) | M1a |
| Property | hypothesis | Version comparison is a total order; normalising is idempotent; a ZIP built from random entries never escapes its temp folder | Every commit | M4 |
| Fuzz corpus | pytest + fixtures | Zip-slip, symlinks, ZIP bombs, odd encodings, broken central directories, ZIP64 ([06 §4](06-security.md)) | Every commit | M4 |
| Scan | pytest + the EICAR test string (written into the job's temp folder by the test itself, never committed as a file) | Detection holds the job and offers only Discard; a ZIP removed before inspection, or still locked after 5 s, is held as a detection (discard only), while a lock that clears within 5 s is inspected normally; "not scanned" when Defender is made unavailable (INS-06) | This PC (Defender needed) | M4 |
| Contract | respx (recorded WooCommerce responses), botocore Stubber | The Defender output parser on recorded `MpCmdRun` outputs (clean, detection, error); the reference parser on every download-link form (shortcode, direct and presigned URL, URL-encoded, unparseable); the exact requests sent: read-only during sync; the change plan equals the writes; the download ID is kept; retries on 429/5xx/52x; `dates_are_gmt` sent | Every commit | M3 |
| Integration | pytest against the **local test stack** | Real writes, read-back, partial, retry, rollback, restore, crash recovery, deletion detection; **a paused store keeps its file through two updates** on the other store, and so does a file a **variation** still offers; a failed or partial store read deletes nothing; an object ShelfSync didn't upload is never deleted automatically; a retention pass never runs between a rollback's check and its write; rollback, then a retention pass, then roll forward still works (APL-07); a rollback or restore whose file was removed from moto is blocked before any store write (APL-08, APL-14) | This PC | M5 (setup M2) |
| Windows checks | pytest, marked `windows`, run with `bash tools/heavy.sh --log windows-checks …` | The real Windows adapters behind the fakes used in CI ([04 §2](04-architecture.md)): Credential Manager read/write/delete, a toast with a click, the `current` junction switch, the HKCU Run value on and off, a Defender scan of EICAR, and, with real-time protection on, whether a freshly written ZIP is removed or locked and for how long (V31; settles the 5 s retry) | This PC, before each milestone's exit and on every release tag | M1a |
| Calibration | pytest + range reads | Matcher accuracy on the bucket's files (§3) | This PC, with the owner's go-ahead | M4, then before each release |
| Performance | pytest-benchmark fixtures | NFR-3: first view < 1 s, a 75 MB package inspected < 10 s, catalog search < 200 ms on 2398 items | This PC | M5 |
| Installer and update | NSIS silent install on the Windows runner, then the update and rollback paths with a signed test release | Install, upgrade, automatic switch-back on a failed health check, "Roll back app", uninstall leaves no program folder | Release tags (CI, Windows) + clean account (M1b) | M1b |
| Migrations | pytest | Every migration runs forward on a copy of the previous release's database; a failing one restores the backup | Every commit | M1b |
| Backup | pytest | Export → import round-trip with and without a passphrase; a wrong passphrase fails cleanly | Every commit | M2 |
| UI unit | Vitest | Formatting, keyboard shortcuts, SSE reducers | Every commit | M1a |
| UI end-to-end | Playwright + @axe-core/playwright | Upload, Review by keyboard, approve, rollback, settings; axe in light and dark on every screen that exists at that milestone | Every commit (CI) | **M1a** (the shell), growing with each milestone |

Coverage (pytest-cov): **≥ 90 %** of lines and branches together in `inspect/`, `match/`, `apply/` and `secure/`, enforced in CI. The Windows adapters live in `platform/` and are measured by the Windows checks, not by CI, so the CI number never counts code it can't run.

## 2. Known bad cases (permanent tests)
Each case in [01 §3](01-audit.md) has a fixture ZIP built from its **header files only** (no vendor code is committed), plus a test of the right outcome: Business Lounge bundle, Elementor vs Elementor Pro, Jupiter X / js-composer-theme, Creote downgrade, GutenKit repeated downgrades, and UDesign (folder `u-design` vs product `udesign`: the theme header decides, the filename alone never makes it Certain, and the previous file is kept).

## 3. Calibration (M4)
1. **Prepare (owner's go-ahead):** list the bucket with the **read-only key** and map every object to a slot, or mark it "unattached" ([01-A §4](01-audit-appendix/A-store-data-checks.md)).
2. **Extract:** range-read each file's central directory and header files (about 1 GiB, an estimate). Save the extracted **headers only** to a local, git-ignored cache, so later runs need no bucket access.
3. **Run cold:** match each file with **no learned fingerprints** and its filename hidden. The expected answer is the product it's attached to.
4. **Ground truth isn't assumed:** files the attachment check flags are set aside, and **the owner reviews that exclusion list** before the run counts. This way the matcher isn't graded against its own judgement.
5. **The bar:** 0 wrong products in Certain, and every known bad case correct. Then as many as possible in Certain.
6. **What it proves:** 0 wrong in about 2,400 trials gives a 95 % upper bound of about **0.13 %** wrong in Certain (the "rule of three"), on today's files. New vendor versions can differ, which is why the trust ramp (§6) follows.
7. **The report** (dataviz rules): results by band, the Certain rate, every disagreement listed, the owner-reviewed exclusions, and separately how many more files reach Certain once learned fingerprints are added. Shared with the owner; its cut-offs ship with the release (MAT-04).
8. **Before each release:** the run repeats on this PC from the local cache. A drop in Certain accuracy blocks the release in the `release.md` checklist. It runs on this PC, not in CI, because CI has no bucket access by design.

## 4. Accessibility
- axe-core (WCAG 2.2 A and AA rules) on every screen in light and dark, in CI, from M1a; zero violations allowed.
- Keyboard paths in Playwright: Review end to end without a mouse; Settings forms; dialogs trap and return focus.
- The tokens test checks every colour pair, including the store dots on every surface ([05 §2.3](05-design-system.md)), from M1a.
- A manual NVDA pass (free screen reader) on Review and Upload before M7.

## 5. The local test stack and the live canary
- **Test stack ($0):** a **LocalWP** site with WooCommerce and the owner's **Amazon S3 Storage** extension (they already have it for the stores), set to a "User defined" endpoint pointing at **moto server** (04-A V6–V8). One script sets it up with sample products shaped like real ones (no customer data). Every write path is proven here first. If the extension can't use moto, the tests prove the stored shortcode and slot, and real downloads are proven in the canary.
- **Live canary (M6, each step with the owner's yes):**
  1. the owner picks one low-traffic product
  2. apply on both stores, then read back both
  3. **test download:** as admin, create a $0 manual order for that product to the owner's own customer account, then open the download link from the order. **The order is deleted afterwards**, with the owner's yes
  4. roll back and check both stores and the download again
  5. nothing else runs live until this passes

## 6. Trust ramp (M6)
- Auto-apply stays **off** until **50 live ZIPs in a row**, rated Certain with no guard, match the owner's decision. Each shows in Review as "ShelfSync would: apply to X".
- **Agree** = the owner approves exactly that action. A disagreement resets the count to 0, and the cut-offs are reviewed (with a new calibration run from the cache) before counting again. ZIPs not rated Certain neither count nor reset (APL-13).
- The counter (`37 / 50`) is on the status strip.

## 7. The clean-account test (M1b)
Windows Sandbox isn't available on Windows 11 Home (04-A V24). The owner creates a **second local Windows account** once (runbook `clean-account.md`, click by click). The installer is tested there with Defender on, and the Smart App Control state is recorded.

## 8. Definition of done for any task
- Tests for the new logic, passing locally and in CI; coverage rule met; the Windows checks pass on this PC when the task touches `platform/`.
- `ruff`, `mypy`, Biome and `tsc` clean.
- For screens: axe clean in both themes, and screenshots checked against [05](05-design-system.md).
- The `reviewer` agent's APPROVE ([12 §4](12-models-and-usage.md)), with `security-review` for Tier A.
- A plain report to the owner: what ran, what passed, and what wasn't verified.
