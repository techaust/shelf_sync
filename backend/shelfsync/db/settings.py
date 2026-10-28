"""Settings stored as JSON in the `setting` table. Defaults live in code, not as rows (04 section 4)."""

import json
import re
import sqlite3
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from shelfsync.ports import DEFAULT_PORT, LAST_PORT

BACKUPS_KEPT_MIN, BACKUPS_KEPT_MAX = 1, 30  # BAK-01: how many daily database backups are kept
SNAPSHOT_DAYS_MIN, SNAPSHOT_DAYS_MAX = 1, 365  # SET-05: how long catalog snapshots are kept (stored now, used in M3)
KEEP_PREVIOUS_MIN, KEEP_PREVIOUS_MAX = 1, 5  # SET-02: previous files kept per slot (PRD: 1; the range is the lead's)
LINK_TEMPLATE_MAX = 200
DEFAULT_LINK_TEMPLATE = '[amazon_s3 object="{key}"]'  # SET-02 (03): what the stores' downloads point at today

DEFAULTS: dict[str, Any] = {
    "port": DEFAULT_PORT,
    "theme": "system",
    "start_with_windows": True,
    "notifications": True,
    "log_retention_days": 30,
    "db_backups_kept": 7,
    "snapshot_retention_days": 30,
    # Storage (SET-02). Empty means not set yet: no default region or bucket is decided, so the Storage Test (M2.7)
    # needs both. An empty endpoint is AWS itself.
    "s3_endpoint": "",
    "s3_region": "",
    "s3_bucket": "",
    "keep_previous_files": 1,
    "download_link_template": DEFAULT_LINK_TEMPLATE,
}

_REGION = re.compile(r"[a-z0-9-]{2,32}")
_BUCKET = re.compile(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")
_DNS_HOST = re.compile(r"(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+")
S3_ENDPOINT_MAX = 200
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")  # the only hosts that may be reached without TLS (the local moto stack)


def check_s3_endpoint(value: str) -> None:
    """`""` is AWS. Otherwise an `https` URL to a named host; `http` (or `https`) only to 127.0.0.1 or localhost.
    No user information, query or fragment, and no path beyond a trailing slash. ValueError for anything else."""
    if value == "":
        return
    bad = ValueError("Setting 's3_endpoint' must be empty or an https address.")
    if len(value) > S3_ENDPOINT_MAX or not value.isascii() or not value.isprintable() or " " in value:
        raise bad
    if "?" in value or "#" in value or "\\" in value or not value.startswith(("https://", "http://")):
        raise bad
    parts = urlsplit(value)
    host = parts.hostname
    if host is None or "@" in parts.netloc or parts.path not in ("", "/"):
        raise bad
    try:
        port = parts.port  # ValueError for a bad port
    except ValueError:
        raise bad from None
    if port is not None and not 1 <= port <= 65535:
        raise bad
    if host in LOOPBACK_HOSTS:
        return
    if (
        parts.scheme != "https"
        or _DNS_HOST.fullmatch(host) is None
        or not any(c.isalpha() for c in host.rsplit(".", 1)[-1])
    ):
        raise bad


def check_s3_region(value: str) -> None:
    if value != "" and _REGION.fullmatch(value) is None:
        raise ValueError("Setting 's3_region' must be empty or 2 to 32 lowercase letters, digits and hyphens.")


def check_s3_bucket(value: str) -> None:
    if value != "" and (_BUCKET.fullmatch(value) is None or ".." in value):
        raise ValueError("Setting 's3_bucket' must be empty or a valid bucket name.")


def check_link_template(value: str) -> None:
    if len(value) > LINK_TEMPLATE_MAX or value.count("{key}") != 1 or not value.isprintable():
        raise ValueError(
            "Setting 'download_link_template' must hold {key} exactly once, on one line, in 200 characters."
        )


def _in_range(key: str, low: int, high: int) -> Callable[[Any], None]:
    def check(value: Any) -> None:
        if not low <= value <= high:
            raise ValueError(f"Setting '{key}' must be between {low} and {high}.")

    return check


# One rule per key beyond its type (the type is always the default's exact type, so True is not accepted for an int
# setting). A key with no entry has no rule beyond its type. The port stays inside 47615-47624, the range the "all in
# use" notice names (M1a.1 re-check).
_VALIDATORS: dict[str, Callable[[Any], None]] = {
    "port": _in_range("port", DEFAULT_PORT, LAST_PORT),
    "db_backups_kept": _in_range("db_backups_kept", BACKUPS_KEPT_MIN, BACKUPS_KEPT_MAX),
    "snapshot_retention_days": _in_range("snapshot_retention_days", SNAPSHOT_DAYS_MIN, SNAPSHOT_DAYS_MAX),
    "s3_endpoint": check_s3_endpoint,
    "s3_region": check_s3_region,
    "s3_bucket": check_s3_bucket,
    "keep_previous_files": _in_range("keep_previous_files", KEEP_PREVIOUS_MIN, KEEP_PREVIOUS_MAX),
    "download_link_template": check_link_template,
}


def _check(key: str, value: Any) -> None:
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting '{key}'.")
    expected = type(DEFAULTS[key])
    if type(value) is not expected:  # exact type, so True is not accepted for an int setting
        raise TypeError(f"Setting '{key}' must be {expected.__name__}, not {type(value).__name__}.")
    rule = _VALIDATORS.get(key)
    if rule is not None:
        rule(value)


def get_setting(connection: sqlite3.Connection, key: str) -> Any:
    """The stored value, or the default if nothing is stored."""
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting '{key}'.")
    row = connection.execute("SELECT value_json FROM setting WHERE key = ?", (key,)).fetchone()
    return DEFAULTS[key] if row is None else json.loads(row[0])


def set_setting(connection: sqlite3.Connection, key: str, value: Any) -> None:
    _check(key, value)
    connection.execute(
        "INSERT INTO setting (key, value_json) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
        (key, json.dumps(value)),
    )


def get_all_settings(connection: sqlite3.Connection) -> dict[str, Any]:
    return {key: get_setting(connection, key) for key in DEFAULTS}
