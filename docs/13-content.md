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
| Scan | "Held: threat found (<name>). This ZIP wasn't uploaded and can only be discarded." / "Held: Windows Defender removed or locked this ZIP before it could be checked. It wasn't uploaded and can only be discarded." / "Held: not scanned. Windows Defender couldn't check this ZIP (<reason>). Apply anyway" |
| ERR-07 | Review: "Nothing waiting. ZIPs that need a decision appear here." · Cleanup: "No issues. ShelfSync checks your stores every <sync interval>." · Activity: "No changes yet. Every change ShelfSync makes appears here." · No stores: "Add your first store to start." |

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

**To check at M1b:** Settings › Updates says "Installs in under a minute". That time isn't measured yet; measure it, or drop it.

