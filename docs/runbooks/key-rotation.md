# Replace a key (or a lost signing key)

_Button and field names are the app's own (checked against the screens in m2.6)._

Replace a key when it may have been seen by someone else (pasted in chat, shown in a screenshot, on a lost PC), when it expires, or once a year. Make the new one first, put it in ShelfSync, check it works, then revoke the old one.

## A WooCommerce key
1. Make a new key for the `shelfsync` user ([keys-and-policies.md](keys-and-policies.md) A.2–A.3).
2. **ShelfSync › Settings › Stores**, in the store's card: **Replace keys**, paste both, **Save store**, then **Test connection**.
3. In WooCommerce, **Settings › Advanced › REST API**, hover the old `ShelfSync` key (the one with the older "Last access") **› Revoke**.

## An AWS key
1. **IAM › Users ›** `shelfsync-rw` (or `shelfsync-ro`) **› Security credentials › Create access key** (a user can have two at once).
2. **ShelfSync › Settings › Storage › Access keys**, in that pair (**Read and write** or **Read only**): **Replace keys**, paste both, **Save keys**.
3. Back in IAM, on the old key: **Actions › Deactivate**; after a day with no problems, **Delete**.

## The GitHub token (optional)
1. GitHub › **Settings › Developer settings › Fine-grained tokens › Generate new token**: only the `techaust/shelf_sync` repository, **Contents: Read-only**, an expiry date.
2. **ShelfSync › Settings › Updates**, under **GitHub token (read-only)**: **Replace**, paste it, **Save**, then **Check now**.
3. Delete the old token on GitHub. Or remove the token from ShelfSync altogether: updates are checked without one while the project is public.

## The install token (the one this page signs in with)
**ShelfSync › Settings › App › Reset access token.** Every open ShelfSync tab is signed out; open ShelfSync again from the tray icon or the Start menu. Nothing else is needed.

## The release signing key
The private key is only on your PC and your offline copy ([release.md](release.md) A).
- **If it may have been seen** but you still have it: make a new key ([release.md](release.md) A), paste the new public key line to Claude, and publish one more release **signed with the old key** that carries the new public key. Installed copies update to it, and from then on trust only the new key. Then destroy the old `.pem` and its offline copy.
- **If it's lost:** installed copies can't verify any new release (they refuse it, nothing breaks). Make a new key, Claude ships a release with the new public key, and each PC installs that release once **by hand** from its `Setup.exe` ([install-and-first-run.md](install-and-first-run.md)); your data stays.
