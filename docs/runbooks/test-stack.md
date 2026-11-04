# The test stack: moto S3 server, and Laragon (later)

The test stack is where every write is proven before it reaches a real store ([07 §5](../07-testing.md), [04 §10](../04-architecture.md)): a Laragon site with WooCommerce and your Amazon S3 Storage extension, whose "User defined" endpoint points at **moto server**, a local stand-in for Amazon S3 ($0). This page covers the moto half today; the Laragon half is added in m2.8 (last section).

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

To be written in m2.8. What it will cover: making the Laragon site (`https://<site>.test`) with WordPress and WooCommerce, activating your Amazon S3 Storage extension on it (your licence allows it on the local test site, [11](../11-decisions.md) 2026-10-25; that row named LocalWP, so it's confirmed for Laragon before m2.8 activates it), setting its "User defined" provider to the endpoint, region, bucket and made-up keys above (04-A V6), and the one script that adds sample products.

**Decided 2026-11-05** ([11](../11-decisions.md), [runs/m2.0-plan.md](../runs/m2.0-plan.md) §3 Q3): the test site runs in **Laragon** (already installed at `C:\laragon`; its free tier is for non-commercial use only, and you made the call on its terms). ShelfSync signs in with Basic auth over Laragon's own HTTPS, and only the test harness is given Laragon's certificate file (`C:\laragon\etc\ssl\laragon.crt`): the app gets no new setting or package. Whether Python 3.15 accepts that certificate for a `.test` address is checked first in m2.8 (04-A V57).
