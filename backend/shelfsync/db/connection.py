"""SQLite connections: the standard sqlite3 module, no ORM (04 section 2)."""

import sqlite3
from pathlib import Path

# How long a statement waits for another connection's lock before failing with "database is locked".
# 5 s: ShelfSync's writes are short and one user is on it, so a wait this long only happens while a backup or a
# checkpoint runs; it rides that out, yet a real deadlock shows as an error within seconds, not as a frozen screen.
BUSY_TIMEOUT_MS = 5000


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a connection with WAL, foreign keys on and the busy timeout.

    The connection is in autocommit mode (isolation_level=None): transactions are explicit
    (`BEGIN` ... `COMMIT`), which the migration runner relies on. `timeout` sets the busy timeout.
    If a PRAGMA fails (for example the file isn't a database), the connection is closed before the error is raised.
    """
    connection = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
    except BaseException:
        connection.close()
        raise
    return connection
