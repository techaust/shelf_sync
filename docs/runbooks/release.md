# Make a ShelfSync release (signing offline)

A release is built by GitHub (`release.yml`) and **signed by you on this PC with the offline key**. The app installs an update only if `manifest.json.sig` is a valid Ed25519 signature, by the key built into the app, over the exact `manifest.json` ([06 §6](../06-security.md), [ADR 0002](../adr/0002-embedded-python-nsis.md)). Nobody else, not GitHub and not Claude, can sign.

**Run every command here in Windows PowerShell, outside the Claude app** (press **Windows key**, type `Windows PowerShell`, open it). Each block is one command: paste it, press **Enter**.

## A. Once: make the signing key
1. Pick where the key lives: a folder **outside** `shelf_sync` that only you use (your own credentials folder), plus an offline copy (a USB drive). Losing it means a new key and a new install for every PC (runbook `key-rotation.md`, M2).
2. Go to the repo:
   ```powershell
   cd "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\shelf_sync"
   ```
3. Make the key. Replace `<your folder>` with the folder from step 1 (keep the quotes):
   ```powershell
   $env:UV_PYTHON_DOWNLOADS='never'; $env:PYTHONPATH='backend'; uv run python tools/release/keygen.py "<your folder>\shelfsync-release-key.pem"
   ```
4. Type a passphrase of **at least 16 characters**, twice (nothing shows while you type). Keep it with your passwords: without it the key can't sign.
5. It prints a line of **64 hex characters** (the public key) and the encryption it used. The public key is safe to share: **paste that one line to Claude**. Never paste the passphrase or the `.pem` file.
6. Copy the `.pem` file to the offline drive.

Claude then puts the public key into `backend/shelfsync/update/release_key.py` in a PR (your yes to push and merge). From that merge on, every build can verify updates.

## B. Each release
1. **Claude** sets the version in `pyproject.toml` (and `__version__`) in a PR, and after your yes pushes the tag `v<X.Y.Z>` on `main`.
2. GitHub builds and tests it (about 5 minutes) and makes a **draft** release with `ShelfSync-Setup-<X.Y.Z>.exe`, `shelfsync-<X.Y.Z>-win64.zip` and `manifest.json`. Claude tells you when it's ready.
3. Open https://github.com/techaust/shelf_sync/releases, find the draft **v<X.Y.Z>**, and click **manifest.json** to download it.
4. Make a folder for this release and move the manifest into it:
   ```powershell
   New-Item -ItemType Directory -Force "$env:USERPROFILE\Documents\shelfsync-releases\v<X.Y.Z>"
   ```
   ```powershell
   Move-Item "$env:USERPROFILE\Downloads\manifest.json" "$env:USERPROFILE\Documents\shelfsync-releases\v<X.Y.Z>\"
   ```
5. Sign it (from the repo folder, step A.2):
   ```powershell
   $env:UV_PYTHON_DOWNLOADS='never'; $env:PYTHONPATH='backend'; uv run python tools/release/sign.py "$env:USERPROFILE\Documents\shelfsync-releases\v<X.Y.Z>\manifest.json" "<your folder>\shelfsync-release-key.pem"
   ```
6. It shows the version, tag, **source commit**, build time and the two file hashes. Check the source commit is the one Claude named for the tag. Type `y`, then the passphrase.
7. It writes `manifest.json.sig` next to the manifest. On the draft release page click **Edit** (the pencil), drag `manifest.json.sig` into **Attach binaries**, wait for the upload.
8. Make sure **Set as a pre-release** is **not** ticked (the app ignores pre-releases) and **Set as the latest release** is ticked. Click **Publish release**.

Publishing is public and every installed copy will find it at its next check: publish only what you mean to ship.

## What never to do
- Never put the `.pem` file or the passphrase in the repo, in chat or in a screenshot.
- Never sign a manifest whose source commit you didn't expect. `sign.py` refuses to overwrite an existing signature: delete a wrong `.sig` yourself and sign again.
