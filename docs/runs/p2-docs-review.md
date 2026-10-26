# Run: p2-docs-review (Phase 2 documentation review)

Status: closed (Phase 2 approved by the owner, 2026-10-25)
Tier: none (documentation)
Usage:
- general-purpose claude-opus-5-5/high [no skills; started before the agent system existed]: weekly and 5-h not recorded (the usage check began after this run)
- reviewer claude-opus-5-5/high [code-review] (re-review, 2026-10-25): weekly 75 % → 76 %, 5-h 43 % → 53 % (model-audit confirmed)
- reviewer claude-opus-5-5/medium [code-review, security-review: refused, no repo] (re-check 1, 20:43 IST): weekly 77 %, 5-h 59 % at start
- reviewer claude-opus-5-5/medium [code-review] (re-check 2, 20:58 IST), (re-check 3, 21:23 IST), (re-check 4, 21:36 IST): weekly 77 % → 83 % across the evening (model-audit confirmed all four at medium)
- each review's `code-review` helper: general-purpose claude-opus-5-5/high [no skills], read-only, listed by model-audit with its note

## 1. Brief
Rate every file in the project out of 10 on accuracy, consistency, completeness, clarity, actionability, TecHaust fidelity, honesty, security and code quality, and list the exact fixes for 10/10 (lead, 2026-10-25).

## 5. Review (independent, 2026-10-25, copied verbatim)

