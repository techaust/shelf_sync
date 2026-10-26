"""A small migration runner: db/migrations/NNNN_name.sql, applied in order, one transaction each (SYS-07)."""

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from shelfsync.clock import to_iso, utc_now

DEFAULT_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_COMMENTS = re.compile(r"/\*.*?\*/|--[^\n]*", re.DOTALL)  # block comments and line comments


class MigrationError(Exception):
    """A migration could not be applied or the folder is unusable. Start-up stops on this."""


@dataclass(frozen=True)
class Migration:
    version: int
    path: Path


def discover(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[Migration]:
    """The migration files in version order. A badly named file or a repeated number is an error."""
    found: dict[int, Migration] = {}
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _NAME.match(path.name)
        if match is None:
            raise MigrationError(f"Migration file '{path.name}' doesn't match NNNN_name.sql.")
        version = int(match.group(1))
        if version in found:
            raise MigrationError(f"Two migration files share the number {version:04d}.")
        found[version] = Migration(version, path)
    return [found[version] for version in sorted(found)]


def applied_versions(connection: sqlite3.Connection) -> set[int]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migration'"
    ).fetchone()
    if exists is None:
        return set()
    return {row[0] for row in connection.execute("SELECT version FROM schema_migration")}


def _statements(sql: str) -> list[str]:
    """Split a script into complete statements (triggers included), so each runs inside our own transaction.

    sqlite3's executescript() would commit first, which would break the one-transaction-per-migration rule.
    """
    statements: list[str] = []
    current = ""
    for character in sql:
        current += character
        # Test only at a semicolon: sqlite3 knows whether it ends a statement or sits in a string, a comment or a
        # trigger body. This also splits two statements written on one line.
        if character == ";" and sqlite3.complete_statement(current):
            statements.append(current)
            current = ""
    if _COMMENTS.sub("", current).strip():  # anything after the last `;` other than comments is half a statement
        raise MigrationError("The migration ends in the middle of a statement.")
    return statements


def migrate(connection: sqlite3.Connection, migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[int]:
    """Apply every migration not yet recorded; return the versions applied now.

    Each one runs in a single transaction together with its `schema_migration` row. If one fails, it is rolled
    back, the version table is left as it was, and MigrationError stops the start-up. A database that has a
    version this app doesn't know (a newer app wrote it) is refused rather than guessed at.
    """
    migrations = discover(migrations_dir)
    known = {migration.version for migration in migrations}
    done = applied_versions(connection)
    unknown = sorted(done - known)
    if unknown:
        raise MigrationError(
            f"The database has version {unknown[-1]:04d}, which this version of ShelfSync doesn't know. "
            "It was probably written by a newer version."
        )
    applied_now: list[int] = []
    for migration in migrations:
        if migration.version in done:
            continue
        try:
            statements = _statements(migration.path.read_text(encoding="utf-8"))
            connection.execute("BEGIN IMMEDIATE")
            try:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migration (version, applied_at) VALUES (?, ?)",
                    (migration.version, to_iso(utc_now())),
                )
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:  # not after a failed BEGIN, which would hide the real cause
                    connection.execute("ROLLBACK")
                raise
        except (sqlite3.Error, MigrationError, OSError, UnicodeDecodeError) as error:
            raise MigrationError(f"Migration {migration.path.name} failed, nothing of it was kept: {error}") from error
        applied_now.append(migration.version)
    return applied_now
