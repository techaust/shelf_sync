# 13: Content (wording in the app)

| | |
|---|---|
| **Phase** | 2, Project documentation (**approved by the owner 2026-10-25**). Added 2026-10-25 after the independent review (TecHaust keeps its wording in `07-content.md`; ShelfSync numbers it 13) |
| **Date** | 2026-10-25 |
| **Used by** | The `designer` for every screen, toast and dialog; the `reviewer` checks wording against it |

## 1. Voice
- **Plain, calm, exact.** The owner reads this mid-task: say what happened, why, and what to do next.
- **Sentence case** everywhere (buttons too): "Approve and apply", not "Approve And Apply".
- **Name things the same way every time:** product, slot, store, ZIP, file, Review, Cleanup, Activity, held, partial.
- **Numbers and names are exact:** "Creote 4.3.0 → 3.0.4" is shown as two versions with an arrow icon, never "an older version".
- **Who did it** is always said: "you", "auto-rule", or "outside ShelfSync".
- **Banned:** "Oops", "Something went wrong", "Please try again later" with no reason, exclamation marks in errors, "AI", "magic", "smart" as a claim, "seamless", "simply", "just" (as in "just click").

## 2. Patterns
| Element | Pattern | Example |
|---|---|---|
| Button | Verb + object | "Approve and apply", "Link all 3", "Roll back to 4.61.0" |
| Held reason | "Held: <reason>." + one line why | "Held: downgrade. Your stores have 4.3.0; this ZIP is 3.0.4." |
| Confirmation | What will change, where, and whether it can be undone | "This points both stores back to jupiterx-4.61.0.zip. You can roll forward again from History." |
| Skipped delete | "Kept <file>:" + who still uses it | "Kept jupiterx-4.60.0.zip: PluginWay (paused) still offers it." |
| Over a limit | "Can't open <file>: <limit> is over the limit (<value>)." + what to do | "Can't open bigpack.zip: the unpacked size is over the 2 GB limit (2.6 GB). Nothing was uploaded." |
| Retention skipped | "Kept old files this time:" + why | "Kept old files this time: PluginWay couldn't be read (HTTP 524). Nothing was deleted." |
| Not ShelfSync's file | What it is + the Cleanup action | "udesign.zip wasn't uploaded by ShelfSync, so it's never deleted automatically. Delete it in Cleanup if you're sure." |
| Blocked by a missing file | "Can't <action>: <file> is no longer in S3." + one action | "Can't roll back: jupiterx-4.60.0.zip is no longer in S3. Set file manually" |
| Error | What failed + why (from the source) + one action | "PluginWay didn't respond (HTTP 524, Cloudflare timeout). Nothing was changed there. Retry PluginWay" |
| Empty state | What will appear + the next action | "Nothing waiting. ZIPs that need a decision appear here." |
| "Why?" | One line per signal, with points | "+40 Folder slug matches the product's URL slug (jupiterx)" |