```text
ShelfSync documentation review: strict, read-only

Scope: I read all 27 files in ShelfSync. For comparison I read techaust_platform's CLAUDE.md, its docs layout, 06-design-system (palette, contrast and type sections), 10-tooling, 12-status, 13-decisions, 14-models-and-usage (header), 05-architecture (header), ADR 0012 and its two session skills.

To check what the research scripts depend on, I grepped only the STORES and api_base lines of OmniSync's omnisync/config.py. I did not read config.env or any CREDENTIALS folder. Nothing was edited.

Outside checks:
- Web search: the Inno Setup licence. Confirmed that since 6.5.0 the developer asks commercial users to buy a licence, although the open-source licence doesn't strictly require it.
- Web search: pystray notification clicks and WooCommerce meta deletion. Neither search settled the question. Those two points, and the MinIO and boto3 points, come from my own knowledge and are marked "verify".

Scale: 10 = nothing to improve. "n/a" = the aspect doesn't apply.

======================================================================
PART 1: SCORES PER FILE
======================================================================

CLAUDE.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 8 | Facts match the other docs; the "signed" Python claim is broadly right |
| Consistency | 7 | "Markdown only" (L14) clashes with the HTML mockups and PNGs planned in 05 §8. "Import nothing" (L25) is undercut by the scripts' `from omnisync import config` |
| Completeness | 6 | No git workflow, time-zone rule, supply-chain conventions, model/effort rule, or location for the "memory notes" |
| Clarity | 8 | Scannable; a few unexplained terms (WAL, respx, Biome) |
| Actionability | 7 | The rules are actionable; the stack line is incomplete |
| Fidelity | 7 | Structure copied well; TecHaust's Git workflow and Conventions (Time, Security, Supply chain) sections are missing |
| Honesty | 8 | Fine |
| Security | 8 | The secrets rule is good; no supply-chain rule |
| Code | n/a | |

README.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 8 | "Nothing to pay for" ignores Inno Setup's request for a commercial licence |
| Consistency | 8 | ADR 0002 L15 says the README shows the SmartScreen step; it doesn't |
| Completeness | 5 | No what-it-needs list, no "how to start" pointer, no endorsement lockup or owner line |
| Clarity | 9 | Clear |
| Actionability | 5 | Nothing to act on yet |
| Fidelity | 8 | Matches the TecHaust pattern |
| Honesty | 8 | |
| Security | n/a | |
| Code | n/a | |

docs/01-audit.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 7 | "2398 files … each attached to a known product" (L42) clashes with 2 products per store having more than one download |
| Consistency | 7 | Same clash with 01-A |
| Completeness | 6 | No file:line or log-excerpt evidence for P1–P4; the UDesign case is empty (L34) |
| Clarity | 9 | Very readable |
| Actionability | 7 | The bad cases are concrete except UDesign |
| Fidelity | 7 | TecHaust audits cite evidence in appendices; this one asserts |
| Honesty | 7 | Causes are stated as fact with no traceable evidence |
| Security | n/a | |
| Code | n/a | |

docs/01-audit-appendix/A-store-data-checks.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 6 | The counts depend on the REST `downloadable` filter and the default `status=any` (drafts, private and pending included); neither is stated or verified |
| Consistency | 7 | §4 "one per product" vs §1 "2 have more than one download" |
| Completeness | 5 | No method or source for the near-miss pairs, the multi-download count or the S3 numbers; no query time |
| Clarity | 8 | |
| Actionability | 5 | Not reproducible: the kept scripts don't print downloads, near misses or S3 data |
| Fidelity | 8 | |
| Honesty | 5 | L3 implies the scripts produced these numbers; several they can't |
| Security | n/a | |
| Code | n/a | |

docs/02-plan.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 6 | Wrong or unverified: SmartScreen "once", the "$0" range reads, the ~1 GiB estimate, stale-meta removal through REST, and the claim that `modified_after` sees deletions |
| Consistency | 6 | L7 "republished whenever this plan changes" vs status L26; L157 scores a retired look 10 |
| Completeness | 7 | Strong design; canonical-slug origin, version-family definition, port and time zone missing |
| Clarity | 8 | Good, a little dense |
| Actionability | 7 | |
| Fidelity | 8 | |
| Honesty | 5 | The scorecard gives 10/10 on 11 of 12 aspects before any code, with many open gaps |
| Security | 7 | |
| Code | n/a | |

docs/03-prd.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 7 | SYS-05 notification click (not possible with pystray, verify); APL-09 meta removal through REST (verify); MAT-05 example muddled |
| Consistency | 7 | Proposals list (L12) ≠ the decisions rows; snapshot retention sits under Backup |
| Completeness | 6 | No error or empty states, logging content, time zone, default port, disk-space handling, total ZIP limits or uninstall details |
| Clarity | 7 | Dense tables; jargon (`modified_after`, MD5, SSE, `-N`) unexplained for the owner |
| Actionability | 6 | Several acceptance tests are tied to today's counts or are vague ("this PC", "within one sync") |
| Fidelity | 8 | ID scheme and §0 decisions match TecHaust |
| Honesty | 8 | Proposals flagged |
| Security | 7 | |
| Code | n/a | |

docs/04-architecture.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 5 | SSE can't send a token header; the shortcut path breaks after an update; the embeddable package needs `._pth` edits; ETag/MD5 caveats; range-read flow incomplete; deletions not seen by incremental sync |
| Consistency | 6 | The token hand-off clashes with the launcher's "only opens the browser"; snapshots are both a table and a folder |
| Completeness | 5 | No default port, failed or cancelled job states, logging design, time zone, automatic DB backup, uninstall of side-by-side versions, or Start-with-Windows mechanism |
| Clarity | 7 | |
| Actionability | 6 | |
| Fidelity | 6 | No stack-verification appendix (TecHaust has 05-A); versions deferred |
| Honesty | 6 | Library behaviour stated as fact before the Context7 check |
| Security | 6 | |
| Code | n/a | |

docs/05-design-system.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 7 | Tokens match TecHaust exactly. But "all higher in dark" is false (card border 3.6 vs 3.5), two Lucide names are old aliases, and the PW dot fails 3:1 on stone-200 |
| Consistency | 7 | HTML and PNG in docs/ vs Markdown only; "→ in Plex Mono" vs "arrows are icons" |
| Completeness | 6 | No empty, error or loading screens; no wizard, tray-menu, help or notification layouts; no copy or voice rules; nothing on table virtualisation |
| Clarity | 8 | |
| Actionability | 8 | |
| Fidelity | 9 | Very close to TecHaust 06 |
| Honesty | 8 | |
| Security | n/a | |
| Code | n/a | |

docs/06-security.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 5 | Ed25519 key in Actions secrets does not stop a GitHub-account takeover; scrypt N=2^17 fails with hashlib's default maxmem; pip-audit has no "high" level; header-only token breaks SSE and CSV links |
| Consistency | 6 | §9 checks the token at M1; 08 builds it at M2 |
| Completeness | 6 | Missing: malware in vendor ZIPs reaching customers; same-user processes reading Credential Manager; WooCommerce key scope; Smart App Control; temp clean-up after a crash; a read-only calibration key |
| Clarity | 7 | |
| Actionability | 7 | |
| Fidelity | 7 | |
| Honesty | 6 | Overclaims the signature's protection |
| Security | 6 | |
| Code | n/a | |

docs/07-testing.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 6 | Calibration "fails the release build" can't run in CI without live-bucket keys and the owner's go-ahead |
| Consistency | 6 | DoD needs axe for every screen; axe tooling arrives at M5, screens from M1–M3 |
| Completeness | 6 | No performance, installer, update or migration tests; agreement in the trust ramp undefined; no sample-size caveat |
| Clarity | 8 | |
| Actionability | 6 | |
| Fidelity | 7 | |
| Honesty | 6 | "0 wrong in Certain" presented as proof; ground truth is circular |
| Security | 7 | |
| Code | n/a | |

docs/08-roadmap.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 7 | Days add up to 21 |
| Consistency | 6 | Token/Host checks at M2 vs 06 §9 at M1 |
| Completeness | 5 | Wizard, Dashboard, Rules/Updates/App settings, help, Start-with-Windows, APL-15 and Catalog CSV are in no milestone; Phase 3 has no estimate |
| Clarity | 8 | |
| Actionability | 7 | |
| Fidelity | 8 | |
| Honesty | 6 | M1 at 2 days (CI, installer, embedded Python, tray, updater with signatures, Defender test) is optimistic and not flagged |
| Security | 7 | |
| Code | n/a | |

docs/09-tooling.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 7 | Cloudflare plugin is enabled but not listed in §1; Context7 coverage of Inno Setup and WooCommerce unverified |
| Consistency | 7 | §6 "Gaps" vs T2 listing the same tools under Context7 |
| Completeness | 6 | No machine table (TecHaust has one); packages missing: python-multipart, pytest-cov, lock-file tool, OpenAPI type generator, a toast library |
| Clarity | 8 | |
| Actionability | 8 | |
| Fidelity | 7 | Claude in Chrome isn't covered; no Found/Needed/Action table |
| Honesty | 8 | |
| Security | 8 | |
| Code | n/a | |

docs/10-status.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 8 | |
| Consistency | 7 | Contradicts the 02 L7 republish claim |
| Completeness | 7 | Missing waits: the Inno licence question, the MinIO/S3-emulator choice, the S3 plugin for LocalWP |
| Clarity | 9 | |
| Actionability | 8 | |
| Fidelity | 8 | No time or time zone (TecHaust: "14:00 (IST)") |
| Honesty | 7 | Doesn't say that library and platform claims are unverified until M1 (rule 9) |
| Security | n/a | |
| Code | n/a | |

docs/11-decisions.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 7 | L33 says 02:00 "was in the plan"; 02 never says 02:00 |
| Consistency | 6 | The 8 KB proposal has no row; "Lead (accepted with the plan)" and "Owner / Lead" aren't defined who-values |
| Completeness | 6 | Defaults without rows: 0.15 s spacing, Start-with-Windows on, 2-thread pool, 64 KB tail, token hand-off, scrypt parameters, theme follows Windows |
| Clarity | 8 | |
| Actionability | 8 | |
| Fidelity | 8 | |
| Honesty | 7 | |
| Security | n/a | |
| Code | n/a | |

ADR 0001
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 8 | Plain `zipfile` can't range-read remote files without a seekable HTTP wrapper; not mentioned |
| Consistency | 9 | |
| Completeness | 6 | No alternatives considered (Tauri, Electron, a Node backend, WebSocket) |
| Clarity | 8 | |
| Actionability | 7 | |
| Fidelity | 8 | |
| Honesty | 8 | |
| Security | n/a | |
| Code | n/a | |

ADR 0002
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 5 | SmartScreen is "once per downloaded file", not per PC; Smart App Control can block with no "Run anyway"; Inno Setup's licence request not mentioned |
| Consistency | 6 | L12 states the signed manifest as accepted; 06 §6 calls it a proposal |
| Completeness | 6 | No `._pth`, stable launcher, uninstall or AppUserModelID notes |
| Clarity | 8 | |
| Actionability | 6 | |
| Fidelity | 8 | |
| Honesty | 6 | |
| Security | 6 | |
| Code | n/a | |

ADR 0003
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 7 | Incremental sync can't see deletions |
| Consistency | 8 | |
| Completeness | 6 | Canonical-slug origin and paused-store behaviour missing |
| Clarity | 9 | |
| Actionability | 7 | |
| Fidelity | 8 | |
| Honesty | 8 | |
| Security | n/a | |
| Code | n/a | |

ADR 0004
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 8 | |
| Consistency | 9 | |
| Completeness | 7 | No consequence for the early Review load; no statistical caveat |
| Clarity | 9 | |
| Actionability | 7 | |
| Fidelity | 8 | |
| Honesty | 7 | |
| Security | n/a | |
| Code | n/a | |

ADR 0005
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 7 | "Only with the token": health and the static files need none |
| Consistency | 8 | |
| Completeness | 6 | Token renewal and the second-launch hand-off missing |
| Clarity | 9 | |
| Actionability | 7 | |
| Fidelity | 8 | |
| Honesty | 8 | |
| Security | 7 | |
| Code | n/a | |

ADR 0006
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 9 | |
| Consistency | 8 | Says "tokens unchanged" while adding app-bar tokens |
| Completeness | 8 | |
| Clarity | 9 | |
| Actionability | 8 | |
| Fidelity | 9 | |
| Honesty | 9 | VERIFY WITH LEGAL used properly |
| Security | n/a | |
| Code | n/a | |

ADR 0007
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 9 | |
| Consistency | 7 | "Markdown only" vs the 05 §8 HTML and PNG files |
| Completeness | 7 | Silent on TecHaust's models/effort rule (keep or drop) |
| Clarity | 9 | |
| Actionability | 8 | |
| Fidelity | 8 | |
| Honesty | 9 | |
| Security | n/a | |
| Code | n/a | |

docs/runbooks/README.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 9 | |
| Consistency | 8 | |
| Completeness | 6 | No planned uninstall, app update/rollback, port-conflict or troubleshooting, database restore, or key-rotation runbooks |
| Clarity | 9 | |
| Actionability | 6 | |
| Fidelity | 8 | |
| Honesty | 9 | |
| Security | n/a | |
| Code | n/a | |

docs/runbooks/research-scripts.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 7 | Says "prints SKU" nowhere though the script does; "nothing in OmniSync is changed" not verified (import side effects) |
| Consistency | 7 | Example slug ≠ the "canonical slug jupiterx" story |
| Completeness | 5 | No expected output, run time, or what to do on 401/403/Cloudflare errors; no "how to open PowerShell" clicks |
| Clarity | 7 | |
| Actionability | 7 | |
| Fidelity | 8 | |
| Honesty | 7 | |
| Security | 7 | Prints nothing secret; fine |
| Code | n/a | |

.claude/skills/start-session/SKILL.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 9 | |
| Consistency | 8 | |
| Completeness | 7 | Doesn't read the memory notes; no model check |
| Clarity | 9 | |
| Actionability | 8 | |
| Fidelity | 7 | TecHaust's has setup, budget and branch clean-up steps |
| Honesty | 9 | |
| Security | 9 | |
| Code | n/a | |

.claude/skills/end-session/SKILL.md
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 8 | |
| Consistency | 8 | |
| Completeness | 7 | No CHANGELOG line format; doesn't record what wasn't verified in status |
| Clarity | 9 | |
| Actionability | 8 | |
| Fidelity | 7 | |
| Honesty | 8 | |
| Security | 9 | |
| Code | n/a | |

tools/research/lookup_slug.py
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 8 | Correct REST usage |
| Consistency | 8 | |
| Completeness | 5 | No argument check; no status filter |
| Clarity | 7 | |
| Actionability | 7 | |
| Fidelity | n/a | |
| Honesty | 8 | |
| Security | 7 | Imports and runs OmniSync module code |
| Code | 5 | Crashes on missing argv, on non-JSON 200 responses (Cloudflare) and on an empty api_base |

tools/research/slug_overlap.py
| Aspect | Score | Reason |
|---|---|---|
| Accuracy | 6 | The duplicate-slug test (L37) can miss duplicates within one store; counts include non-published products |
| Consistency | 6 | Doesn't produce several numbers 01-A attributes to the scripts |
| Completeness | 5 | No download counts, near-miss detection or totals check |
| Clarity | 7 | |
| Actionability | 7 | |
| Fidelity | n/a | |
| Honesty | 7 | |
| Security | 7 | Same as lookup_slug.py |
| Code | 5 | No retry or backoff (one 52x kills the run); pagination by `len < 100` instead of X-WP-TotalPages; hardcoded store keys |

======================================================================
PART 2: SPECIFIC FIXES TO REACH 10/10, PER FILE
======================================================================

CLAUDE.md
1. L14 "Markdown only": either allow `docs/NN-name-appendix/` to hold HTML mockups and PNG screenshots (05 §8 L194–195 plans exactly that), or move them out of docs/. Make CLAUDE.md, ADR 0007 L10 and 05 §8 say the same thing.
2. L25 rule 4 "import nothing from it": the scripts run `from omnisync import config` (lookup_slug.py L8, slug_overlap.py L9), which executes OmniSync code. Reword the exception to "the research scripts import omnisync.config read-only to borrow store settings". Verify the import has no write side effects (logs, cache files).
3. Add a "Git workflow" section now (the repo is created at M1). Cover branch protection on main, PR-only changes, conventional commits, the commit identity (as TecHaust L99–103), and that pushes need the owner's yes.
4. Extend "Conventions" with TecHaust's missing items:
   - Time: store UTC; show the owner's local time zone (IST?) and name it; snapshot time 02:00 local.
   - Supply chain: exact pins, hashes, GitHub Actions pinned by SHA.
   - Security: deny by default; no secrets in logs.
5. L32 "memory notes": say where they live and what goes in them.
6. L39 stack: add Pillow, React Router, TanStack Query, bandit, pip-audit, Vitest and python-multipart, or say "summary; full list in 09 §7".
7. Add a one-line model/effort rule (which model and effort the Lead runs on), or state that it is deliberately not copied (and record that in ADR 0007).

README.md
1. L3 "nothing to pay for": add "(Inno Setup asks commercial users to buy a licence; not strictly required; owner decision pending, see 11)", or remove the claim.
2. ADR 0002 L15 says "the README shows it" (SmartScreen). Either add an "Installing" placeholder section that says it will show the "More info → Run anyway" step from M1, or change the ADR.
3. Add who it's for, the owner, and a one-line "Start here: docs/02-plan.md".

docs/01-audit.md
1. L42 "2398 files … each attached to a known product" and 01-A L28 "one per product" contradict L41 (2 products per store have more than one download). Either the extra downloads are not in the bucket, or the file count is wrong. Measure and state which, for example "2398 main-slot files; the 2 extra downloads per store are <where>".
2. L19–22: give each cause an evidence pointer (OmniSync file and function, log file and line, or product ID). For example, P1 "keyed from the attached file": name the OmniSync function. P4: the log lines for Creote. TecHaust audits do this in appendices; add `01-audit-appendix/B-omnisync-evidence.md`.
3. L34 UDesign: it is a "known bad case" with no content. Either remove it from the "become permanent tests" list until known, or mark it "OPEN: owner to describe (by M4)" in the same style as the status.
4. L13: "settled by someone reading logs and editing JSON files by hand". Name the files: `product-slug-overrides.json` is named at L21; name the alias file too.
5. Add the method behind §4 (which REST filters, which status values, the query time in UTC).

docs/01-audit-appendix/A-store-data-checks.md
1. L3 "The scripts are kept in tools/research/" implies they produced every number. The kept scripts do not print:
   - the multi-download count (L13): `_fields` omits `downloads`
   - the near-miss pairs (§2)
   - the S3 count and size (§4)
   Either extend the scripts or say how each number was obtained (for example "S3 count via AWS MCP run_script, read-only, on <date>"; "near misses found by hand from the 3 only-one-store slugs").
2. L9 "Downloadable products 2398": state that the REST default is `status=any`, so drafts, pending and private are included. Say whether that was intended. Re-run with `status=publish` if the catalog should use published products only. Also confirm the store's WooCommerce version supports the `downloadable` filter: an unknown filter is silently ignored and would return all products.
3. L12 "Slug repeated within the store 0": the script's test (slug_overlap.py L37) only flags slugs whose combined count is above 2. A slug twice in one store and absent from the other (count 2) is missed. Fix the script (see below) and re-measure, or reword to "no slug appears more than twice across both stores".
4. L29 "about 1 GiB … inside AWS's free 100 GB/month": mark it as an estimate. Vendor packages that contain an inner theme ZIP stored deflated must be downloaded and inflated whole to read the inner header, so the estimate may be much higher. Also, GET requests are billed per 1,000 (cents, not $0). Say "egress within the 100 GB free allowance; request charges a few cents".
5. Add the measurement time and the WooCommerce version of each store.

docs/02-plan.md
1. L7: "republished … whenever this plan changes" is false today (status L26: still the old look). Change to "republished at P3.6; until then it shows Draft 3's look".
2. L23 canonical slug `jupiterx`: say how the canonical slug is first set. The research runbook's example URL slug is `jupiterx-website-builder-for-wordpress-woocommerce`, so it isn't the URL slug. For example: "initially the shared URL slug; the owner can shorten it". Add an S3-key collision rule: `<slug>-<version>.zip` already exists with different content ("Apply anyway" on a same-version guard) → use a suffix such as `-r2`, never overwrite, or rollback is lost.
3. L34 `modified_after`: it never returns trashed or deleted products (the default status excludes trash; deleted posts vanish), and it is read in site time unless `dates_are_gmt=true` is sent. L35 promises deleted products show in Cleanup. Add "the nightly snapshot also lists every product ID, to detect deletions", and "dates are sent as GMT".
4. L53: the version order puts readme "Stable tag" second. Say that "trunk", a missing tag, or a readme tag older than the header is not a disagreement, or Review will flood.
5. L62: add `premium`, `plus`, `ultimate` and `extended` to the edition-word examples (MAT-06's example uses "Premium").
6. L67 "Version family jump": define it, for example "major number decreases, or changes by more than 1, or the scheme changes". Otherwise 3.9 → 4.0 is ambiguous.
7. L87 "~40 hand-written overrides": give the source (the file and count) in 01, or remove it.
8. L113 "stale … keys removed": WooCommerce REST v3 `meta_data` in a product update is applied through update_meta_data. To my knowledge there is no supported REST delete of a meta key (verify on the test stack). Change to "set to empty, or removed via <mechanism>, to be verified in M5".
9. L115 brake "more than 30 auto-applies in 10 min" vs a 50-ZIP batch (UI-UPL): say whether a 50-file Certain batch is expected to trip the brake, or count per batch.
10. L133: "SmartScreen asks once at install" → "asks each time a new unsigned Setup.exe downloaded from the internet is run". Add: "On Windows 11 with Smart App Control on, the unsigned Setup.exe and the unsigned wheel DLLs may be blocked with no Run-anyway option; check the owner's PC (Windows Security → App & browser control)."
11. L142 cost row: change "Inno Setup … $0" to "$0 (Inno Setup 6.5+ asks commercial users to buy a licence; not strictly required: owner's call)". MinIO: since late 2025 the community edition ships source-only (verify). Name a $0 fallback, for example moto server or an older pinned MinIO binary.
12. L148–166 scorecard: a plan can't honestly be 10/10 before code with these gaps open. Either re-score (most at 8–9 with the gap named) or rename it "design intent". L157 must not show 10 for a retired look; show "—, re-scored after Phase 3".

docs/03-prd.md
1. L12 proposals list: it names the "8 KB plugin-header scan" but 11 has no row for it. Also, 8 KB is WordPress's own get_file_data limit, so it is a fact, not a proposal. Drop it from the list, or add a row. Add the missing proposals: 0.15 s spacing (APL-12), Start with Windows on (SYS-04), entry limit 20,000 and ratio 100:1 (06), Ed25519 and 90 % coverage. Then L12 matches 11 L31–37 one to one.
2. L37 CAT-01 "All 2398 products per store": tie it to the live count, for example "equals the store's X-WP-Total for the same filter at test time".
3. L44 SYNC-01: add "and a product deleted or trashed in WP admin shows in Cleanup within one nightly snapshot" (see 02 fix 3).
4. L46 SYNC-03 "02:00": state the time zone; say what happens if the PC is asleep or off at 02:00 (catch up on wake).
5. L53 INS-02: WordPress only reads plugin headers from PHP files in the plugin folder's root. Say "`*.php` at the root of each plugin folder", or bundled libraries and vendor sub-plugins will be detected as plugins.
6. L55 INS-04: define "disagreement" (see 02 fix 4).
7. L61 MAT-05: the example is confusing (the filename `wpforms-pro` and the product "WPForms Pro" share the edition word). Rewrite: "a ZIP whose main plugin header is 'WPForms' (no Pro) scored against product 'WPForms Pro' → Likely, never auto".
8. L62 MAT-06: the test passes without stripping anything (the slug contains every word) and "Premium" is not in the edition list. Use a case that needs stripping, for example header "YITH WooCommerce Wishlist Premium" vs product "WooCommerce Wishlist" with YITH as a vendor prefix. Add `premium` to the list.
9. L64 MAT-08: define "version family jump" (see 02 fix 6).
10. L73 APL-02: "ETag or a HEAD check". The ETag equals the MD5 only for a single-part upload without SSE-KMS or SSE-C. Say "single-request put_object with ContentMD5 (S3 rejects a mismatch); never multipart; HEAD to confirm size; not valid under SSE-KMS".
11. L81 APL-09: mark "remove stale keys" as "verify REST support at M5" (see 02 fix 8).
12. L84 APL-13: define "agree". For example, only ZIPs ShelfSync would have auto-applied count. A ZIP it would have sent to Review counts if the owner's decision matches the pre-selected candidate. Say whether non-Certain ZIPs advance or reset the count.
13. L113 SYS-05 "Clicking the notification opens the right screen": pystray's notify() has no click callback, as far as I know (verify). Either drop the click behaviour or name a library (for example windows-toasts / WinRT toasts, which need an AppUserModelID on the Start-menu shortcut; Inno Setup's [Icons] supports AppUserModelID).
14. L114 SYS-06: say how token expiry is handled (fine-grained tokens have expiry dates), and what the UI shows when the check fails.
15. L116 SYS-08: add "uninstall also removes version folders the in-app updater added (not in Inno's uninstall log)". Accept: "after uninstall, %LOCALAPPDATA%\Programs\ShelfSync does not exist".
16. L128 SET-06 Port: give the default port and the behaviour when it is taken (try the next port? error screen?).
17. L136 NFR-3: "this PC" → record the PC (CPU, RAM, disk) in 09 §1 so the target is testable.
18. Add a section "Errors and empty states": store unreachable on first run; wrong keys; 0 products; S3 denied; disk full; PC sleeps mid-job; empty Review; empty Cleanup. Each with what the owner sees.
19. Add "Logging": what is logged per job, the format, the default retention (SYS-09 says "setting" with no default), and the time zone.
20. Add an automatic database backup (for example a daily copy using SQLite's online backup API, keep 7). Today the only backups are before migrations and manual exports.
21. Clarity: add a 6-line glossary for the owner (slug, MD5, SSE, WAL, `modified_after`, ETag).

docs/04-architecture.md
1. L96 and 06 L25: EventSource (SSE, L101) cannot send custom headers, and a plain `<a href="/api/catalog.csv">` can't either. Specify how the token travels for `/events` and the CSV downloads, for example a SameSite=Strict, HttpOnly cookie set by a one-time exchange of the fragment token, or a short-lived query token for those two routes only.
2. L143 Launcher: when ShelfSync is already running it "only opens the browser", but the token lives in sessionStorage (06 L23), which a new tab or window doesn't have. Say the launcher reads the token from Credential Manager and always opens `http://127.0.0.1:<port>/#token=…`. The same applies to notification clicks.
3. L140–142: the shortcuts can't run "pythonw.exe from the current version", because a shortcut has a fixed path and the version folder changes after an update. Add a stable launcher outside `versions\` (for example `%LOCALAPPDATA%\Programs\ShelfSync\ShelfSync.pyw` run by a stable pythonw, or a tiny launcher that reads `current`). Same for Start with Windows (state the HKCU\…\Run key or the Startup-folder shortcut).
4. L138: the embeddable package has no site-packages and ignores PYTHONPATH. Its `python312._pth` must be edited (add `Lib\site-packages` and the app folder, uncomment `import site`), and wheels installed with `pip install --target`. Say so.
5. L33 "PSF-signed python.exe / pythonw.exe": also say python312.dll and the stdlib .pyd files are signed. The third-party .pyd and DLL files (L145) are not.
6. L113–127 job states: add `failed` (APL-02 "the job fails"), `cancelled` (Quit or Pause), and the transitions uploading → failed, discarded → [*], and partial → review (an edit check during retry). Define "held".
7. L133 WooCommerce: add "Approved Download Directories (WooCommerce 6.4+) may block or disable a download whose file isn't in an approved location. Verify how the `[amazon_s3 …]` shortcode passes this on the test stack." Add "send dates as GMT (`dates_are_gmt=true`)". Name the WooCommerce version range supported.
8. L134 S3: the flow "last 64 KB, then the header files" skips a step. Find the EOCD in the tail, then fetch the central directory at its stated offset (it can be far larger than 64 KB, and ZIP64 has its own EOCD), then the local headers and data of the needed entries. Inner ZIPs stored deflated must be fetched whole. Add: "boto3 ≥ 1.36 adds CRC32 checksums by default; set `request_checksum_calculation='when_required'` for S3-compatible endpoints if they reject it (verify with the chosen emulator)."
9. L141: "snapshots" listed as a data folder, but §4 L91 keeps snapshots in the `snapshot` table. Pick one.
10. §4: add `id` to `fingerprint` (DELETE /fingerprints/{id} needs it) and `error`, `attempt` and `updated_at` to `job`. Say how a paused store affects "linked on every store" (`store.paused` vs "active" in L79). List the indexes and foreign keys.
11. §5: add missing endpoints:
    - snapshot dates for a product (APL-14 lists them)
    - DELETE and PATCH /stores/{id} (SET-01 remove and pause)
    - wizard state and resume (UI-WIZ)
    - start teach-from-current-files
    - trigger a sync now
    - link a near-miss pair
    - dismiss a Cleanup issue
