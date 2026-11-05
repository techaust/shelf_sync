# The test stack: moto S3 server, and Laragon

The test stack is where every write is proven before it reaches a real store ([07 §5](../07-testing.md), [04 §10](../04-architecture.md)): a Laragon site with WooCommerce and your Amazon S3 Storage extension, whose "User defined" endpoint points at **moto server**, a local stand-in for Amazon S3 ($0). This page covers the moto half (sections 1 and 2) and the Laragon half (section 3).

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

## 3. Laragon, WooCommerce and the S3 extension (m2.8)

Each step says whose it is: **(you)** or **(Claude)**. Claude never changes anything under `C:\laragon` itself. Steps marked **unverified** haven't been tried on the real site yet; if one doesn't match what you see, stop and tell Claude what the screen says.

**Decided 2026-11-05** ([11](../11-decisions.md), [runs/m2.0-plan.md](../runs/m2.0-plan.md) §3 Q3):
- The test site runs in **Laragon**, already installed at `C:\laragon`. Its free tier is for non-commercial use only, and you made the call on its terms.
- The test harness (`testenv/laragon.py`) reaches the site over HTTPS with WooCommerce's Basic auth. Only the harness trusts the site's certificate: the ShelfSync app gets no new setting or package.
- Your Amazon S3 Storage licence covers the local test site ([11](../11-decisions.md) 2026-10-25). That row named LocalWP; you confirmed it for Laragon on 2026-11-05.

**Why the site gets its own certificate** ([04-A V57](../04-architecture-appendix/A-stack-verification.md), [runs/m2.8](../runs/m2.8-laragon-test-stack.md) §2):
- Python refuses Laragon's own certificate for `shelfsync-test.test`. Laragon's certificate covers `*.test`, and a wildcard right under `.test` never matches a site name.
- Laragon also rewrites that certificate itself. Adding the site's name to `C:\laragon\etc\ssl\auto.openssl.conf` did nothing. Turning SSL off and on rebuilt that file and the certificate, and dropped the added name (2026-11-05).
- So the harness makes a certificate for exactly `shelfsync-test.test`, and the site uses it (§3.2). You chose this on 2026-11-05.

**One thing `check` doesn't test:** how Windows finds `shelfsync-test.test` (the line Laragon adds to the hosts file). The harness always connects to `127.0.0.1` and only checks the certificate and the name, so a key can never leave this PC. The browser in §3.1 step 5 is what tests the name.

**Every PowerShell command below** runs in the same kind of window:
1. **(you)** Click Start, type `PowerShell`, click **Windows PowerShell**. Use this, not the Claude app's terminal.
2. **(you)** Go to the `shelf_sync` folder:

```powershell
cd "D:\Business\2. GPL Projects\3. Other Assets\Applications\shelf_sync"
```

3. **(you)** Tell uv never to download a Python (this window only):

```powershell
$env:UV_PYTHON_DOWNLOADS='never'
```

### 3.1 Make the site
These follow Laragon's own quick start (laragon.org/docs/quick-start).
1. **(you)** Open Laragon and click **Start All**.
2. **(you)** Click **Menu › Quick app › WordPress**. Type the name `shelfsync-test` and click OK.
   - Laragon makes the folder `C:\laragon\www\shelfsync-test`, downloads WordPress into it, and makes its database.
3. **(you)** Open **Menu › Apache › SSL**. If **Enabled** already has a tick, leave it. If not, click it.
4. **(you)** In your browser, open `http://shelfsync-test.test` and finish WordPress's own setup:
   - choose the site title, an admin user name and a password, and keep the password in your password manager (never in chat);
   - **unverified:** if WordPress asks for database details, Laragon's usual ones are Database Name `shelfsync-test`, Username `root` and an empty Password. If they don't work, tell Claude.
5. **(you)** Check that `http://shelfsync-test.test` shows the new site. This also checks that Windows finds the name.

### 3.2 Give the site its own certificate
Do this after §3.1: the command checks that `C:\laragon\www\shelfsync-test` exists.

**What it writes:**
- `C:\ShelfSync-TestStack\tls\shelfsync-test.test.crt` (the certificate) and `C:\ShelfSync-TestStack\tls\shelfsync-test.test.key` (its private key).
  - The `tls` folder and the key are limited to your Windows account, so no other account on this PC can read the key or swap the certificate.
  - The folder is outside Laragon's own folders, outside the `shelf_sync` folder, and outside `AppData`. The command refuses a folder that holds anything else.
- `C:\laragon\etc\apache2\sites-enabled\00-shelfsync-test.test.conf`, a small Apache file that serves the site over HTTPS with that certificate.

Nothing secret is printed. The key never leaves this PC and never goes into the `shelf_sync` folder.

**Steps:**
1. **(you)** Open Windows PowerShell in the `shelf_sync` folder (the three steps at the top of §3).
2. **(you)** Make the certificate:

