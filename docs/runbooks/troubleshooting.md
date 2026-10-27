# Troubleshooting

The log is the first place to look: `%LOCALAPPDATA%\ShelfSync\logs\shelfsync.log` (paste that path into the File Explorer address bar). It never holds a secret, so you can send Claude the last lines.

| What you see | What to do |
|---|---|
| Nothing happens when you open ShelfSync | Look for the tray icon (click **^** at the bottom right). If it's there, click it. If not, open ShelfSync from the Start menu again and wait 10 seconds. Still nothing: send Claude the last 30 lines of the log |
| "ShelfSync is already running but isn't answering" | Wait a moment, then open it from the tray icon. If it stays stuck, right-click the tray icon › **Quit**, then open it again |
| "Port 47615 is in use, so ShelfSync started on 47616" | Another program took the port. Open ShelfSync from the tray icon (it knows the new address). Bookmarks to the old address now reach the other program |
| "Ports 47615–47624 are all in use" | Close the program using them (often a development server), then start ShelfSync again |
| "This tab isn't signed in" | Open ShelfSync from the tray icon or the Start menu: it opens a signed-in tab |
| "ShelfSync is missing its screens" | Run the latest `ShelfSync-Setup` again: it repairs the install and keeps your data |
| "ShelfSync couldn't update its database, so it didn't start" | Don't delete anything. Send Claude the last 50 lines of the log |
| Settings › Updates says the token was refused or expired | Make a new fine-grained, read-only GitHub token, or remove the token: updates are checked without one |
| The tray icon is missing after a Windows update | Open ShelfSync from the Start menu |