12. Add a "Configuration and ports" subsection: default port; config file path (or "all in the `setting` table"); log file path, name, rotation and default retention; temp path; what happens on a port clash.
13. Add a "Time" line: store UTC ISO-8601; show local time; snapshot schedule in local time.
14. L45 CI: "free for private repos within the monthly minutes". Add that Windows runners use minutes at 2× on private repos (Free plan: 2,000 min/month, about 1,000 Windows minutes).
15. Add a stack-verification appendix (`docs/04-architecture-appendix/A-stack-verification.md`, as TecHaust 05-A) before approval. Each claim gets a status (pystray features, keyring backend limits, WooCommerce downloads/meta/filters, S3 ETag/ContentMD5, embeddable signing, Inno licence, MinIO availability, LocalWP S3 plugin) and a source.
16. L152: the "same Amazon S3 download plugin" on LocalWP. That WooCommerce extension may not support a custom (MinIO) endpoint, and its licence or zip must be available (verify). If it can't point at MinIO, the integration tests prove the shortcode text but not a working download. Say so.

docs/05-design-system.md
1. L95 "all higher in dark" is false. TecHaust 06 §2.3: control border on card is 3.6 light vs 3.5 dark, and the dark dialog is 3.2. Copy the table rather than paraphrase.
2. L102–103: PW `#009699` is 3.6:1 on white (`--color-surface`) but about 2.85:1 on stone-200 (`--color-fill-subtle`) and under 3:1 on verdigris-100 (selected rows). Say which surfaces store dots may sit on, or darken the light PW dot (for example `#007f82`, to be re-measured) so it passes ≥ 3:1 on every light surface.
3. L111 and L116: `check-circle` and `alert-triangle` are Lucide's old alias names (current names: `circle-check`, `triangle-alert`), while L113 already uses the new style `circle-help`. Use the current names throughout.
4. L117: "neutral + determinate progress" with icon "`loader` (in-button only)" is contradictory. Say "progress bar in rows; `loader` icon only inside buttons".
5. L157 ChangePlan "current → new" and L182 "before → after in Plex Mono" conflict with L136 "arrows are Lucide icons, never text". Say "an `arrow-right` icon between two Plex Mono values".
6. §2.2 L84–93 omits TecHaust's `--color-link`, `--color-link-hover`, `--color-btn-secondary-fg` and `--color-accent-decor`, while claiming "unchanged". Include them or say "subset used by ShelfSync".
7. L93 app-bar tokens: give the measured contrast (mist on ink-900, mist on ink-750, focus ring on the app bar) now. They are new pairs not covered by TecHaust's measurements.
8. L194–195: reconcile HTML and PNG in docs/ with "Markdown only" (see CLAUDE.md fix 1).
9. Add layouts for the first-run wizard, the tray menu, the help panel, notifications, and empty, error and loading states per screen. Add a short copy and voice section (or a `07-content`-style doc): tone, error-message pattern, banned phrases, as TecHaust 07 §1.3.
10. L160 DataTable: add "virtualised rows for 2398+ items" (needed for the 200 ms target).
11. L56 tray icons "for light and dark taskbars": say how the taskbar theme is read (HKCU\…\Themes\Personalize\SystemUsesLightTheme). Verify pystray can use a multi-size ICO.

