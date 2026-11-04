# The test stack: moto S3 server, and Laragon

The test stack is where every write is proven before it reaches a real store ([07 §5](../07-testing.md), [04 §10](../04-architecture.md)): a Laragon site with WooCommerce and your Amazon S3 Storage extension, whose "User defined" endpoint points at **moto server**, a local stand-in for Amazon S3 ($0). This page covers the moto half (sections 1 and 2) and the Laragon half (section 3, being written in m2.8).

Nothing here touches your real bucket, AWS account or stores.

## 1. Start the S3 server

**Run these in Windows PowerShell**, one block at a time, in the same window. Go to the `shelf_sync` folder:

```powershell
cd "D:\Business\2. GPL Projects\3. Other Assets\Applications\shelf_sync"
```

Tell uv never to download a Python (this window only):

```powershell
$env:UV_PYTHON_DOWNLOADS='never'
```

Start the server:

```powershell
uv run python testenv/moto_s3.py
```

After a few seconds it prints:

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

Leave that window open while you test. Each request it answers adds one line such as `127.0.0.1 - - [02/Nov/2026 05:30:54] "PUT /shelfsync-test-stack/probe.txt" 200` (the method, the path and the result; never the part after `?`).

What the server is:
- **Only on this PC** (`127.0.0.1`): no other computer can reach it, and no other program can take over its port while it runs.
- **Not reachable from web pages:** it answers only requests addressed to `127.0.0.1:<port>` or `localhost:<port>` (anything else gets "403 Forbidden"), and moto's "any website may call me" setting (CORS) is off, so a page open in your browser can't read, change or empty it. The S3 extension's download links are plain links (the browser goes to them), which don't need CORS; that it works this way is checked when the extension is set up (04-A V6, section 3).
- **In memory only:** nothing is written to disk. Stopping it removes the bucket and every file in it; the next start begins empty with a new bucket.
- **Any key pair works:** it checks no keys or signatures. Use made-up keys (below), **never your real AWS keys**.
- **Not a full copy of Amazon S3** ([04-A V8](../04-architecture-appendix/A-stack-verification.md)): it doesn't refuse a wrong `Content-MD5`, an expired download link or a changed one. Those are proven in other tests and in the live canary (M6), not here.

Options, if you need them (add them after `testenv/moto_s3.py`):
- `--port 47631`: another port, if 47630 is taken. It says so ("Port 47630 on 127.0.0.1 can't be used: …"), so you'd know. ShelfSync's own port is 47615 (up to 47624), so the default stays clear of it.
- `--bucket another-name`: another bucket name.
- `--region eu-west-2`: another region.

### Stop it
Click in its window and press **Ctrl+C**. It prints "Stopped. The bucket and its files are gone (they were in memory only)." Closing the window stops it too.

## 2. Point ShelfSync at it and run the Storage Test

**Only do this while ShelfSync has no real AWS keys saved.** Saving the test stack's endpoint, region, bucket and keys replaces the real ones (there is one storage setting), and **secret keys can't be put back**: ShelfSync never shows a saved secret, and AWS shows a secret only once, when the key is made.
- The endpoint, region and bucket can be noted down and typed back afterwards.
- **Never write a secret key down** to put it back later.
- If your real keys are already saved in ShelfSync, skip this section; or, if you go ahead, plan to make new real keys afterwards with [key-rotation.md](key-rotation.md) and save those.

1. Start the S3 server (section 1) and leave it running.
2. Open ShelfSync › **Settings › Storage** (**Add storage** if nothing is set yet).
3. Fill in, exactly:
   - **Endpoint:** `http://127.0.0.1:47630` (use `127.0.0.1`, not `localhost`: `localhost` works too, but was clearly slower in the tests)
   - **Region:** `us-east-1`
   - **Bucket:** `shelfsync-test-stack`
4. **Save storage.**
5. **Access keys**, made-up values (ShelfSync wants 16 or more letters and digits):
   - **Read and write:** access key ID `TESTSTACKREADWRITE`, secret `TestStackSecretReadWrite1`; **Save keys**.
   - **Read only:** access key ID `TESTSTACKREADONLY1`, secret `TestStackSecretReadOnly1`; **Save keys**.
6. Click **Test connection** (the Test button on Settings › Storage, arriving with T2's screen). It must say "Passed in <n> ms.", with all three steps (write, read, delete) passed, and the server's window shows its four requests for one test file under `/shelfsync-test-stack/shelfsync-test/`: `PUT` 200, `GET` 200, `DELETE` 204, then `HEAD` 404 (the check that the file is gone).

If it says "couldn't reach the storage service", the server isn't running or the port differs from the endpoint. Any other message: send Claude the message and the server window's last lines.

The same check runs automatically in the tests (`tests/test_testenv_moto_s3.py`, the Storage Test through ShelfSync's own S3 client against this script's server).

## 3. Laragon and the S3 extension (the owner's, m2.8)

_Being written in m2.8._ This section has the site's certificate (§3.2) so far. Still to come in m2.8: WordPress, WooCommerce and its two keys, your Amazon S3 Storage extension (your licence allows it on the local test site, [11](../11-decisions.md) 2026-10-25; that row named LocalWP, so it's confirmed for Laragon before m2.8 activates it) set to the S3 server above (04-A V6), the sample products, and the check.

**Decided 2026-11-05** ([11](../11-decisions.md), [runs/m2.0-plan.md](../runs/m2.0-plan.md) §3 Q3):
- The test site runs in **Laragon**, already installed at `C:\laragon`. Its free tier is for non-commercial use only, and you made the call on its terms.
- The test harness (`testenv/laragon.py`) reaches the site over HTTPS with WooCommerce's Basic auth. Only the harness trusts the site's certificate: the ShelfSync app gets no new setting or package.

