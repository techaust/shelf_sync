# Runbooks

Step-by-step procedures written for the owner: click by click, one command per block, full paths.

| Runbook | When |
|---|---|
| [research-scripts.md](research-scripts.md) | Re-count the stores or look up one product (read-only) |

Added when their milestone is built ([08](../08-roadmap.md)):

| Runbook | Milestone | What it covers |
|---|---|---|
| `clean-account.md` | before M1b | Create a second local Windows account for the clean-install test; check the Smart App Control state (Windows Security → App & browser control) without changing it |
| `install-and-first-run.md` | M1b | Verifying the `Setup.exe` hash ([06 §6](../06-security.md)), installing it, the SmartScreen "Run anyway" click, the wizard |
| `release.md` | M1b | Making a release: CI build, signing the manifest with the offline key, uploading the signature (owner's yes), the pre-release calibration check |
| `update-and-rollback.md` | M1b | Installing an update in the app; "Roll back app"; what an automatic switch-back looks like |
| `uninstall.md` | M1b | Uninstalling, and keeping or removing the data |
| `troubleshooting.md` | M1b, grows | "ShelfSync won't open", port in use, the tray icon missing, reading the logs |
| `key-rotation.md` | M2 | Rotating the WooCommerce keys, both S3 keys, the GitHub token and the install token; what to do if the signing key is lost |
| `keys-and-policies.md` | M2 | Creating the Shop Manager key and the two IAM policies |
| `test-stack.md` | M2 | Starting and resetting the LocalWP + moto test stack |
| `restore-database.md` | M2 | Restoring the database from a daily backup |
| `calibration.md` | M4 | Running the calibration and reading its report |
| `canary.md` | M6 | The live canary, test download and rollback, step by step |
| `backup-and-new-pc.md` | M7 | Export, import, and moving to a new PC |