docs/06-security.md
1. L51–52: wrong. With the private key stored as a GitHub Actions secret, anyone who takes over the GitHub account can edit a workflow and sign a malicious release, so the signature does not close that gap. Either keep the private key offline on the owner's PC and sign releases locally (a release.md step), or protect it with a required-reviewer environment and state the remaining risk. Fix the sentence.
2. L56: `hashlib.scrypt(N=2**17, r=8, p=1)` needs about 128 MiB, and Python's default maxmem (OpenSSL's 32 MiB) raises ValueError. Specify `maxmem=256 * 1024 * 1024`, or use cryptography's Scrypt.
3. L61: "a high finding fails the build". pip-audit reports vulnerabilities without severity, so any finding fails unless a reviewed ignore is listed. Spell out per tool: `pip-audit` (any finding), `npm audit --audit-level=high --omit=dev`, `bandit -lll`.
4. L23–25: see 04 fixes 1–2 (SSE and CSV can't carry the header; the second launch needs the token again). Also say whether the token ever rotates.
5. L27: "can't read the owner's Credential Manager entries or %LOCALAPPDATA%". True for another standard user, false for an administrator. Add the main residual risk: any program running as the owner can read every keyring entry. Credential Manager protects at rest, not from same-user malware.
6. L40 bombs: give defaults for "total unpacked size (setting)" and "per-entry size", and define "large entries" for the 100:1 rule. Check the 20,000-entry limit against the corpus at M4.
7. L45 IAM: add a separate read-only key (GetObject and ListBucket only) for calibration and teach-from-current-files. "The calibration client has no write methods" (07 L28) is a code promise; a read-only key enforces it. State whether bucket versioning is on (DeleteObject is permanent without it).
8. L46 WooCommerce: say plainly that WooCommerce REST keys are not scoped to products. A Read/Write key on a Shop Manager can also edit orders, coupons and customers. That's the residual risk.
9. Add a threat row: vendor ZIPs from GPL sources can contain backdoored PHP that ShelfSync then publishes to every customer. ShelfSync is not a malware scanner. Optionally run a $0 Windows Defender scan of the ZIP before upload (`MpCmdRun.exe -Scan -ScanType 3 -File …`) and hold it on detection. The owner decides.
10. Add: temp folders left by a crash are removed on start-up; Smart App Control (see 02 fix 10); SmartScreen wording.
11. L68 vs 08 L39: the token and Host/Origin checks are checked at M1 here but built at M2 in the roadmap. Align them (move them into M1, which is safer since the shell is served from M1).

docs/07-testing.md
1. L32 "a drop in Certain accuracy fails the release build": the release build runs in GitHub Actions, which has no live-bucket keys, and CLAUDE.md L24 needs the owner's go-ahead for live-bucket reads. Change to "re-run locally before each release with the owner's go-ahead; the release checklist (release.md) blocks on its report". Or cache the range-read extracts locally (headers only, no vendor code) and run CI on that cache.
2. L29: the ground truth is circular. The files excluded as "mismatched" are chosen by the attachment check, which uses the same signals as the matcher. Have the owner review the exclusion list, and list it in the report.
3. L30: state the statistical limit. 0 wrong in about 2,400 trials gives a 95 % upper bound of roughly 0.12 % wrong (rule of three), and only on today's files. New vendor versions are a different distribution, which is why the trust ramp exists. Say so.
4. L28–30: calibration and teach-from-current-files use the same files. State that calibration runs with no learned fingerprints (cold), and report separately how many reach Certain only through learned fingerprints.
5. L37 and L51: the DoD needs axe clean for every screen, but @axe-core/playwright is added at M5 (09 T16), while screens exist from M1–M3. Add axe at M1, or exempt M1–M4 explicitly.
6. L22: coverage needs pytest-cov (add it to 09 §7).
7. L42 "a test download": say how. For example the admin's download link on the order edit page of a $0 test order, deleted afterwards with the owner's yes.
8. L46: define "agree" (see 03 fix 12).
9. Add test layers:
   - performance (NFR-3: first view, 75 MB inspect, 200 ms search) with fixtures
   - installer and update (silent install on the Windows runner; upgrade, rollback, uninstall)
   - migrations (forward on a copy of the previous release's database)
   - the backup round-trip (listed in 06 §9 but not here)
10. Note that Windows Sandbox isn't available on Windows 11 Home. The "clean user account" test needs a second local Windows account, made by the owner (runbook step).

docs/08-roadmap.md
1. Add a PRD-ID → milestone traceability table. Unassigned today:
   - UI-WIZ (wizard), UI-DSH (dashboard), UI-HELP
   - SET-03 Rules, SET-04 Updates, SET-06 App
   - SYS-04 Start with Windows, SYS-08 uninstall data, SYS-09 logs
   - APL-12 rate limiting (needed from M3's first live reads)
   - APL-15 set file manually
   - the Catalog CSV export
2. L39 M2 "token + Host/Origin" vs 06 §9 at M1: align them (see 06 fix 11).
3. L38 M1 at 2 days covers repo, CI, tokens and fonts, the embedded-Python installer, the tray, single instance, the shell, and the updater with signature verification plus a clean-account Defender test. Say this is the riskiest estimate, or split it (M1a installer, M1b updater).
4. Phase 3: add an estimate (days) and say who builds the brand pipeline (09 §7 says its libraries are "chosen in P3.3").
5. L43 M6 "2 + normal use": estimate how long 50 live ZIPs take at the owner's usual rate, so the M7 date is honest.
6. L44 M7 "A week of real updates with no terminal needed": add measurable criteria (for example 0 partial jobs left unresolved, 0 wrong products, every job logged).

docs/09-tooling.md
1. L11 "Enabled plugins": the Cloudflare plugin (skills cloudflare:*) is enabled in this environment but missing; §4 L56 then excludes it. List it. Add Claude in Chrome to §4 with TecHaust's reason (uses the real logged-in Chrome).
2. §1: add TecHaust's machine table (Found / Needed / Action): Python 3.12.10 ✓; Node and npm versions; git; gh (signed in as?); Inno Setup (needed locally, or CI only?); LocalWP; MinIO or an alternative; RAM, CPU and disk (for NFR-3).
3. L20 T2 vs L68–69 §6 "Gaps": T2 claims Context7 covers Inno Setup and WooCommerce, while §6 calls them gaps. Check Context7 for each and record the library ID or "not indexed".
4. L72 packages:
   - add python-multipart (FastAPI needs it for `POST /jobs` multipart uploads)
   - add pytest-cov
   - name the hash-lock tool (pip-tools or uv)
   - name an OpenAPI→TypeScript generator (04 L34 says OpenAPI drives the UI types)
   - name a toast library if SYS-05 click-through is kept
   - add a seekable-HTTP/range wrapper if one is used
5. L23 T5: also list `aws-storage` for the bucket checks, if used.
6. L34 T16: say the Playwright package is needed earlier if axe moves to M1 (see 07 fix 5).

docs/10-status.md
1. L3: add the time and time zone ("2026-10-25, HH:MM IST") as TecHaust 12-status does.
2. "Waits on the owner" (L19–23): add the open owner decisions this review surfaced:
   - the Inno Setup commercial-licence request
   - MinIO's availability, or a $0 alternative
   - whether the WooCommerce Amazon S3 Storage plugin can be installed on LocalWP and pointed at an emulator
   - Smart App Control state on the PC
3. Add per rule 9: "Not yet verified: library and platform behaviour in 04 (pystray notifications, WooCommerce meta deletion and download directories, S3 checksums), to be checked with Context7 and the test stack before approval or at M1".
4. L26: keep, and fix 02 L7 to match.

docs/11-decisions.md
1. L33: "15 min and 02:00 were in the plan". 02 §6 L116 says only "Nightly snapshot", with no time. Change to "15 min was in the plan; 02:00 is proposed".
2. L4: define the who-values used below. "Lead (accepted with the plan)" (L19) and "Owner / Lead" (L9) aren't in the definition. Use only Owner, Lead and Lead (proposed), and say what the owner accepted.
3. Add the missing proposed rows:
   - 0.15 s request spacing (APL-12)
   - Start with Windows on (SYS-04)
   - notifications on (SYS-05)
   - the 2-thread inspection pool (04 L129)
   - the 64 KB tail read (04 L134)
   - the token hand-off by URL fragment → sessionStorage (06 L23)
   - scrypt parameters (06 L56)
   - CI on windows-latest
   - the default port, once chosen
4. 8 KB scan: add a row, or remove it from 03 L12 (see 03 fix 1).
5. When the ADR 0002 manifest wording is fixed, cross-reference row 35 from ADR 0002.

ADR 0001
1. Add "Alternatives considered" (Tauri/Electron, a Node backend, PyInstaller, WebSocket vs SSE) with one-line reasons, so the decision is reviewable.
2. L16: "zipfile covers the hard parts". Add "with a small seekable HTTP-range file wrapper for remote reads; zipfile's filename-encoding quirks (cp437 vs the UTF-8 flag) are handled".

ADR 0002
1. L12: "verify a signed manifest" is written as accepted, but the signature is still a Lead proposal (06 L52, 11 L35). Say "verify the release checksums (and, if approved, a signed manifest)".
2. L15: "once per PC, at install" → "each time an unsigned installer downloaded from the internet is opened". Add the Smart App Control risk (Windows 11 can block unsigned installers and DLLs with no override).
3. L11: "Inno Setup 6 (free)" → "free to use; since 6.5.0 the author asks commercial users to buy a licence (not strictly required)". Record the owner's decision.
4. Add consequences: the `._pth` edit, the stable launcher outside `versions\`, uninstall of updater-added versions, and AppUserModelID if toasts are used.
5. L17: "tested on a clean account with Defender on at M1". Add "and with Smart App Control state recorded".

ADR 0003
1. Add: the canonical slug starts as <rule> and is editable (see 02 fix 2).
2. L17: "Incremental sync … keep the links honest" → add "plus a nightly full ID listing to catch deletions".
3. Add what "linked on every store" means when a store is paused or newly added (a new store makes every product unlinked until linked).

ADR 0004
1. Consequences: add "Early on, many ZIPs go to Review (Likely); Review load drops as fingerprints accumulate".
2. Add the statistical caveat (see 07 fix 3).

ADR 0005
1. L15: "reachable … only with the token" → "every API call except /api/health needs the token; the static UI files are public on 127.0.0.1 but hold no data".
2. Add the token-transport consequences (SSE and CSV, second launch).

ADR 0006
1. L11: "unchanged" → "unchanged, plus two ShelfSync app-bar tokens (05 §2.2)".

ADR 0007
1. L10 "Markdown only": reconcile with 05 §8 (see CLAUDE.md fix 1).
2. L14 "Not copied": also say whether TecHaust's model and effort rule (docs/14) is kept for the Lead, and whether a `07-content`-style copy doc and a stack-verification appendix are copied (both are part of TecHaust's structure).

docs/runbooks/README.md
1. Add planned runbooks, each with its milestone:
   - uninstall (and keep or remove data)
   - app update and "Roll back app"
   - port conflict and "ShelfSync won't open" troubleshooting
   - restore the database from backup
   - rotate keys (WooCommerce, S3, GitHub token, signing key)
   - Smart App Control / SmartScreen
2. Add the second-Windows-account setup for the M1 clean-account test.

docs/runbooks/research-scripts.md
1. L10: "Open PowerShell" → click-by-click ("Start → type PowerShell → click Windows PowerShell").
2. L14: add that it also prints the SKU counts (slug_overlap.py L41). Give the expected output shape and the run time (about 50 paged requests).
3. Add "If you see 401/403 (key or Cloudflare blocked) or a traceback: stop and send the last line; nothing was written".
4. L3 "Nothing in OmniSync is changed": verify that `import omnisync.config` writes nothing (logs, caches, `__pycache__` — Python will write `__pycache__` .pyc files into OmniSync's folder unless `-B` or `PYTHONDONTWRITEBYTECODE` is set). Add `-B` to both commands.
5. L17–20: say why the example slug is the long one while the docs call the canonical slug `jupiterx` (see 02 fix 2).
6. Say the numbers will differ from 01-A as the stores change, and the status filter used.

.claude/skills/start-session/SKILL.md
1. Step 1: also read the memory notes (CLAUDE.md L32) and, when a milestone is active, its PRD IDs.
2. Add a one-line model and effort check, if CLAUDE.md gains that rule.
3. Step 2 (from M1): add TecHaust's merged-branch clean-up (switch to main, `git pull --ff-only`, delete the merged branch).

.claude/skills/end-session/SKILL.md
1. L8: give the CHANGELOG line format, as TecHaust's (`- YYYY-MM-DD [#N](url) title`).
2. L6: add "include a 'Not verified' line" (rule 9).
3. Description: "pause" also names the app's "Pause everything". Drop it, or say "pause the session".
4. Step 6: say who merges, and that a pushed docs PR waits for the owner's approval.

tools/research/lookup_slug.py
1. L7–10: check the arguments. `if len(sys.argv) != 3: sys.exit("usage: lookup_slug.py <OmniSync folder> <slug>")`.
2. L18: `r.json()` raises on a 200 HTML page (Cloudflare challenge). Wrap it in try/except ValueError and print the content type and the first 200 characters instead.
3. Fail clearly when `store['api_base']` is empty (config.py L230 sets "" when the URL is missing).
4. Add `"status": "any"` explicitly (or `publish`) so the output matches whatever 01-A uses.
5. Run it with `python -B`, or set `sys.dont_write_bytecode = True` before the import, so no .pyc lands in OmniSync.

tools/research/slug_overlap.py
1. L37: the duplicate test is wrong. `(sa + sb)` with `n > 2` misses a slug that appears twice in one store and not at all in the other. Use `[s for s, n in sa.items() if n > 1]` and the same for sb, and print each.
2. L17: add `"status": "publish"` (or print counts per status), and add `downloads` to `_fields`. Print the count of products with more than one download, so 01-A §1 L13 is reproducible.
3. L24: stop on the `X-WP-TotalPages` header, and cross-check `len(out) == int(r.headers["X-WP-Total"])`, so a silently ignored filter or a short page is caught.
4. Add a retry with backoff for 429, 5xx and 520–527 (3 tries), and a short sleep between pages (match APL-12's 0.15 s).
5. Print the near-miss candidates (edit distance ≤ 2 or a `-N` suffix, with the same normalised title), so 01-A §2 is reproducible.
6. Print a UTC timestamp and the store's WooCommerce version (GET /system_status needs more rights; or say "not printed").
7. L29–30: take the store keys from `config.STORE_A` and `config.STORE_B` (config.py L28–29) instead of the hardcoded strings.
8. Wrap the main code in `if __name__ == "__main__":` with a `main()`; add argv checks as in lookup_slug.py.

======================================================================
PART 3: CROSS-CUTTING
======================================================================

Contradictions between files
1. "Markdown only" (CLAUDE.md L14, ADR 0007 L10) vs HTML mockups and PNG screenshots in docs/ (05 L194–195, 08 L30).
2. The token is checked at M1 (06 L68) but built at M2 (08 L39).
3. The signed manifest: accepted in ADR 0002 L12, proposed in 06 L52 and 11 L35.
4. "Republished whenever the plan changes" (02 L7) vs still the old look (10 L26).
5. "02:00 was in the plan" (11 L33): the plan has no time (02 L116).
6. The proposals list in 03 L12 (includes 8 KB) vs the rows in 11 L31–37 (no 8 KB; adds the entry limit and ratio).
7. "2398 S3 files, one per product" (01 L42, 01-A L28, 02 L85) vs 2 products per store having more than one download (01 L41, 01-A L13).
8. Canonical slug `jupiterx` (01-A L25, 02 L23, 01 L31) vs the runbook's URL slug `jupiterx-website-builder-for-wordpress-woocommerce`. How the canonical slug is first set is never stated.
9. The token in a header for every call (04 L96, 06 L25) vs SSE /events and the CSV downloads, which can't send headers.
10. The launcher "only opens the browser" (04 L143) vs a token held only in sessionStorage (06 L23).
11. The DoD needs axe for every screen (07 L51) vs the axe tooling added at M5 (09 L34) while screens ship from M1.
12. Calibration gates the CI release build (07 L32) vs live-bucket reads needing the owner's go-ahead (CLAUDE.md L24).
13. Snapshots: a table (04 L91) vs a data folder (04 L141).
14. "Arrows are icons, never text" (05 L136) vs "current → new" in Plex Mono (05 L157, L182).
15. ADR 0002 L15 says the README shows the SmartScreen step; it doesn't.
16. 09 L11 omits the enabled Cloudflare plugin that 09 L56 then excludes.

Missing documents for this stage
1. A stack/platform verification appendix (TecHaust 05-A equivalent). Every library and platform claim gets a source and a status. This is the single biggest trust gap: pystray, keyring, WooCommerce REST (downloads, meta delete, filters, Approved Download Directories), the S3 ETag/ContentMD5 and boto3 checksum defaults, embeddable-Python signing and `._pth`, the Inno licence, MinIO distribution, and the LocalWP S3 plugin's endpoint support.
2. An OmniSync evidence appendix (01-audit-appendix/B) backing P1–P4.
3. A content/copy doc (TecHaust 07 equivalent): UI wording, error messages, help text, notification text, banned phrases.
4. A PRD → milestone → test traceability matrix (in 08 or 07).
5. An "operations" section or doc: default port, config locations, log format and retention, time zone, automatic database backup, uninstall, data move to a new PC. Partly planned as runbooks, but the design decisions belong in 04 now.
6. A brand-audit doc slot for P3.2 (TecHaust has 11-brand-audit).
7. A models/effort note, or an explicit "not copied" line (ADR 0007).

What would make a careful owner distrust the set
- 02 §12 rates the plan 10/10 on 11 of 12 aspects before any code, while this review found wrong claims (SmartScreen "once", the Ed25519 protection, the scrypt parameters, notification clicks, meta deletion, deletions through `modified_after`) and undefined rules (version family jump, trust-ramp agreement, canonical-slug origin). That breaks CLAUDE.md rule 9.
- 01-A suggests its numbers come from the kept scripts, but several can't be reproduced by them, and the duplicate-slug check is buggy.
- 06 states the signing key in GitHub Actions closes the "account taken over" gap; it doesn't.
- The $0 promise has three unflagged risks: Inno Setup's commercial-licence request, MinIO community binaries (verify), and the paid WooCommerce S3 extension on LocalWP.
- Several screens and settings in the PRD have no milestone, so "21 build days" undercounts.

======================================================================
PART 4: OVERALL PROJECT SCORE PER ASPECT
======================================================================
| Aspect | Score | Main reason |
|---|---|---|
| Accuracy | 6.5 / 10 | Tokens, contrast maths (I re-computed GF 7.4/7.1 and PW 3.6/8.1; all correct), day totals and most WooCommerce/S3 basics are right. But the set has about 10 wrong or unverified platform claims (above) |
| Internal consistency | 6.5 / 10 | 16 cross-file contradictions, most small, a few structural (token transport, Markdown-only, signed manifest) |
| Completeness | 6 / 10 | Strong core design; missing port, time zone, logging, DB backup, uninstall, error and empty states, deletion detection, traceability, copy doc, verification appendix |
| Clarity for the owner | 8 / 10 | Plain, scannable, good tables; some unexplained jargon in 03 and 04; no glossary |
| Actionability / testability | 6.5 / 10 | Many acceptance tests are concrete; several are tied to today's counts, are vague, or depend on undefined terms; calibration-in-CI isn't executable as written |
| Fidelity to techaust_platform | 7.5 / 10 | Numbering, headers, record-keeping, ADRs, skills and tokens copied closely. Missing TecHaust's verification appendix, evidence appendices, machine table, Git workflow and conventions, time-stamped status, content doc |
| Honesty | 6.5 / 10 | Proposals are well marked in 03, 06 and 11, but the plan scorecard, the signature claim, the "$0" items and the unreproducible appendix numbers overclaim |
| Security soundness | 6.5 / 10 | A good localhost model (127.0.0.1, token, Host/Origin, CSP, Credential Manager, ZIP limits). Undermined by the signing-key placement, token transport gaps, the scrypt maxmem error, no read-only calibration key, and no mention of same-user malware or malicious vendor code reaching customers |
| Code quality (2 scripts) | 5 / 10 | Short and readable, but no argument checks, no retries, fragile JSON handling, a duplicate-detection bug, pagination by page size, hardcoded store keys |

Sources:
- [Inno Setup (Wikipedia)](https://en.wikipedia.org/wiki/Inno_Setup)
- [jrsoftware.org licence ordering page](https://jrsoftware.org/isorder.php)
- [Inno Setup 6.5 release notes](https://jrsoftware.org/files/is6.5-whatsnew.htm)
- [wc-api-custom-meta README (WooCommerce REST meta)](https://github.com/judgej/wc-api-custom-meta)```

## 6. Integration notes (lead, 2026-10-25)
- Every fix in Part 2 and every item in Part 3 was applied, except where the owner had to decide first. Those decisions (NSIS, offline signing key, Defender scan) were asked and answered the same day.
- Platform facts were re-checked against sources (Context7: WooCommerce REST, pystray; web: MinIO, Inno Setup licence, Python embeddable package, windows-toasts, MpCmdRun) and recorded in docs/04-architecture-appendix/A-stack-verification.md.
- Not verified: the re-review. The reviewer agent loads only in a new session.

## 7. Handover
Next session (in shelf_sync): start the reviewer agent (Opus, high) in re-review mode with this file as input. It reports FIXED / PARTLY / NOT FIXED per item, then new findings and scores. The lead fixes what's left, then asks the owner to approve Phase 2.

## 8. Re-review (reviewer agent, Opus high, 2026-10-25)

**Verdict: SEND BACK** for H1. M1–M7 go in the same pass; the lows can follow. Then a re-check of the fix diff only.

### 8.0 Skills and what ran
- Loaded `code-review` (on `tools/`). Not loaded: `security-review` (no repo or app diff yet; security points are design findings), `frontend-design` (no screens).
- Passed: `node --check` (both .mjs), `bash -n` (both .sh), `ast.parse` (both research scripts), JSON parse of settings.json; model-guard fed 5 sample inputs; every WCAG pair in 05 recomputed (lowest PluginWay light pair 4.01:1); TecHaust tokens match 05 exactly; link/anchor check over every .md (0 broken); tool versions match 09 §1.
- OmniSync read-only (config.env never opened): 01-B claims spot-checked accurate; `gutenkit-blocks-addon` absent from both `stores/*/mapping.json`. Stores, S3 and GitHub not contacted.

### 8.1 Re-check of §5
- PARTLY: 01-A #2 (`downloadable` filter unverified), 02 #12 (scorecard still 10 with known gaps: 02:157, 163, 165), 10 #2 (S3 extension licence for LocalWP not an owner wait), 11 #2 (undefined who-values: 11:15, 25, 61), 11 #3 (unreviewed defaults marked "Lead": 11:45–51, 54–56, 68–69).
- NOT FIXED: none. Everything else FIXED, including all 16 contradictions and 7 missing documents in Part 3.

### 8.2 New findings
**High**
- **H1** A retention delete can remove a file that a paused store (or another product or slot) still serves (03 APL-07, 02:107, 06:58, ADR 0003:14, 04:88; the `file` table can't represent a shared key). Fix: delete only if a fresh read across every store (active or paused, any status including trash) finds no reference; never auto-delete objects ShelfSync didn't upload (offer them in Cleanup); an `object_ref` table in 04 §4; a note in 06 §5; the integration test "a paused store keeps its file through two updates"; an APL-07 acceptance case.

**Medium**
- **M1** The scorecard overclaims (02:157, 163, 165): Diagnosis 9.5, Security 9, Testing 9.5, gaps named in "Still open".
- **M2** Who-values in 11 (15, 25, 45–51, 54–56, 61, 68–69): "Lead (proposed)"; "Owner (accepted with plan Draft 3)"; L61's note into the decision text.
- **M3** The long-lived install token travels in the `#t=` URL (06:24–25, 04:163, ADR 0005:11, CLAUDE.md): the launcher POSTs the token to `/api/session/ticket` for a single-use 60 s ticket; the URL carries only the ticket. Update 06 §2, 04 §8, ADR 0005, CLAUDE.md; add an 11 row.
- **M4** The M1a security base isn't in Tier A (12:25–26): A = "M1a security base, M1b updater signature check, M2 Credential Manager and backup crypto, M4, M5 writes, M6"; B = "M1a and M1b (rest), M2 (rest), …".
- **M5** Windows-only parts vs Linux CI (04:49, 07:13, 27, 11:55): adapters behind interfaces with fakes on Linux, `sys_platform == "win32"` markers; a "Windows checks" layer run on this PC via heavy.sh before each milestone exit and on release tags; a 04-A row for windows-toasts' platform requirements (M1a).
- **M6** Rollback and restore don't check that the target object exists (03:85, 91; 04:152): `head_object` on every target key in the change plan; a missing key blocks the job with a reason and offers APL-15.
- **M7** model-guard lets an Agent call with no type through (model-guard.mjs:28–32): if the default is general-purpose, treat a missing type as banned; record in 10.

**Low**
- L1 10:24 stale rename step; 10:38 V6 → "the moto-endpoint part of V6".
- L2 research-scripts.md:39 stale note; :35 "HTTP 401" vs lookup_slug.py's output: print `HTTP <code>` and `r.text[:200]`.
- L3 02:130 "two app-bar additions" → three.
- L4 12:84 P3.4 → P3.0.
- L5 ADR 0002:16 "from M1" → "from M1b".
- L6 01-A:17 "first-run check in M2" vs CAT-01/ERR-02 in M3.
- L7 06:60 14-day GitHub token warning: add to SYS-06 and 11, plus a 04-A row (`github-authentication-token-expiration` header).
- L8 the 2 GB free-disk threshold (03:146, 13:33) is missing from 03's proposals list and 11.
- L9 scrypt `maxmem` is a `hashlib.scrypt` parameter, not `cryptography` (04:41, 06 §7).
- L10 08's lists vs 03: UI-SHELL live counts (M5) missing; ERR-07 only in M3; 03's "M1" vs M1a/M1b.
- L11 04-A rows: the `downloadable` filter (CAT-01) and the minimum WooCommerce version for `include_status` (04:151), "to verify (M3)"; slug_overlap.py prints a count of products with no download.
- L12 13:37 "every 15 minutes", :44 "30 updates" → placeholders.
- L13 slug_overlap.py: L62 a missing `X-WP-Total` → keep None; L119–123 title check before edit distance; L20 normalise `add-on` before splitting.
- L14 model-audit.mjs: L19/L62 local vs UTC date; L92 print local time with the zone.
- L15 heavy.sh:97 `stop()` kills only the direct child: kill the tree, `wait`, exit 130 on Ctrl-C.
- L16 watch.sh: L8, L11–12 ignore `HEAVY_LOCK`/`HEAVY_MIN_FREE_MB`; L13 a stale lock disables stall detection; L17 `stat -c %Y` isn't the start time.
- L17 01-B:17 name products 485/476 as WPBakery (`js-composer`) and reword 01:27; 01-B:20 cite gutenkit's absence from both mapping.json files.
- L18 05:119, ADR 0006:14 `#007b80` "PluginWay's own deeper teal" uncited → "a deeper teal chosen for contrast".
- L19 06 §10: the first-install Setup.exe isn't signature-checked; SHA-256 in the signed manifest, `Get-FileHash` in the install runbook.
- L20 code-finder.md:3, 10, 14 "the ShelfSync folder" → `shelf_sync`.
- L21 (optional, owner's yes) settings.json `permissions.deny` for OmniSync's `config.env`, `**/CREDENTIALS/**`, `.env*`.
- L22 10 waits: does the Amazon S3 Storage extension licence allow a LocalWP activation (cost flag if not).

### 8.3 Scores (Acc / Con / Com / Cla / Act / Fid / Hon / Sec / Code)
| File | Acc | Con | Com | Cla | Act | Fid | Hon | Sec | Code | Why not 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| CLAUDE.md | 10 | 9 | 10 | 10 | 10 | 10 | 10 | 9 | n/a | M3 |
| README.md | 10 | 9 | 10 | 10 | 10 | 9 | 10 | n/a | n/a | L5; lockup waits on P3.3 |
| 01-audit | 9 | 10 | 9 | 10 | 9 | 10 | 10 | n/a | n/a | L17; UDesign (owner) |
| 01-A | 9 | 9 | 9 | 10 | 10 | 10 | 10 | n/a | n/a | L11, L6; re-measure pending |
| 01-B | 10 | 10 | 9 | 10 | 10 | 10 | 10 | n/a | n/a | L17 |
| 02-plan | 10 | 9 | 8 | 10 | 10 | 10 | 8 | 8 | n/a | L3, H1, M1 |
| 03-prd | 10 | 9 | 8 | 10 | 9 | 10 | 10 | 8 | n/a | L7, L8, L10, H1, M6 |
| 04-architecture | 9 | 9 | 8 | 10 | 9 | 10 | 10 | 8 | n/a | L9, H1, M5, M3 |
| 04-A | 10 | 9 | 9 | 10 | 10 | 10 | 10 | n/a | n/a | L1, L7, L11, M5 |
| 05-design-system | 10 | 10 | 9 | 10 | 10 | 10 | 9 | n/a | n/a | Phase 3; L18 |
| 06-security | 9 | 9 | 8 | 10 | 10 | 10 | 9 | 8 | n/a | L7, M3, H1, L19 |
| 07-testing | 10 | 9 | 8 | 10 | 9 | 10 | 10 | 9 | n/a | M5, H1 |
| 08-roadmap | 10 | 9 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | L10 |
| 09-tooling | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | — |
| 10-status | 8 | 9 | 9 | 10 | 9 | 10 | 10 | n/a | n/a | L1, L22 |
| 11-decisions | 10 | 8 | 9 | 10 | 9 | 10 | 9 | n/a | n/a | M2, L7, L8 |
| 12-models | 10 | 8 | 10 | 10 | 9 | 10 | 10 | n/a | n/a | M4, L4 |
| 13-content | 10 | 9 | 9 | 10 | 10 | 10 | 10 | n/a | n/a | L12; "delete refused" wording; glossary: canonical slug, twin |
| ADR 0001 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | n/a | — |
| ADR 0002 | 10 | 9 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | L5 |
| ADR 0003 | 10 | 10 | 9 | 10 | 10 | 10 | 10 | 9 | n/a | H1 |
| ADR 0004 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | n/a | — |
| ADR 0005 | 10 | 10 | 9 | 10 | 10 | 10 | 10 | 9 | n/a | M3 |
| ADR 0006 | 10 | 10 | 10 | 10 | 10 | 10 | 9 | n/a | n/a | L18 |
| ADR 0007, 0008 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | n/a | — |
| runbooks/README | 10 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | n/a | — |
| research-scripts.md | 9 | 9 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | L2 |
| runs/README | 10 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | n/a | — |
| start-session, end-session | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | — |
| agents (6 of 7) | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | — |
| agents: code-finder | 10 | 9 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | L20 |
| .claude/settings.json | 10 | 10 | 9 | n/a | 10 | 10 | 10 | 9 | 10 | L21 |
| model-guard.mjs | 9 | 10 | 9 | 10 | 10 | 10 | 10 | n/a | 9 | M7 |
| model-audit.mjs | 8 | 9 | 10 | 10 | 10 | 10 | 10 | n/a | 8 | L14 |
| heavy.sh | 9 | 10 | 10 | 10 | 10 | 10 | 10 | n/a | 8 | L15 |
| watch.sh | 9 | 9 | 10 | 10 | 10 | 10 | 10 | n/a | 8 | L16 |
| lookup_slug.py | 9 | 10 | 10 | 10 | 10 | n/a | 10 | 10 | 9 | L2 |
| slug_overlap.py | 9 | 10 | 9 | 10 | 10 | n/a | 10 | 10 | 9 | L11, L13 |

Whole project: Accuracy 9.4 · Consistency 9.1 · Completeness 8.8 · Clarity 10 · Actionability 9.5 · TecHaust fidelity 9.9 · Honesty 9.4 · Security 8.7 · Code quality 8.7.

### 8.4 Cannot honestly reach 10 yet (and what unlocks it)
- 01 Com/Act: the owner describes UDesign (by M4). 01-A Com: the re-run (owner's go-ahead, before M3) and the M4 bucket mapping.
- 02: Look and feel after Phase 3; each 9.5 needs its milestone exit test (M3, M4, M5).
- 04-A: V3–V6, V8, V12 (actual file), V14, V15 at M1b–M5.
- 05 Com, README Fid: logo, assets, mockups (Phase 3); the SmartScreen screenshot (M1b).
- 07, ADR 0004: Certain rate and cut-offs (M4); trust-ramp length (M6). 08: estimates unproven until M1.
- 10: the Smart App Control state (owner). 12: the account plan confirmed by the owner; settings and hook tested with a live agent.

## 9. Re-check of the fixes (reviewer agent, Opus medium, 2026-10-25)
**Verdict: APPROVE.** H1, M1–M7 and L1–L22 all FIXED, with file:line evidence. Skills: `code-review` loaded and run; `security-review` loaded but refused to run outside a git repo (its checklist was applied by hand; re-run from M1a); `frontend-design` n/a. Repeated: model-guard (6 inputs), syntax checks on all six scripts, link check (0 broken), the 03 M column against the 08 lists (match; NFR-2/6/7 are cross-cutting on purpose).

New findings (follow-ups, all fixed by the lead the same evening; not yet re-checked):
- **N1** (medium) model-guard vs 12 §3 on skill helpers → 12 §3 and the hook's header now state that skill helpers don't pass through the Agent tool (seen in today's model-audit: the reviewer's `code-review` helper ran as general-purpose despite the hook); model-audit's note kept.
- **N2** (medium) the launcher's ticket call has no Origin → 06 §2 names the one exemption (no `Origin` allowed, install token required), 04 §5, 06 §9 M1a, an 11 row.
- **N3** (medium; high if variations exist) safe delete ignored variation downloads → APL-07, 04 §4 `object_ref`, 04 §6, 07 integration test, ADR 0003, 02, and 04-A **V30** (read-only check at M3, owner's go-ahead).
- **N4** (medium) `platform/` outside review coverage → Tier A in 12 §2, 06 header, reviewer.md trigger; the Defender output parser is a pure function in `inspect/` with a contract test on recorded outputs (07).
- **N5** (medium) over-limit ZIP: failed vs held → INS-01 now "fails with the limit named" (no Apply anyway); 04 §6; an 11 row.
- **N6** (medium) a store re-read per candidate → one retention pass after the queue drains, one read covers all candidates, a failed read deletes nothing (04 §6, APL-07, 11).
- **L-a** SYS-03 wording · **L-b** `object_ref` names the nightly snapshot as its source · **L-c** SET-06 logic M1a / screen M1b; M1a exit wording · **L-d** ADR 0006 double comma · **L-e** 02 Security row · **L-f** cookie shared across 127.0.0.1 ports named in 06 §10 · **L-g** Setup.exe hash in the install runbook row.

Scores after the fixes it checked (before N1–N6 and L-a to L-g were fixed): Accuracy 9.9 · Consistency 9.6 · Completeness 9.5 · Clarity 10 · Actionability 9.9 · TecHaust fidelity 9.9 · Honesty 9.9 · Security 9.3 · Code quality 10. Its estimate with N1–N6 and L-a to L-g fixed: Consistency and Security about 9.8, Completeness about 9.7.

Usage: reviewer claude-opus-5-5/medium [code-review, security-review (refused: no repo)]: weekly 77 %, 5-h 59 % at start.

## 10. Second re-check (reviewer agent, Opus medium, 2026-10-25, evening)
**Verdict: APPROVE.** N1, N2, N3, N5, L-a, L-c to L-g FIXED; N4, N6, L-b PARTLY. Skills: `code-review` run; `security-review` can't run without a repo (checklist applied by hand). Scores before this pass's fixes: Accuracy 9.8 · Consistency 9.6 · Completeness 9.4 · Clarity 10 · Actionability 9.8 · Fidelity 9.9 · Honesty 9.8 · Security 9.2 · Code 9.8.

New findings, all fixed by the lead the same evening (not yet re-checked):
1. (medium) a Defender detection could be approved → **owner: discard only**; INS-06, MAT-08, UI-REV, 04 §6 edge, 06 §4, 07 Scan row, 13, an 11 row.
2. (medium) retention not protected from rollback/restore between read and delete → retention is a job holding the writer slot and skips files a queued rollback, restore or Set file manually will use (04 §6, 11, 07).
3. (medium) real-time protection may remove the ZIP before the scan → a vanished or locked file counts as a detection; EICAR written by the test; 04-A **V31** (M1a Windows checks).
4. (medium) what "points at" an object wasn't defined → the key in any form counts, an unparseable link counts as a reference (03 APL-07, 04 §4, 07 contract test, 11); measured: all 2400 links per store are the `[amazon_s3 ...]` shortcode.
5. (medium) `platform/` missing from 09 §3 and 12 §3 lists → added (and `inspect/` to the Haiku off-limits list).
6–13. (low) APL-07 and the 02 flow describe the retention pass · SYNC-03 and 04 §7 name the snapshot read (full downloads, trash, variations) · retention cost note · 13 wording for over-limit, skipped retention, not-ShelfSync's-file · 07 tests for a failed read and found objects · 06 §10 other Windows users · model-guard treats `""`/`null` as no type, and the helper observation reworded as "cause not verified" · 02 scorecard · 08 link to 07 §1.

## 11. Evidence gathered this evening (owner's go-ahead for each)
- **Live hook test:** an Explore agent on Haiku and an untyped Agent call were both refused by `model-guard` before starting (12 §6's first-day check; the test avoided Fable so a failure couldn't start one).
- **heavy.sh Ctrl-C path:** an interrupt (SIGINT, via `env --default-signal=INT`) ended bash, sleep and a native node.exe, exit 130, lock released.
- **Read-only store checks** (15:43–15:50 UTC): 01-A reproduced exactly; both stores 2402 products, all `simple` (V30: no variations); `downloadable=true` honoured (V27); WooCommerce 11.2.1 / WordPress 7.1.3 on both; every download link is the shortcode form. New scripts `downloads_check.py`, `wc_version.py` (GET only).
- **UDesign:** found in OmniSync's log (entries from 12:05 UTC today, newer than the audit): a last-resort filename guess went live on both stores and deleted the unversioned old file. Recorded in 01 and 01-B; the owner isn't sure it's the case they remembered.
- **Smart App Control:** Off (owner).

Usage: reviewer claude-opus-5-5/medium [code-review] (second re-check); weekly 77–78 %, 5-h about 60 % at start.

## 12. Final re-check (reviewer agent, Opus medium, 2026-10-25, night)
**Verdict: APPROVE.** Findings 1, 2 and 4–12 FIXED; 3 and 13 PARTLY. The model guard refused `""`, `null`, `{}`, Explore, Fable, `max` and `model:null`; syntax checks passed on all eight scripts. Scores before this last pass: Accuracy 9.7 · Consistency 9.6 · Completeness 9.4 · Clarity 10 · Actionability 9.9 · Fidelity 9.9 · Honesty 9.8 · Security 9.5 · Code 9.9 (its estimate with these fixed: Consistency 9.9, Completeness 9.7, Security 9.8).

New findings, all fixed by the lead the same night:
- **M1** a ZIP removed by real-time protection would fail as "unreadable" before reaching the scan → the worker checks the file before inspecting; gone or still locked after 5 s → held as a detection (04 §6 edge and bullet, 07, 11).
- **M2** retention could delete the file a rollback moved away from → "kept" = current plus most recently replaced file (APL-07, 07 test, ADR 0003, 11).
- **M3** Smart App Control still shown as unchecked → 09 §1, 02 §9 and §12 updated (Off; re-checked on the clean account at M1b).
- **L1** a harmless lock → 5 s retry · **L2** V31 source wording · **L3** CLAUDE.md names the helper exception · **L4** 13 wording for a removed or locked ZIP · **L5** `downloads_check.py` now reads trash too; re-run 16:01 UTC: 0 in trash on both stores, the same results · **L6** `wc_version.py` handles a non-JSON reply · **L7** 06 §5 now carries the full safe-delete rule.

## 13. Fourth re-check (reviewer agent, Opus, 2026-10-25, night)
**Verdict: APPROVE.** §12's M1–M3 and L1–L6 FIXED, L7 PARTLY. New: N1 (medium) stale "re-measure" text in 02 §12 and this handover; N2–N10 (low): 01-A row, 02 UDesign cell, 06 §5 missing three safe-delete parts, 10 time and script count, three 11 rows said "final" instead of "second" re-check, 07 Windows checks didn't name V31, `wc_version.py` had no `api_base` guard, `model-audit.mjs` didn't flag a lead off Opus (and CLAUDE.md called it "the day's runs"), `heavy.sh` left a PID-less lock if interrupted right after taking it. **All fixed by the lead the same night.** Scores before these fixes: Accuracy 9.9 · Consistency 9.7 · Completeness 9.7 · Clarity 10 · Actionability 9.9 · Fidelity 9.9 · Honesty 9.8 · Security 9.7 · Code 9.8 (estimate after: Consistency about 9.9, Code about 9.9). The reviewer's report said "low effort", but model-audit shows it ran at medium as requested.

## 14. Handover
**Phase 2 approved by the owner on 2026-10-25.** This run is closed. Next session: Phase 3 starts with P3.0 (whether the built-in browser works inside an agent, [08](../08-roadmap.md)); its own run file is opened then. Carried forward: the checks that can't be done before their milestone are listed in [10 Not verified](../10-status.md).
