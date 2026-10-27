"""The updater's two small files in the data folder (04 section 8).

`update\\state.json` holds the installed and previous versions, the pending download, the last check, the
pre-migration backup, the token's expiry and the switch intent. `update\\result.json` holds the last switch's outcome,
which `GET /api/updates` reports. Writes are atomic (a temporary file, then `os.replace`). A file that can't be read
or doesn't have the expected shape is set aside under another name and logged, never trusted; a link in its place is
removed unread.
"""

import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from shelfsync.clock import to_iso, utc_now
from shelfsync.paths import is_plain_file, remove_entry
from shelfsync.update.layout import UpdatePaths
from shelfsync.update.versions import is_valid_version

_log = logging.getLogger("shelfsync.update")

STATE_FORMAT = 1
MAX_STATE_BYTES = 256 * 1024


class StateError(Exception):
    """The file has the wrong shape. Never carries the file's content."""


@dataclass(frozen=True)
class BackupRecord:
    """The online backup taken before a migration run: the file, the schema numbers either side, and when."""

    path: str
    from_schema: int
    to_schema: int
    at: str


@dataclass(frozen=True)
class PendingUpdate:
    version: str
    folder: str
    verified_at: str


# What `LastCheck.outcome` may hold: GitHub's outcomes (`github.Outcome`) and the two update outcomes. A stored value
# outside this list is dropped on load, so a damaged file can never make `GET /api/updates` fail.
CHECK_OUTCOMES = frozenset(
    {
        "ok",
        "no_release",
        "token_refused",
        "rate_limited",
        "not_public",
        "unreachable",
        "update_refused",
        "update_failed",
    }
)


@dataclass(frozen=True)
class LastCheck:
    at: str
    outcome: str  # a GitHub outcome (github.Outcome), or `update_refused` / `update_failed`
    detail: str | None = None  # a fixed code naming why, for the two update outcomes


@dataclass(frozen=True)
class SwitchIntent:
    mode: str  # "install" or "rollback"
    from_version: str
    to_version: str
    started_at: str


@dataclass(frozen=True)
class State:
    installed: str | None = None
    previous: str | None = None
    switched_at: str | None = None
    pending: PendingUpdate | None = None
    last_check: LastCheck | None = None
    backup: BackupRecord | None = None
    switch: SwitchIntent | None = None
    token_expires_at: str | None = None


# ---- (de)serialising with checks ------------------------------------------------------------------------------------


def _text(data: dict[str, Any], key: str, *, optional: bool = False) -> str | None:
    value = data.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, str) or len(value) > 1000:
        raise StateError(key)
    return value


def _version(data: dict[str, Any], key: str, *, optional: bool = False) -> str | None:
    value = _text(data, key, optional=optional)
    if value is not None and not is_valid_version(value):
        raise StateError(key)
    return value


