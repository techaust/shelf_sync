# Update ShelfSync, and roll it back

ShelfSync checks GitHub for a newer release by itself. A GitHub token is optional (Settings › Updates). It installs only a release signed with your key ([release.md](release.md)); anything else is refused and nothing changes.

## Update
1. Open ShelfSync, go to **Settings › Updates**.
2. Click **Check now** (or wait for the automatic check). The page says "Version <X.Y.Z> is being downloaded and checked.", then "Version <X.Y.Z> is ready to install."
3. Click **Install <X.Y.Z> and restart**, read the dialog, confirm. ShelfSync closes, switches to the new version and opens again (about a minute). The tab reloads by itself.
4. Settings › Updates says "Updated to <X.Y.Z>."

**If the new version doesn't start**, ShelfSync switches back to the one you had by itself and says "<new> didn't start, so <old> is back." with the reason. Your data is as it was. Tell Claude the reason line.

**If a release is refused** ("…was found but refused: it isn't signed by TecHaust or its files don't match. Nothing was installed."), nothing was installed. That is the app protecting you: tell Claude.

## Roll back
1. **Settings › Updates › Roll back app.**
2. The dialog says one of two things:
   - "Your data stays as it is.": only the program goes back.
   - "The database goes back to how it was on <date>…": the update changed the database, so ShelfSync puts back the copy it took just before the update. Changes since then are lost; a copy of the current data is kept in the backups folder first.
3. Click **Roll back**. ShelfSync closes and opens again on the earlier version: "Rolled back to <X.Y.Z>."

You can install the newer version again from the same page later.
