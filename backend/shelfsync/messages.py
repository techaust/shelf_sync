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

# M1a.4 (proposed wording, not yet in docs/13): a second launch, the log, the data folder
LAUNCH_NO_ANSWER = "ShelfSync is already running but isn't answering. Wait a moment, then open it from the tray icon."
LAUNCH_REFUSED = (
    "ShelfSync didn't open a tab: the program answering on its port isn't your copy of ShelfSync. "
    r"Details are in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log"
)
LAUNCH_NO_SIGN_IN = "ShelfSync is running but couldn't open a signed-in tab. Open it from the tray icon."
LOG_WRITE_FAILED = (
    "ShelfSync can't write to its log file, so some events may be missing from it. "
    r"Check that %LOCALAPPDATA%\ShelfSync\logs isn't locked by another program."
)
START_FAILED_DATA_FOLDER = (
    "ShelfSync couldn't use its data folder, so it didn't start. "
    r"Check that %LOCALAPPDATA%\ShelfSync exists and that you can write to it."
)
SERVER_STOPPED = (
    "ShelfSync stopped unexpectedly. "
    r"The reason is in the log: %LOCALAPPDATA%\ShelfSync\logs\shelfsync.log"
)