def _number(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if type(value) is not int or not 0 <= value <= 100_000:
        raise StateError(key)
    return value


def _section(data: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise StateError(key)
    return value


def _last_check(data: dict[str, Any]) -> LastCheck | None:
    section = _section(data, "last_check")
    if section is None:
        return None
    try:
        outcome = _text(section, "outcome")
        if outcome not in CHECK_OUTCOMES:
            return None
        return LastCheck(str(_text(section, "at")), str(outcome), _text(section, "detail", optional=True))
    except StateError:
        return None  # a bad last check is forgotten; it is only informational


def state_from_json(data: object) -> State:
    if not isinstance(data, dict) or data.get("format") != STATE_FORMAT:
        raise StateError("format")
    pending = _section(data, "pending")
    backup = _section(data, "backup")
    switch = _section(data, "switch")
    mode = _text(switch, "mode") if switch is not None else None
    if switch is not None and mode not in ("install", "rollback"):
        raise StateError("switch")
    return State(
        installed=_version(data, "installed", optional=True),
        previous=_version(data, "previous", optional=True),
        switched_at=_text(data, "switched_at", optional=True),
        pending=(
            PendingUpdate(
                str(_version(pending, "version")), str(_text(pending, "folder")), str(_text(pending, "verified_at"))
            )
            if pending is not None
            else None
        ),
        last_check=_last_check(data),
        backup=(
            BackupRecord(
                str(_text(backup, "path")),
                _number(backup, "from_schema"),
                _number(backup, "to_schema"),
                str(_text(backup, "at")),
            )
            if backup is not None
            else None
        ),
        switch=(
            SwitchIntent(
                str(mode),
                str(_version(switch, "from_version")),
                str(_version(switch, "to_version")),
                str(_text(switch, "started_at")),
            )
            if switch is not None
            else None
        ),
        token_expires_at=_text(data, "token_expires_at", optional=True),
    )


def state_to_json(state: State) -> dict[str, Any]:
    document: dict[str, Any] = {"format": STATE_FORMAT}
    for name in ("installed", "previous", "switched_at", "token_expires_at"):
        document[name] = getattr(state, name)
    for name in ("pending", "last_check", "backup", "switch"):
        value = getattr(state, name)
        document[name] = asdict(value) if value is not None else None
    return document


# ---- files ---------------------------------------------------------------------------------------------------------


def _read_json(path: Path) -> object | None:
    """The parsed file, or None if there is none. A link or a file with several names is removed unread; a file
    that can't be read or parsed is set aside. Both are logged by name only."""
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        _log.warning("The updater file %s can't be read", path.name)
        return None
    if not is_plain_file(path):
        _log.warning("The updater file %s was a link or shared file; it was removed unread", path.name)
        try:
            remove_entry(path)
        except OSError:
            _log.warning("The updater file %s couldn't be removed", path.name)
        return None
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_STATE_BYTES + 1)
        if len(raw) > MAX_STATE_BYTES:
            raise ValueError("too large")
        parsed: object = json.loads(raw.decode("utf-8"))
        return parsed
    except OSError, ValueError:
        _set_aside(path)
        return None


def _set_aside(path: Path) -> None:
    target = path.with_name(f"{path.name}.bad-{to_iso(utc_now()).replace(':', '')}")
    try:
        os.replace(path, target)
        _log.warning("The updater file %s couldn't be read and was set aside", path.name)
    except OSError:
        _log.warning("The updater file %s couldn't be read or set aside", path.name)


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
    os.replace(temporary, path)


class StateStore:
    """`update\\state.json`. Updates are read-modify-write under a lock (one writer at a time: the app, or the
    switch process while the app is stopped)."""

    def __init__(self, paths: UpdatePaths) -> None:
        self._path = paths.state_json
        self._lock = threading.Lock()

    def load(self) -> State:
        data = _read_json(self._path)
        if data is None:
            return State()
        try:
            return state_from_json(data)
        except StateError:
            _set_aside(self._path)
            return State()

    def save(self, state: State) -> None:
        with self._lock:
            _write_json(self._path, state_to_json(state))

    def update(self, change: Callable[[State], State]) -> State:
        with self._lock:
            new = change(self.load())
            _write_json(self._path, state_to_json(new))
            return new


# ---- result.json ---------------------------------------------------------------------------------------------------

RESULT_OUTCOMES = ("updated", "rolled_back", "kept_old", "not_switched", "failed")


@dataclass(frozen=True)
class SwitchResult:
    """What the last switch did. `outcome`: `updated` or `rolled_back` (the target runs), `kept_old` (the target didn't
    start, so the old version is back), `not_switched` (nothing changed), `failed` (neither version started).
    `reason` is a fixed code (see `switch.py`)."""

    mode: str
    from_version: str
    to_version: str
    outcome: str
    reason: str | None
    at: str


class ResultStore:
    def __init__(self, paths: UpdatePaths) -> None:
        self._path = paths.result_json

    def load(self) -> SwitchResult | None:
        data = _read_json(self._path)
        if data is None:
            return None
        try:
            if not isinstance(data, dict) or data.get("format") != STATE_FORMAT:
                raise StateError("format")
            mode = _text(data, "mode")
            outcome = _text(data, "outcome")
            if mode not in ("install", "rollback") or outcome not in RESULT_OUTCOMES:
                raise StateError("result")
            return SwitchResult(
                str(mode),
                str(_version(data, "from_version")),
                str(_version(data, "to_version")),
                str(outcome),
                _text(data, "reason", optional=True),
                str(_text(data, "at")),
            )
        except StateError:
            _set_aside(self._path)
            return None

    def save(self, result: SwitchResult) -> None:
        _write_json(self._path, {"format": STATE_FORMAT, **asdict(result)})
