"""The `wizard` table (migration 0003, UI-WIZ): the owner's mark for a step whose state can't be read from the data.
Each row's `state_json` is `{"done": true|false}`; nothing else is stored there (no input, never a key)."""

import json
import sqlite3


def marks(connection: sqlite3.Connection) -> dict[str, bool]:
    """Each marked step and whether it is marked done. A row that doesn't read as `{"done": bool}` counts as not
    done."""
    found: dict[str, bool] = {}
    for step, state_json in connection.execute("SELECT step, state_json FROM wizard"):
        try:
            state = json.loads(state_json)
        except ValueError:
            state = None
        found[step] = isinstance(state, dict) and state.get("done") is True
    return found


def set_mark(connection: sqlite3.Connection, step: str, done: bool) -> None:
    connection.execute(
        "INSERT INTO wizard (step, state_json) VALUES (?, ?) ON CONFLICT (step) DO UPDATE SET state_json = "
        "excluded.state_json",
        (step, json.dumps({"done": done})),
    )
