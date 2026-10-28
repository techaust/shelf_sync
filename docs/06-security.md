# 06: Security

| | |
|---|---|
| **Phase** | 2, Project documentation (**approved by the owner 2026-10-25**); corrected after the 2026-10-25 independent review |
| **Date** | 2026-10-25 |
| **Implements** | [03 PRD](03-prd.md) INS-05, INS-06, SYS-06, LOG-01, SET-05, NFR-5 · [ADR 0005](adr/0005-localhost-only.md) |
| **Reviewed by** | The `reviewer` agent with `security-review` on every change to `secure/`, `inspect/`, `apply/`, `update/`, `platform/`, the API middleware and the installer ([12 §2](12-models-and-usage.md): Tier A) |

## 1. What we protect, and from what

| Asset | Threat | Main defence |
|---|---|---|
| WooCommerce keys | Read from disk, logs or a backup; used by a web page | Credential Manager (§3), redaction, encrypted backup, nothing secret reaches the browser |
| S3 keys | The same | The same, plus least-privilege policies and a separate read-only key (§5) |
| The live stores' downloads | A wrong file; a forged request | Matching guards, change plans, edit and read-back checks ([02 §6](02-plan.md)); session cookie + Host/Origin (§2) |
| **The stores' customers** | **A vendor ZIP with backdoored code, published to everyone who bought the product** | **Windows Defender scan before upload; a detection or a failed scan holds the job** (§4). ShelfSync is not a malware auditor; this catches known malware only |
| The owner's PC | A hostile ZIP (path traversal, bombs) | Safe reader (§4) |
| The app itself | A tampered update | Releases signed with the owner's **offline** key (§6) |
| Customers' access to purchases | A download replaced under a new ID | Same download ID kept (APL-04) |

