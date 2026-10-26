"""Owner-facing strings that more than one part uses. Wording is exactly docs/13-content.md (ERR-06 rows)."""

# docs/13 section 3: ERR-06
ERR06_FALLBACK = "Port {preferred} is in use, so ShelfSync started on {port}."
ERR06_ALL_IN_USE = "Ports 47615–47624 are all in use. Close the program using them, then start ShelfSync again."
# docs/13 section 6: ERR-06, second line
ERR06_OLD_ADDRESS = "Open ShelfSync from the tray icon. The old address now reaches the other program."

# Not in docs/13 yet (placeholders for the lead to move into 13): start-up failures.
START_FAILED = "ShelfSync couldn't start. The details are in the log."
START_FAILED_MIGRATION = "ShelfSync couldn't start: {detail}"
