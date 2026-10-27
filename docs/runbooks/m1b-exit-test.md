# M1b exit test (the owner's)

The test from [08](../08-roadmap.md): ShelfSync **installs on the second clean account with Defender on** (Smart App Control state recorded), **updates itself from a signed test release and refuses a tampered one**, and **uninstall leaves no program folder**. Everything here runs outside the Claude app. Claude does the steps marked **Claude** after your yes in chat.

The test releases are public on GitHub (the repo is public). v0.1.2 is a deliberately broken release: you delete it at the end.

| # | Who | Step | Pass when |
|---|---|---|---|
| 1 | You | Make the clean account and record the protection states ([clean-account.md](clean-account.md)) | Defender's real-time protection is On; the states are sent to Claude |
| 2 | You | Make the signing key ([release.md](release.md) A) and paste the **public** key line to Claude | 64 hex characters in chat; the `.pem` and an offline copy exist |
| 3 | Claude | PR: the public key in `release_key.py`; merge on green | merged |
| 4 | Claude | Tag `v0.1.0` | GitHub makes the draft |
| 5 | You | Sign and publish v0.1.0 ([release.md](release.md) B.3–8) | published as the latest release |
| 6 | You, **clean account** | Download, check the hash, install ([install-and-first-run.md](install-and-first-run.md)) | ShelfSync opens signed in; note any SmartScreen or Smart App Control message |
| 7 | Claude | PR: version 0.1.1; merge; tag `v0.1.1` | GitHub makes the draft |
| 8 | You | Sign and publish v0.1.1 | published |
| 9 | You, clean account | **Settings › Updates › Check now**, then **Install 0.1.1 and restart** ([update-and-rollback.md](update-and-rollback.md)) | "Updated to 0.1.1." |
| 10 | You, clean account | **Roll back app** | "Rolled back to 0.1.0." Then install 0.1.1 again: "Updated to 0.1.1." |
| 11 | Claude | PR: version 0.1.2; merge; tag `v0.1.2` | GitHub makes the draft |
| 12 | You | **Tamper on purpose:** don't sign v0.1.2. Attach **v0.1.1's** `manifest.json.sig` (from `Documents\shelfsync-releases\v0.1.1\`) to the v0.1.2 draft, then publish it | published with a signature that belongs to another manifest |
| 13 | You, clean account | **Check now** | "Version 0.1.2 was found but refused: it isn't signed by TecHaust or its files don't match. Nothing was installed." ShelfSync stays on 0.1.1 |
| 14 | You, clean account | Uninstall with **Remove my data** ticked ([uninstall.md](uninstall.md)), then the three checks there | `False`, "unable to find", `False` |
| 15 | You | On GitHub, open the v0.1.2 release › **Delete** (it's broken on purpose). Keep v0.1.0 and v0.1.1 | v0.1.2 gone |
| 16 | You, own account | The Windows checks, outside Claude (below) | all pass |
| 17 | You | Send Claude: the states from step 1, any warning text from step 6, the result of each step, and "approved" if M1b passes | M1b closed in [08](../08-roadmap.md) |

## Step 16: the Windows checks
In Windows PowerShell on your own account:
```powershell
cd "D:\BUSINESS\3. CHILD PROJECTS\1. GPL PROJECTS\OTHER ASSETS\SOFTWARE\shelf_sync"
```
```powershell
$env:UV_PYTHON_DOWNLOADS='never'; uv run pytest -m windows --no-cov 2>&1 | Tee-Object .logs\windows-checks.log
```
The last line must say **passed** with no **failed**. Tell Claude; it reads `.logs\windows-checks.log`.

Also, once, the uninstall entry of the copy on **your own** account, if you installed one (Claude can't see the real registry from inside the app, 04-A V42):
```powershell
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\ShelfSync"
```
Send Claude what it prints (it holds no secret).
