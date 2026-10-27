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
| [restore-database.md](restore-database.md) | Restore the database from a daily, pre-migration or pre-rollback backup with the restore command |

Added when their milestone is built ([08](../08-roadmap.md)):

| Runbook | Milestone | What it covers |
|---|---|---|
| `test-stack.md` | M2 | Starting and resetting the LocalWP + moto test stack |
| `calibration.md` | M4 | Running the calibration and reading its report |
| `canary.md` | M6 | The live canary, test download and rollback, step by step |
| `backup-and-new-pc.md` | M7 | Export, import, and moving to a new PC |