**Why the site gets its own certificate** ([04-A V57](../04-architecture-appendix/A-stack-verification.md), [runs/m2.8](../runs/m2.8-laragon-test-stack.md) §2):
- Python refuses Laragon's own certificate for `shelfsync-test.test`. Laragon's certificate covers `*.test`, and a wildcard that sits right under `.test` never matches a site name.
- Laragon also rewrites that certificate itself. Adding the site's name to `C:\laragon\etc\ssl\auto.openssl.conf` did nothing. Turning SSL off and on rebuilt that file and the certificate, and dropped the added name (2026-11-05).
- So the harness makes a certificate for exactly `shelfsync-test.test`, and the site uses it (§3.2). You chose this on 2026-11-05.

### 3.1 Make the site (you)
Full steps come later in m2.8. In short, from Laragon's own quick start (laragon.org/docs/quick-start):
1. Open Laragon and click **Start All**.
2. Click **Menu › Quick app › WordPress**.
3. Name it `shelfsync-test`. Laragon makes the folder `C:\laragon\www\shelfsync-test`, downloads WordPress into it, and the site answers at `shelfsync-test.test`.
4. Turn on HTTPS: **Menu › Apache › SSL › Enabled**.

### 3.2 Give the site its own certificate (you, in Windows PowerShell)
Do this after §3.1: the command checks that `C:\laragon\www\shelfsync-test` exists.

**What it writes:**
- `C:\ShelfSync-TestStack\tls\shelfsync-test.test.crt` (the certificate) and `C:\ShelfSync-TestStack\tls\shelfsync-test.test.key` (its private key; only your Windows account can open it). The folder is outside Laragon's own folders, outside the `shelf_sync` folder, and outside `AppData`.
- `C:\laragon\etc\apache2\sites-enabled\00-shelfsync-test.test.conf`, a small Apache file that serves the site over HTTPS with that certificate.

Nothing secret is printed. The key never leaves this PC and never goes into the `shelf_sync` folder.

**Steps:**
1. Open **Windows PowerShell**: click Start, type `PowerShell`, click **Windows PowerShell**. Use this, not the Claude app's terminal.
2. Go to the `shelf_sync` folder:

```powershell
cd "D:\Business\2. GPL Projects\3. Other Assets\Applications\shelf_sync"
```

3. Tell uv never to download a Python (this window only):

```powershell
$env:UV_PYTHON_DOWNLOADS='never'
```

4. Make the certificate:

```powershell
uv run python -m testenv.laragon cert
```

   It prints "Made a certificate for shelfsync-test.test, valid until <date> (UTC).", then its SHA-256 fingerprint and the three files above.
   - If it says "Already there", the files exist from an earlier run; nothing was changed. Add `--force` to the command only if you mean to replace them.
   - If it says "Make the site in Laragon first", do §3.1.
5. Reload Apache with Laragon's own command (laragon.org/docs/cli):

```powershell
C:\laragon\laragon.exe reload apache
```

   Clicking **Stop**, then **Start All** in Laragon does the same.
6. Claude runs `check` once the site's keys are saved (later in this section). It must say "Connected in <n> ms. WooCommerce <version>, …". A certificate problem shows as "The store's security certificate wasn't accepted."

**Why Laragon shouldn't undo this, and what is only assumed:**
- **Documented by Laragon** (laragon.org/docs/pretty-urls): Laragon writes each site's Apache file itself, named `C:\laragon\etc\apache2\sites-enabled\auto.<site>.test.conf`. The template for every one of them is `C:\laragon\usr\tpl\VirtualHost.tpl`. The `cert` command touches neither.
- **Documented by Apache 2.4** (`Include` and name-based virtual hosts):
  - The files in `sites-enabled` are read in alphabetical order. Laragon's `httpd.conf` reads them with `IncludeOptional "C:/laragon/etc/apache2/sites-enabled/*.conf"`, read on this PC on 2026-11-05.
  - The first site whose `ServerName` matches answers.
  - `00-shelfsync-test.test.conf` sorts before `auto.shelfsync-test.test.conf`, so it answers for `shelfsync-test.test` while Laragon's own file stays as Laragon wrote it.
- **Not documented: that Laragon leaves a file without the `auto.` prefix alone.** Laragon's docs don't say so (checked 2026-11-05). Laragon's own `00-default.conf` is such a file. **Unverified until you've done step 7.**
7. **Check that Laragon keeps it.** In Laragon:
   - turn SSL off and on again (**Menu › Apache › SSL › Enabled**, twice: this is what rewrote Laragon's certificate on 2026-11-05);
   - click **Stop**, then **Start All**;
   - in File Explorer, open `C:\laragon\etc\apache2\sites-enabled`. `00-shelfsync-test.test.conf` must still be there. Tell Claude whether it is, and Claude runs `check` again.

   If the file is gone, tell Claude: Laragon does rewrite it, and this part of the runbook changes.

**Keep the files out of `C:\laragon\etc\ssl`.** Laragon rewrites its own certificate files there.

**A browser warns about this certificate** if you open `https://shelfsync-test.test`. Windows doesn't trust it: only the harness does, by the 2026-11-05 decision. Use `http://shelfsync-test.test` for the WordPress admin pages. The harness alone uses `https`, where WooCommerce accepts its keys.

**Renew or replace it:** the certificate is valid for a year (the date is printed). Run step 4 with `--force` (`uv run python -m testenv.laragon cert --force`), then step 5. `check` picks up the new file by itself.

**Undo it:**
1. Delete `C:\laragon\etc\apache2\sites-enabled\00-shelfsync-test.test.conf` and the folder `C:\ShelfSync-TestStack`.
2. Run step 5. The site goes back to Laragon's own settings.
