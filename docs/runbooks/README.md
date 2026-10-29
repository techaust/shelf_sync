# Runbooks

Step-by-step procedures written for the owner: click by click, one command per block, full paths.

| Runbook | When |
|---|---|
| [research-scripts.md](research-scripts.md) | Re-count the stores or look up one product (read-only) |
| [m1b-exit-test.md](m1b-exit-test.md) | The M1b exit test, step by step, with who does what |
| [clean-account.md](clean-account.md) | Make the second local Windows account for the clean-install test; read (never change) the Defender, Smart App Control and SmartScreen states |
| [release.md](release.md) | Make the signing key once; sign and publish each release (the pre-release calibration check joins it at M4) |
| [install-and-first-run.md](install-and-first-run.md) | Check the `Setup.exe` hash ([06 §6](../06-security.md)), install it, the SmartScreen "Run anyway" click, the first run (the wizard joins it at M3) |
| [update-and-rollback.md](update-and-rollback.md) | Install an update in the app; "Roll back app"; what an automatic switch-back looks like |
| [uninstall.md](uninstall.md) | Uninstall, keep or remove the data, and check nothing is left |
| [troubleshooting.md](troubleshooting.md) | "ShelfSync won't open", port in use, the tray icon missing, reading the logs (grows) |
| [keys-and-policies.md](keys-and-policies.md) | Make the Shop Manager key for each store and the two AWS keys with their policies; record the bucket's versioning and encryption |
| [key-rotation.md](key-rotation.md) | Replace a WooCommerce key, an AWS key, the GitHub token, the install token; what to do if the signing key is seen or lost |
| [cloud-sessions.md](cloud-sessions.md) | Set up the ShelfSync cloud environment once; start a cloud session; what may and may not run there |
| [restore-database.md](restore-database.md) | Restore the database from a daily, pre-migration or pre-rollback backup with the restore command |

## What the Settings pages do (M2)
Wording as on screen ([13](../13-content.md)). Every key is kept in Windows Credential Manager and is never shown again or sent to the page.

**Settings › Stores.** One card per store: its name, address, main button name, identifier (shape, colour and two-letter code), time between requests, and its Shop Manager key.
- **Add a store**, then **Add store**; **Save store** for a change; **Replace keys** for a new key ([keys-and-policies.md](keys-and-policies.md) A, [key-rotation.md](key-rotation.md)).
- **Test connection** only reads: it shows the time, the WooCommerce version and how many downloadable products there are.
- **Pause store** keeps a store's updates waiting until **Resume store**. **Remove** stops ShelfSync updating it and deletes its keys from Credential Manager at once; nothing on the store itself changes.
- The bar at the top of every screen has a chip per store. When a store can't be reached, its chip and its card say "<Store> can't be reached." with the reason; the chip's panel can run the test again.

**Settings › Storage.** The S3 bucket ShelfSync uploads to.
- **Add storage**, then **Endpoint** (empty for Amazon S3), **Region**, **Bucket**, **Previous files to keep** (1 to 5 per slot, kept for rollback) and **Download link template** (`{key}` becomes the file name); **Save storage**.
- **Access keys:** a **Read and write** pair (uploads and deletes) and a **Read only** pair (reads files back to check them). **Replace keys**, then **Save keys**; **Remove keys** deletes a pair ([keys-and-policies.md](keys-and-policies.md) B).
- **S3 access policy guide** gives both IAM policies with your bucket filled in. Testing the bucket arrives with the S3 update (m2.7); until then settings and keys are saved without a test.

**Settings › Backup.**
- **What's kept:** the last and next daily database backup (02:00 local time) and how many are kept now. **Database backups to keep** (1 to 30) and **Keep snapshots for** (1 to 365 days, used from a later version); **Save backup settings**.
- **How to restore a backup** opens the restore guide: restoring is a command, not a button ([restore-database.md](restore-database.md)).
- **Export settings** saves a `.ssbak` file of your settings and stores. With **Include secrets (needs a passphrase)** it also holds the keys, locked with a passphrase of at least 12 characters that ShelfSync can't recover.
- **Import from file…** is for a new install or a new PC: it works only on a ShelfSync with no stores yet. Restart ShelfSync afterwards when it says so. Moving to a new PC step by step: `backup-and-new-pc.md` (M7).

Added when their milestone is built ([08](../08-roadmap.md)):

| Runbook | Milestone | What it covers |
|---|---|---|
| `test-stack.md` | M2 | Starting and resetting the LocalWP + moto test stack |
| `calibration.md` | M4 | Running the calibration and reading its report |
| `canary.md` | M6 | The live canary, test download and rollback, step by step |
| `backup-and-new-pc.md` | M7 | Export, import, and moving to a new PC |