## 2. Unreachable from outside
- The server binds to **`127.0.0.1` only**, never `0.0.0.0`.
- **Install token:** 32 random bytes made on first run, kept in Credential Manager. "Reset access token" in Settings makes a new one and ends every open session, so each tab signs in again through the tray icon or the Start menu (owner, 2026-10-26).
- **Getting a session (single-use ticket):** the launcher (and a toast click) sends the install token straight to `POST /api/session/ticket` and gets back a **ticket**: random, single-use, valid for 60 s. It opens `http://127.0.0.1:<port>/#t=<ticket>`. The install token itself never appears in a URL, so it never reaches browser history, history sync or the browser's command line. The page sends the ticket once to `POST /api/session`, removes it from the address bar, and gets back a **session cookie** (`HttpOnly`, `SameSite=Strict`, `Path=/`, browser-session lifetime). That cookie works for every call, including `GET /api/events` (SSE) and the CSV downloads, which can't send custom headers (04-A V22). A second launch or a new tab gets a fresh ticket, so it's always signed in. A used, expired or unknown ticket is refused.
- **Which requests need it:** every `/api` route except `GET /api/health` and the two sign-in routes, `POST /api/session/ticket` and `POST /api/session` (each with its own checks, below; the full table is in [runs/m1a.2-security.md](runs/m1a.2-security.md) item 11). The static UI files (HTML, JS, CSS, fonts) are served without it; they hold no data.
- **Host and Origin checks:** requests whose `Host` isn't `127.0.0.1:<port>` or `localhost:<port>` are refused; state-changing requests whose `Origin` is missing or different are refused. This blocks web pages the owner visits and DNS-rebinding tricks.
- **The one exception, `POST /api/session/ticket`:** it's called by the launcher (a Python program, not a browser), so it carries no `Origin` and no `X-ShelfSync`. It's exempt from those two checks **only when no `Origin` header is present**, refuses any request that carries one (so no web page can use it), and requires the install token in an `Authorization` header. The Host check still applies.
- **CSRF:** besides `SameSite=Strict` and the Origin check, state-changing calls must carry `X-ShelfSync: 1`. Browsers can't add that header to a cross-origin request without CORS, and ShelfSync sends no CORS headers. `SameSite` doesn't separate ports (another server on `127.0.0.1` is the same site), so against other local servers the Origin and `X-ShelfSync` checks are what protect ShelfSync (04-A V32).
- **Headers:** a strict Content Security Policy (`default-src 'self'`, no inline scripts, `frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- **No login screen** ([ADR 0005](adr/0005-localhost-only.md)). Another standard Windows user on this PC could reach the port but has no token, and can't read the owner's Credential Manager or `%LOCALAPPDATA%`. An administrator account can read anything (§10).

## 3. Secrets
- In **Windows Credential Manager** (keyring), one entry per secret; never in SQLite, settings, `runtime.json` or logs.
- The UI shows them **masked** (store keys `ck_••••a91f`; an S3 key ID its first and last four, `AKIA••••9XYZ`; an S3 secret only `••••`; never the length) and can only **replace** them (write-only endpoint); a secret never travels back to the browser.
- **Log redaction:** one `redact` step, applied to every final log line (tracebacks included), every HTTP error body and every other output path, masks anything shaped like `ck_…`, `cs_…`, AWS keys, GitHub tokens, the install token and the session cookie. A test sends known secrets through every log path and fails if any appears.
- **The one raw file:** the launcher's stall report, `tmp\shutdown-stall.txt` (M1a.5), is written by Python's `faulthandler` without `redact`. It holds only thread ids, file paths, line numbers and function names, never values. The next start reads it back through the redacting log handler (capped at 64 KB, and never through a link), then removes it with the rest of `tmp\`.
- Errors from the stores and AWS are stripped of signatures and auth headers before they're shown or logged.
- **Entry names** (M2): `install-token`, `github-token`, `s3-rw-key-id`, `s3-rw-secret`, `s3-ro-key-id`, `s3-ro-secret`, and one pair per store, `store-<id>-key` and `store-<id>-secret` (store ids are never reused). Every stored value is registered with `redact` at start-up and when it is set or read. "Remove my data" deletes the fixed names and, reading the database read-only, every store's pair (removed stores too).
- **Store keys stay with their store** (M2.1): HTTP Basic over HTTPS only, never in a URL; redirects are never followed; a change of a store's host must come with new keys in the same request, and it deletes the old pair before the new address is saved, so a crash at any point leaves no keys rather than keys on the wrong host. The `httpx` and `httpcore` loggers are kept at WARNING, so no request URL reaches the log.

## 4. Safe ZIP handling and the malware scan
Vendor ZIPs are untrusted input.
- **Malware scan (INS-06):** Windows Defender scans the uploaded ZIP (`MpCmdRun.exe -Scan -ScanType 3 -File … -DisableRemediation`, 120 s timeout, output parsed, 04-A V19) **before** any S3 or store step. A detection holds the job with the threat name and can **only be discarded** (owner, 2026-10-25). If the saved ZIP disappears, or stays locked after retries for 5 s (real-time protection is the likely cause), that counts as a detection too. If the scan can't run (Defender turned off, another antivirus replacing it, timeout), the job is held as "not scanned" with **Apply anyway**. The scan can be turned off in Rules only with a confirmation.
- Read from inside the archive by default. A nested ZIP that must be opened goes into a **per-job temp folder** (`%LOCALAPPDATA%\ShelfSync\tmp\<job>`), removed when the job ends **and at every start-up** (leftovers from a crash).
- **Zip-slip:** entry names are normalised; any with `..`, a drive letter, a leading `/` or `\`, or a reserved Windows name (`CON`, `NUL`, …) is refused.
- **Symlinks and special entries** are ignored.
- **Bombs (defaults, all settings):**
  - 2 GB total unpacked per upload
  - 300 MB per nested ZIP
  - 500 MB per single entry
  - compression ratio above 100:1 refused for any entry over 10 MB unpacked
  - 20 000 entries per archive, checked against the calibration corpus at M4
  - nesting depth 3
- **Nothing is executed:** PHP and JS are read as text (headers only, first 8 KB); no file is handed to another program except Defender.
- The fuzz corpus covers these cases ([07 §2](07-testing.md)).

## 5. Least privilege
- **AWS, two keys** (policies written with the `aws-iam` skill at M2):
  - **read/write** (daily use): `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on `arn:aws:s3:::<bucket>/*` and `s3:ListBucket` on `arn:aws:s3:::<bucket>`
  - **read-only** (calibration, teach from current files): `s3:GetObject` and `s3:ListBucket` only. The calibration code also has no write methods, but the key is what enforces it
  - **Storage "Test"** (owner, 2026-10-26): it writes a tiny object under `shelfsync-test/` with the read/write key, reads it back with the read-only key, then deletes it with the read/write key. That's about 4 requests per click, a tiny AWS charge. The test object never goes on a store, so it's the one object deleted outside the retention pass.
  - **Bucket versioning:** if it's off, `DeleteObject` is permanent. So ShelfSync deletes an old file only after every store succeeded, always keeps each slot's current and most recently replaced file (so a rollback can be rolled forward), and runs the **safe-delete check** of APL-07 first: in one retention pass that holds the single writer slot, a fresh read of every store (**paused ones included**, any product status including trash, variations included) must find no download whose link contains the object's key in any form; an unparseable link counts as a reference, files a queued rollback, restore or Set file manually will use are left out, a failed or partial store read deletes nothing, and objects ShelfSync didn't upload are never deleted automatically. Whether versioning is on is recorded at M2 (it isn't turned on by ShelfSync: it costs storage)
- **The two policies** (M2, drafted with the `aws-iam` skill; `BUCKET` is the owner's bucket, filled in by the app's guide, never committed):
  ```json
  {"Version":"2012-10-17","Statement":[
   {"Sid":"ShelfSyncObjects","Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject"],"Resource":"arn:aws:s3:::BUCKET/*"},
   {"Sid":"ShelfSyncList","Effect":"Allow","Action":"s3:ListBucket","Resource":"arn:aws:s3:::BUCKET"}]}
  ```
  ```json
  {"Version":"2012-10-17","Statement":[
   {"Sid":"ShelfSyncRead","Effect":"Allow","Action":"s3:GetObject","Resource":"arn:aws:s3:::BUCKET/*"},
   {"Sid":"ShelfSyncList","Effect":"Allow","Action":"s3:ListBucket","Resource":"arn:aws:s3:::BUCKET"}]}
  ```
  To verify against the AWS docs before M2's exit (04-A): `s3:GetObject` covers HEAD and ranged GETs; with `s3:ListBucket` a missing key answers 404, not 403 (APL-08 and APL-14 rely on it); a bucket encrypted with its own KMS key also needs `kms:Decrypt` and `kms:GenerateDataKey`. The owner reads the bucket's versioning and encryption in the S3 console (Properties) and Claude records them.
- **WooCommerce:** keys created for a dedicated **Shop Manager** user, not the admin account, with Read/Write. **Residual risk, stated plainly:** WooCommerce REST keys can't be limited to products. A Read/Write key can also change orders, coupons and customers, so it's guarded like a password.
- **GitHub:** update checks need no token while the repo is public (owner, 2026-10-27). If the owner sets one, it's a fine-grained token with read-only **Contents** on the `shelf_sync` repo only, kept in Credential Manager. It has an expiry date; the app warns 14 days before it, reading the expiry from GitHub's `github-authentication-token-expiration` response header (SYS-06, 04-A V26).

## 6. Signed updates (owner decision 2026-10-25: offline key)
- Each release publishes the installer, a `manifest.json` (version, SHA-256 of every file) and an **Ed25519 signature** of the manifest.
- **The private key lives only on the owner's PC**, encrypted with a passphrase, never in GitHub. CI builds the release unsigned; the owner signs the manifest with one command from the `release.md` runbook, and the signature is uploaded with the owner's yes.
- The app ships the **public key** and refuses any update whose signature or checksums don't verify. So even someone who took over the GitHub account couldn't ship an update ShelfSync would install.
- **First install is different:** a `Setup.exe` downloaded by hand isn't checked by anything ShelfSync controls (there's no installed copy yet). So the signed manifest also lists the SHA-256 of `Setup.exe`, and the install runbook has the owner check it before running it: the release tool on the owner's PC verifies the manifest's signature with the public key kept there (not one fetched from GitHub), then compares the manifest's hash with `Get-FileHash` of the downloaded `Setup.exe`.
- **If the key is lost:** the next release can't be verified by installed copies. The owner then reinstalls once from a new `Setup.exe` carrying a new public key (runbook `key-rotation.md`). A backup of the encrypted key file is kept with the owner's other offline backups.

## 7. Backup export
- One file with the settings and catalog; **secrets are included only when the owner sets a passphrase**.
- The key is derived from the passphrase with the standard library's **`hashlib.scrypt`** (N = 2^17, r = 8, p = 1, `maxmem` = 256 MiB, 04-A V21) and the file is encrypted with **AES-256-GCM**, with a random salt and nonce per export. Without the passphrase the file holds no usable keys.
- Import checks the integrity tag before changing anything.

## 8. Supply chain
- Exact pins with hashes: Python via **uv**'s lock file, the UI via `package-lock.json`. GitHub Actions pinned by commit SHA. **Dependabot** (free) opens update PRs.
- CI on every PR, with explicit failure rules:
  - `pip-audit`: **any** finding fails, unless it's listed with a reason in a reviewed ignore file
  - `npm audit --omit=dev --audit-level=high`
  - `bandit -r backend`: **any** finding fails; a `# nosec` needs its reason next to it
- The embedded Python package comes from python.org with its SHA-256 pinned in the build script, and its executables' signatures are checked.
- No telemetry; outbound hosts are the stores, the S3 endpoint and GitHub only (NFR-5).

## 9. Security checks per milestone
| Milestone | Check |
|---|---|
| M1a | Bind address; install token → single-use ticket → session cookie (used and expired tickets refused; the ticket route refuses any request with an `Origin` and any without the token); Host/Origin/CSRF header; CSP; log redaction |
| M1b | Update signature verification refuses unsigned and tampered releases; installer on a clean account; `Setup.exe` hash listed in the signed manifest |
| M2 | Credential Manager; backup encryption round-trip; both IAM policies; Shop Manager guide; versioning state recorded |
| M4 | ZIP fuzz corpus; EICAR detection and "not scanned" paths; the calibration client uses the read-only key |
| M5 | `security-review` of `apply/` (writes, retries, rollback, deletions, the safe-delete check, the target-file check) |
| M7 | A full `security-review` before handover |

## 10. Residual risks (what ShelfSync can't prevent)
- **Malware running as the owner** can read every Credential Manager entry the owner can. Credential Manager protects secrets at rest and from other standard users, not from malware already on the PC. Keeping Windows and Defender up to date is the defence.
- **An administrator** on this PC can read everything.
- **Other local servers:** browsers scope cookies by host, not port, so another server the owner opens on `127.0.0.1` would receive the session cookie. If that server is the owner's own program, the risk is low: it could already read the install token from Credential Manager. If **another Windows user** on this PC runs it, that user could replay the owner's session cookie (§2: other users can reach local ports). On this single-user PC that's unlikely, and it's the main reason to move to a dedicated host name (`shelfsync.localhost`) later, checked in 04-A first.
- **Port squatting while ShelfSync is closed:** another program (for example another Windows user's) could listen on ShelfSync's port and answer like ShelfSync, so the launcher would send it the install token. From M1a.4 the launcher first asks Windows which process owns the listening socket and sends the token only to ShelfSync running as the same Windows user (04-A V33). Until that check is verified, this risk stays open.
- **A hand-downloaded `Setup.exe`** from a taken-over GitHub account would not be caught by the app's update check (§6); the published hash check in the install runbook is the defence, and it relies on the owner running it.
- **Unknown or new malware** in a vendor ZIP passes a Defender scan. The trust ramp and Review keep a person in the loop, but the code itself isn't audited.
- **The public repo** (during development, owner's choice, [11](11-decisions.md)): the code, the security design, the store names and their WooCommerce/WordPress versions are readable by anyone. No defence here relies on being hidden, and no secret or store address is ever committed (checked before the first push). Running the tests from a fork can't reach secrets: CI uses none and runs on `pull_request` with read-only permissions.
- **WooCommerce key scope** (§5): a leaked Read/Write key can change orders and customers.
- **The S3 read/write key can delete any object in the bucket**, including ones ShelfSync didn't upload. The code never does (APL-07), but the key allows it.
- **Store entries left behind** (M2.1): a roll back from a build with stores to one without them (0002), or a crash while a store is being added, can leave `store-<id>-…` entries in Credential Manager that an older uninstaller doesn't know. They hold keys the owner can revoke in WooCommerce; the owner can also delete them under Windows Credentials.
- **Smart App Control and SmartScreen** (04-A V17–V18) are Windows protections, not threats; they may block or warn on the unsigned installer.
