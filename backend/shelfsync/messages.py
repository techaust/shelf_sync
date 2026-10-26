"""Owner-facing strings that more than one part uses. Wording is exactly docs/13-content.md (ERR-06 rows)."""

# docs/13 section 3: ERR-06
ERR06_FALLBACK = "Port {preferred} is in use, so ShelfSync started on {port}."
ERR06_ALL_IN_USE = "Ports 47615–47624 are all in use. Close the program using them, then start ShelfSync again."
# docs/13 section 6: ERR-06, second line
ERR06_OLD_ADDRESS = "Open ShelfSync from the tray icon. The old address now reaches the other program."

# docs/13 section 3: Start-up
START_FAILED = r"ShelfSync couldn't start. The reason is in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log"
START_FAILED_MIGRATION = (
    "ShelfSync couldn't update its database, so it didn't start. "
    r"The reason is in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log"
)