```powershell
uv run python -m testenv.laragon cert
```

   It prints "Made a certificate for shelfsync-test.test, valid until <date> <time> <your time zone>.", then its SHA-256 fingerprint and the three files above.
   - If it says "Already there", the files exist from an earlier run; nothing was changed. To replace them on purpose, use **the replace command** below instead.
   - If it says "Make the site in Laragon first", do §3.1.

   **The replace command** (used in step 5 and under "Renew or replace it"): it makes a new certificate and key in place of the old ones. All three files are written first and swapped in together; if anything fails, the old ones are put back.

```powershell
uv run python -m testenv.laragon cert --force
```

3. **(you)** Reload Apache with Laragon's own command (laragon.org/docs/cli):

```powershell
C:\laragon\laragon.exe reload apache
```

   Clicking **Stop**, then **Start All** in Laragon does the same.
4. **(Claude)** Runs `check` once the site's keys are saved (§3.3). It must say "Connected in <n> ms. WooCommerce <version>, …".
   - **"The store's security certificate wasn't accepted."** right after step 3 most likely means Laragon's own site file (`auto.shelfsync-test.test.conf`, with Laragon's certificate) answered instead of ours. Check that `00-shelfsync-test.test.conf` is in `C:\laragon\etc\apache2\sites-enabled` and reload Apache again (step 3).

**Why Laragon shouldn't undo this, and what is only assumed:**
- **Documented by Laragon** (laragon.org/docs/pretty-urls): Laragon writes each site's Apache file itself, named `C:\laragon\etc\apache2\sites-enabled\auto.<site>.test.conf`. The template for every one of them is `C:\laragon\usr\tpl\VirtualHost.tpl`. The `cert` command touches neither.
- **Documented by Apache 2.4** (`Include` and name-based virtual hosts):
  - The files in `sites-enabled` are read in alphabetical order. Laragon's `httpd.conf` reads them with `IncludeOptional "C:/laragon/etc/apache2/sites-enabled/*.conf"`, read on this PC on 2026-11-05.
  - The first site whose `ServerName` matches answers.
  - `00-shelfsync-test.test.conf` sorts before `auto.shelfsync-test.test.conf`, so it answers for `shelfsync-test.test` while Laragon's own file stays as Laragon wrote it.
- **Laragon does rewrite some files that don't start with `auto.`.** When SSL was turned off and on (2026-11-05, 03:54:45 IST), Laragon rewrote its own `00-default.conf` in that folder, along with `httpd-ssl.conf` and `laragon.crt`, and the `sites-enabled` folder changed. Its docs don't say whether it ever removes or rewrites a file it didn't make. **Unverified until step 5.**
5. **(you)** **Check that Laragon keeps it.** In Laragon:
   - turn SSL off and on again (**Menu › Apache › SSL › Enabled**, twice);
   - click **Stop**, then **Start All**;
   - in File Explorer, open `C:\laragon\etc\apache2\sites-enabled`. `00-shelfsync-test.test.conf` must still be there.

   Tell Claude what you see; **(Claude)** then runs `check` again.

   **If the file is gone:**
   1. **(you)** Put it back: run **the replace command** (step 2), then step 3.
   2. **(Claude)** The runbook then needs a way Laragon can't undo, for example Laragon's documented template (`usr\tpl\VirtualHost.tpl`). Claude proposes one; nothing changes until you agree.

**Keep the files out of `C:\laragon\etc\ssl`.** Laragon rewrites its own certificate files there.

**A browser warns about this certificate** if you open `https://shelfsync-test.test`. Windows doesn't trust it: only the harness does, by the 2026-11-05 decision. Use `http://shelfsync-test.test` for the WordPress admin pages. The harness alone uses `https`, where WooCommerce accepts its keys.

**Renew or replace it (you):** the certificate is valid for a year (the date is printed). Run **the replace command** (step 2), then step 3. `check` picks up the new file by itself.

**Undo it (you):**
1. Delete `C:\laragon\etc\apache2\sites-enabled\00-shelfsync-test.test.conf` and the folder `C:\ShelfSync-TestStack`.
2. Run step 3. The site goes back to Laragon's own settings.

### 3.3 WooCommerce and its two keys
1. **(you)** In `http://shelfsync-test.test/wp-admin`, go to **Plugins › Add New Plugin**, search for **WooCommerce**, click **Install Now**, then **Activate**. You can skip WooCommerce's setup questions.
2. **(you)** Go to **Settings › Permalinks**, choose **Post name**, and click **Save Changes**. This makes the `/wp-json/` addresses work.
3. **(you)** Go to **WooCommerce › Settings › Advanced › REST API** and click **Add key** twice:
   - Description `ShelfSync test read`, User: your admin user, Permissions **Read**, then **Generate API key**.
   - Description `ShelfSync test write`, User: your admin user, Permissions **Read/Write**, then **Generate API key**.

   WooCommerce shows each consumer key and secret once. Keep both pages open until step 4 is done. Never paste them anywhere else.
4. **(you)** In Windows PowerShell (top of §3), save them:

```powershell
uv run python -m testenv.laragon keys
```

   It asks for four values in this order: the read-only consumer key, its secret, the read/write consumer key, its secret.
   - Nothing shows as you type or paste. That's on purpose.
   - It prints "Saved read-only key pair for shelfsync-test.test." and "Saved read/write key pair for shelfsync-test.test."
   - A wrong shape says why and saves nothing for that pair. Press Enter on a key to skip that pair and keep any saved one.

   The keys go into Credential Manager under `ShelfSync-TestStack`, never ShelfSync's own entries, named after the site. A second test site would get its own entries with `--site`.
5. **(Claude)** Runs `check` (§3.5).

### 3.4 The Amazon S3 Storage extension, pointed at the S3 server
**Unverified:** the extension's screens haven't been seen on this site yet ([04-A V6](../04-architecture-appendix/A-stack-verification.md)). Claude helps with the exact screen when you get there.
1. **(you)** Download the extension's ZIP from your woocommerce.com account (My Account › Downloads).
2. **(you)** In wp-admin, go to **Plugins › Add New Plugin › Upload Plugin**, choose the ZIP, click **Install Now**, then **Activate**.
3. **(you)** Set its provider to **User defined** (S3-compatible), following the vendor's own instructions on its product page (V6: it needs a small snippet the vendor documents). Use these values, the same as section 2:
   - **Endpoint:** `http://127.0.0.1:47630`
   - **Region:** `us-east-1`
   - **Bucket:** `shelfsync-test-stack`
   - **Access key ID:** `TESTSTACKREADWRITE`
   - **Secret:** `TestStackSecretReadWrite1`

   These are made-up keys: the S3 server checks none. Never type real AWS keys here.

### 3.5 Start the S3 server, add the sample products, check
1. **(you)** Start the S3 server in its own PowerShell window (section 1) and leave it running.
2. **(Claude)** Adds the sample products:

```powershell
uv run python -m testenv.laragon seed
```

   **First, it uploads the 13 sample files to the S3 server** ("Uploaded 13 sample files to shelfsync-test-stack at http://127.0.0.1:47630.").
   - It does this on every run. The S3 server keeps everything in memory, so after a restart a new `seed` puts the files back.
   - If the server isn't running, it says so and still adds the products.

   **Then it prints one line per sample:** "Created aurora (#…).", and later "Unchanged …" or "Updated …". The last line counts them.
   - A second run changes nothing that is already right.
   - It only ever touches its own samples. Each one carries the marker `shelfsync_test_sample`; ShelfSync's samples have no SKU, like the real stores.
   - If one of your own products already uses a sample's slug, it stops before writing anything and names that product.
3. **(Claude)** Checks the connection the way Settings does:

```powershell
uv run python -m testenv.laragon check
```

   It should say "https://shelfsync-test.test: Connected in <n> ms. WooCommerce <version>, 10 downloadable products." Settings counts every status except trash (draft, pending and private included), so: aurora, pixel-forms, northwind, harbor, quiet-cache, tidewater-seo, mosaic-gallery, mosaic-gallery-bundle, emberline and lantern. The variable product (its files are on its variations), the service and the trashed one aren't counted. **Unverified** until it runs.

**The samples** (the full table is in [runs/m2.8](../runs/m2.8-laragon-test-stack.md) §3):
- simple themes and plugins, and one product with two downloads;
- one variable product whose two variations carry the downloads;
- one product that isn't downloadable;
- draft, pending, private and trashed products;
- two products sharing one file;
- an old unversioned file, and a file at the bucket's root.

Each download is a tiny ZIP holding only a made-up theme or plugin header.

### 3.6 Try one download (V6)
**Unverified:** these steps test whether the extension can serve a file from the S3 server ([04-A V6](../04-architecture-appendix/A-stack-verification.md)). That's the point of trying them.
1. **(you)** Keep the S3 server running, with `seed` run since its last start.
2. **(you)** In wp-admin, go to **WooCommerce › Orders › Add order**:
   - Customer: yourself;
   - add the item **Aurora (ShelfSync test)**;
   - Status: **Completed**;
   - click **Create**.

   Nothing is charged or sent: the site is on this PC only.
3. **(you)** Open `http://shelfsync-test.test/my-account/downloads/` and click the Aurora download.
4. **(you)** Note the result and tell Claude:
   - **Expected:** `aurora-2.4.1.zip` downloads, and the S3 server's window shows a `GET /shelfsync-test-stack/productrepo/aurora-2.4.1.zip` line with 200.
   - **Anything else:** what the browser shows, and the server window's last lines.

### 3.7 Stop and reset
- **Remove the samples (Claude, or you):** this deletes only the samples, never your own products. It reports anything it kept and why.

```powershell
uv run python -m testenv.laragon seed --reset
```

- **Stop the S3 server (you):** press Ctrl+C in its window. Its files are gone, and the next `seed` puts them back.
- **Stop Laragon (you):** click **Stop** in Laragon.
- **Delete the saved keys (you):** this removes only this site's two pairs from Credential Manager. Delete the two keys in WooCommerce › Settings › Advanced › REST API too.

```powershell
uv run python -m testenv.laragon keys --remove
```

- **Undo the certificate (you):** see the end of §3.2.