## 3. Error and empty-state wording (PRD §7)
| ID | Wording |
|---|---|
| ERR-01 | "<Store> can't be reached: <reason>. Updates for it are waiting. Test connection" |
| ERR-02 | "<Store> returned no downloadable products." / "<Store> runs WooCommerce <v>. ShelfSync needs 5.8 or newer." |
| ERR-03 | "S3 refused access: <AWS reason>. Uploads are held. Open Storage settings" |
| ERR-04 | "Only <n> GB free on <drive>. New uploads are paused until there's at least 2 GB." |
| ERR-05 | "Resumed after a restart: <file> continues from <step>." |
| ERR-06 | "Port 47615 is in use, so ShelfSync started on <port>." / "Ports 47615–47624 are all in use. Close the program using them, then start ShelfSync again." |
| Start-up | "ShelfSync couldn't start. The reason is in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log" / "ShelfSync couldn't update its database, so it didn't start. The reason is in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log" (a notification; the log holds the technical detail) |
| Signed out | A tab without a valid sign-in: "This tab isn't signed in. Open ShelfSync from the tray icon or the Start menu." |
| Sign-in problems | No answer: "ShelfSync didn't answer, so this tab can't sign in." + "Open ShelfSync from the tray icon or the Start menu." + "Try again" (hidden after a ticket sign-in) · Refused: "ShelfSync refused to sign this tab in (HTTP <status>)." + the same line |
| Unknown address | Title "Not found", "There's no screen at this address.", button "Open Dashboard" |
| Launcher (M1a.4) | Not answering: "ShelfSync is already running but isn't answering. Wait a moment, then open it from the tray icon." · Not your copy: "ShelfSync didn't open a tab: the program answering on its port isn't your copy of ShelfSync. Details are in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log" · No tab: "ShelfSync is running but couldn't open a signed-in tab. Open it from the tray icon." |
| Running problems (M1a.4) | Log: "ShelfSync can't write to its log file, so some events may be missing from it. Check that %LOCALAPPDATA%\ShelfSync\logs isn't locked by another program." · Data folder: "ShelfSync couldn't use its data folder, so it didn't start. Check that %LOCALAPPDATA%\ShelfSync exists and that you can write to it." · Stopped: "ShelfSync stopped unexpectedly. The reason is in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log" |
| Start-up, screens missing (M1b.1, proposed) | "ShelfSync is missing its screens, so it didn't start. Run the ShelfSync installer again to repair it. Details are in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log" |
| Installer (M1b.1, proposed) | Running: "ShelfSync is running. Quit it from its tray icon, then run this installer again." · Older Setup: "This installer is ShelfSync <version>, but a newer ShelfSync is already installed. Installing an older version could damage your data, so the installer stopped. Download the newest installer, or uninstall ShelfSync first." · Switch failed: "The installer couldn't switch ShelfSync to the new version. The version you had installed was left as it was. Close any window showing the ShelfSync folder and run the installer again." · No working version: "The installer couldn't finish switching ShelfSync to the new version, so it has no working version right now. Run the installer again to finish the install." · Stuck file: "The installer couldn't remove a file or link in its program folder. Close any window that's using it, then run the installer again. This is what couldn't be removed:" + the path · Finish page checkbox: "Open ShelfSync" |
| Uninstaller (M1b.1, proposed) | Running: "ShelfSync is running. Quit it from its tray icon, then run the uninstaller again." · Stuck file: "The uninstaller couldn't remove a file or link in its program folder. Close any window that's using it, then run the uninstaller again. This is what couldn't be removed:" + the path · Page title "Remove my data", text "ShelfSync keeps your database, backups and logs, and the sign-in token it stored for you, even after it is removed, so a later install picks up where you left off.", checkbox (off by default) "Remove my data too (the database, backups, logs and the stored token). This can't be undone." |
| Remove my data results (M1b.1, proposed; one per uninstall exit code) | Data left (1): "ShelfSync couldn't remove all of your data. Whatever it couldn't remove, including anything a link in the data folder points to, was left in place. Delete what is left yourself if you want it gone; this is the data folder:" + the folder · Token left (5): "ShelfSync couldn't remove its stored sign-in token from Windows Credential Manager, so it may still be stored there. You can delete the ShelfSync entry under Windows Credentials in Credential Manager." · Both (6): both notices · Not ShelfSync's folder (3): "ShelfSync left this folder alone because it doesn't look like ShelfSync's own data folder:" + the folder · Can't check (8): "ShelfSync couldn't check whether it is running, so it didn't remove your data or the stored sign-in token. Run the installer again, then uninstall again with Remove my data ticked. The program is being removed now." · Nothing removed (2, 7, no Python, error): "ShelfSync couldn't remove your data, so nothing was removed: your data and the stored sign-in token are still there. Run the installer again, then uninstall again with Remove my data ticked. The program is being removed now." |
| Settings › Updates (M1b.2, proposed) | Development copy: "This copy of ShelfSync runs from source, so updates are turned off." · No key in the build: "This build can't verify updates, so it won't install any." · Empty state (the token is optional): "ShelfSync checks for updates by itself. A GitHub token is optional: add one only if GitHub refuses the check or the project is private." · "ShelfSync <v> is up to date." · "Version <v> is being downloaded and checked." · "Version <v> is ready to install." · Buttons "Check now", "Install <v> and restart", "Roll back app" · Install dialog: "ShelfSync will close and open again. This takes about a minute." · Roll back, files only: "Roll back to <v>? ShelfSync will close and open again. Your data stays as it is." · Roll back with a database change: "Roll back to <v>? The database goes back to how it was on <date>, so changes made since the update are lost. A copy of the current data is kept in the backups folder." Buttons "Roll back" and "Cancel" · Token: "Token saved." / "That isn't a fine-grained GitHub token (it starts with github_pat_)." / "Your GitHub token expires on <date>. Make a new one before then." / "Token removed." |
| Update check results (M1b.2, proposed; `last_check.outcome`) | `ok` "Checked <date>." · `no_release` "No release has been published yet." · `token_refused` "GitHub refused the token. Check it, or remove it to check without one." · `rate_limited` "GitHub says there were too many checks. Try again later." · `not_public` "GitHub can't find the project. If it is private, add a read-only token." · `unreachable` "Couldn't reach GitHub. Check your connection." · `update_refused` "Version <v> was found but refused: it isn't signed by TecHaust or its files don't match. Nothing was installed." · `update_failed` "Version <v> couldn't be downloaded. It will be tried again at the next check." · detail `no_space` "There isn't enough free space on the drive ShelfSync is installed on." |
| Last switch (M1b.2, proposed; `last_result`) | `updated` "Updated to <v>." · `rolled_back` "Rolled back to <v>." · `kept_old` "<new> didn't start, so <old> is back." + `no_answer` "It didn't answer in time." / `wrong_version` "It reported the wrong version." / `untrusted_listener` "Something else was answering on ShelfSync's address." / `exited` "It stopped while starting." / `migration_failed` "Its database update failed and was undone." · `not_switched` "Nothing was changed." + `old_copy_still_running` "ShelfSync didn't close in time." / `old_process_mismatch` "The program that was running wasn't this version of ShelfSync." / `lock_busy` "Another copy of ShelfSync was starting." / `files_changed` "The files of <v> no longer match what was signed." / `manifest_missing` and `manifest_invalid` "The signature of <v> can't be checked." / `backup_failed` "A copy of the current data couldn't be made, so the roll back was refused." / `backup_missing` and `backup_mismatch` "The backup needed to roll back isn't there." / `database_changed` "The database changed since you confirmed. Try again." · `failed` "Neither version started. Open ShelfSync from the Start menu; the log has the reason." |
| Updates API errors (M1b.2, proposed; `{"error": "<code>"}`) | 409 `development_build` "Updates are turned off in this copy." · `busy` "An update is already under way." · `no_key` "This build can't verify updates." · `nothing_to_install` "There's no downloaded update to install." · `no_previous` "There's no earlier version to roll back to." · `no_backup` "The backup needed to roll back isn't there, so the roll back was refused." · `files_changed` "The files of that version changed on disk, so it was refused." · `manifest_invalid` and `manifest_missing` "That version's signature can't be checked, so it was refused." · `cannot_restart` "ShelfSync couldn't close itself to restart, so nothing was changed." · 429 `too_soon` "A check ran a moment ago. Try again in a minute." · 422 `confirm_required` (the roll back dialog) |
| Shell (M1a.3) | Pause everything tooltip until M5: "Nothing runs yet, so there's nothing to pause." · Health, nothing connected: "No stores or storage yet" · Status strip before the first sync: "Last sync not yet" · Theme button: "Theme: <Same as Windows / Light / Dark>" · Tab title "<Screen>, ShelfSync" |
| Scan | "Held: threat found (<name>). This ZIP wasn't uploaded and can only be discarded." / "Held: Windows Defender removed or locked this ZIP before it could be checked. It wasn't uploaded and can only be discarded." / "Held: not scanned. Windows Defender couldn't check this ZIP (<reason>). Apply anyway" |
| ERR-07 | Review: "Nothing waiting. ZIPs that need a decision appear here." · Cleanup: "No issues. ShelfSync checks your stores every <sync interval>." · Activity: "Nothing changed yet. Every change ShelfSync makes to a store or S3 appears here." (the approved mockup's text) · No stores: "Add your first store to start." |

## 4. Notifications (toasts)
| When | Title | Detail | Action |
|---|---|---|---|
| Review needs the owner | "3 ZIPs need you" | "1 downgrade · 2 first-time matches" | Open Review |
| A job went partial | "PluginWay didn't update" | "XStore 9.7.11 · HTTP 524 · nothing deleted" | Open Activity |
| Brake triggered | "Auto-apply paused" | "<brake limit> updates in 10 minutes. Check, then resume." | Open Dashboard |
| Update ready | "ShelfSync 1.2.0 is ready" | "Installs in under a minute; your data stays." | Open Updates |

## 5. Glossary
Shown in the help panel and linked from [03](03-prd.md).

| Word | Meaning |
|---|---|
| **Slug** | The short, web-address form of a name, e.g. `jupiterx` |
| **Canonical slug** | The one slug ShelfSync uses for a product across all stores, and for its file names; it starts as the shared URL slug and you can edit it |
| **Twin** | The same product on another store, linked by its slug |
| **Slot** | One download button on a product (most have one, "Download") |
| **Fingerprint** | What a matching ZIP looks like inside (folder, header name, author) |
| **Band** | How sure the match is: Certain, Likely, Unsure, No match |
| **Held** | Waiting in Review because a safety rule stopped it |
| **Partial** | Updated on some stores but not all; nothing was deleted |
| **Change plan** | The exact list of what will change, shown before anything changes |
| **MD5** | A fingerprint of a file's bytes, used to check an upload arrived intact |
| **Range read** | Reading only part of a file in S3, so the whole ZIP isn't downloaded |
| **`modified_after`** | Asking a store for only the products changed since a time |
| **SSE** | How the page gets live progress from ShelfSync without refreshing |
| **WAL** | The SQLite setting that keeps the database safe when the app stops suddenly |
| **ETag** | A value S3 returns for a file; not used as proof of content |
| **Trust ramp** | The first 50 Certain ZIPs, which wait for your approval before auto-apply is allowed |

## 6. Screen wording from the P3.4 mockup (approved 2026-10-26)
The approved mockup (`docs/05-design-system-appendix/mockup/`, in `js/app.js`, `js/screens-b.js`, `js/overlays.js` and `js/data*.js`) holds the full wording of every screen. The `reviewer` checked it against this document over three rounds. **Until M1 moves it into the app, the mockup is the source for screen wording.** The designer's lists in [runs/p3.4-mockups.md](runs/p3.4-mockups.md) §4 are a record of what was added, not the final text. Where a list and the mockup differ, the mockup wins.

The strings tied to owner decisions ([11](11-decisions.md), 2026-10-26), as they now read:

| Where | Wording |
|---|---|
| Settings › App, Reset access token | "Every open ShelfSync tab is signed out. Open ShelfSync again from the tray icon or the Start menu." |
| Storage Test, and the wizard's Test step | "ShelfSync writes a tiny test file under `shelfsync-test/` with the read and write key, reads it back with the read-only key, then deletes it: about 4 small S3 requests, a tiny AWS charge." |
| Roll back app, database unchanged | "<version> didn't change the database, so your data stays as it is. You can install <version> again from Settings › Updates." |
| Roll back app, database changed | "<version> changed the database. ShelfSync restores the backup taken just before the update, on <date>. Changes made since then are lost and can't be brought back. You can install <version> again from Settings › Updates." |
| ERR-06, second line | "Open ShelfSync from the tray icon. The old address now reaches the other program." |
| Status strip, brake tripped | "Auto-apply paused" (tooltip: the reason). Rules: "Auto-apply paused: more than 30 updates in 10 minutes." + "Check the latest updates in Activity, then resume." |
| Status strip, trust ramp | "Auto-apply off" (tooltip: "Auto-apply stays off until the trust ramp reaches 50.") |
| Wizard, Teach step | "About 2,400 small S3 read requests. AWS charges a tiny amount for them." Buttons: "Teach and finish" (primary), "Skip for now" |
| Teaching progress | Strip: "Teaching 412 / 2,398", or "Teaching waits while paused". Dashboard: "Teaching from current files", then "Teaching finished" |
| Times | "Times in <zone's long name>", e.g. "Times in India Standard Time" |

**To check at M1b:** Settings › Updates says "Installs in under a minute". That time isn't measured yet; measure it, or drop it. _(Lead (proposed), 2026-10-28: dropped from the screen in m1b.4; the install dialog says "This takes about a minute." until the M1b exit test measures it.)_

