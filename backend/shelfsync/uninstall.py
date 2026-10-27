"""`python -m shelfsync.uninstall --remove-data` (SYS-08): what the uninstaller runs, from `current\\python.exe`, before
any program file is removed and only when "Remove my data" is ticked.

It takes the single-instance lock for the whole job (and refuses if ShelfSync runs), removes every Credential Manager
entry ShelfSync owns (`platform.secrets.OWNED_SECRET_NAMES`), then the data folder, without following any link or
junction in it (`paths.remove_entry`). It carries on after a failure so one locked file doesn't leave the rest behind,
and reports what is left. The lock file is the last thing removed, after the lock is let go.

Exit codes: 0 everything removed; 1 something couldn't be removed or a data folder that is itself a link was left
alone (the uninstaller says so, names the folder and goes on removing the program); 3 refused (the folder doesn't look
like ShelfSync's data folder, or no data folder is known: nothing was touched); 4 ShelfSync is running (nothing was
touched). Output names entries and folders, never a secret. `--service` names the Credential Manager service (the
default is ShelfSync's own; a throwaway build of the installer passes its own so it never touches the real one).
"""

import argparse
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from shelfsync.paths import DataPaths, remove_entry, resolve_data_paths
from shelfsync.platform.secrets import (
    OWNED_SECRET_NAMES,
    SERVICE_NAME,
    KeyringSecretStore,
    SecretStore,
    SecretStoreError,
)
from shelfsync.tray.instance import InstanceLock, default_instance_lock

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_REFUSED = 3
EXIT_RUNNING = 4

_SERVICE = re.compile(r"ShelfSync[A-Za-z0-9._-]*")


def looks_like_data_folder(root: Path) -> bool:
    """Deny by default: only a folder named like ShelfSync's, or one that holds its database, is ever emptied. A
    SHELFSYNC_DATA_DIR left pointing at the wrong place must never turn "Remove my data" into a wider delete."""
    if root.parent == root or not root.name:  # a drive root
        return False
    return root.name.lower().startswith("shelfsync") or (root / DataPaths(root).database.name).is_file()


def is_link(path: Path) -> bool:
    return path.is_symlink() or os.path.isjunction(path)


def link_target(path: Path) -> str:
    try:
        return os.readlink(path)
    except OSError:
        return "(unknown)"


def remove_secrets(store: SecretStore, names: Sequence[str] = OWNED_SECRET_NAMES) -> list[str]:
    """Delete each owned entry; return the names that couldn't be removed."""
    failed: list[str] = []
    for name in names:
        try:
            store.delete(name)
        except SecretStoreError:
            failed.append(name)
    return failed


def remove_data_folder(root: Path, lock: InstanceLock | None = None, keep: str | None = None) -> list[str]:
    """Remove everything in `root`, then `root`. A link inside is removed itself, never followed. `keep` (the lock
    file's name) is left until the end: `lock` is let go first, then the file and the folder go. Returns the names of
    the entries that couldn't be removed ("." for the folder itself). `root` must not be a link (the caller checks)."""
    if not root.exists():
        if lock is not None:
            lock.release()
        return []
    failed: list[str] = []
    for entry in sorted(root.iterdir()):
        if keep is not None and entry.name == keep:
            continue
        try:
            remove_entry(entry)
        except OSError:
            failed.append(entry.name)
    if lock is not None:
        lock.release()
    if keep is not None and os.path.lexists(root / keep):
        try:
            remove_entry(root / keep)
        except OSError:
            failed.append(keep)
    try:
        root.rmdir()
    except OSError:
        failed.append(".")
    return failed


class UnavailableStore:
    """The store for a `--service` whose Credential Manager couldn't be opened: every delete fails, so every entry is
    reported as not removed. It never falls back to another service (least of all ShelfSync's real one)."""

    def get(self, name: str) -> str | None:
        raise SecretStoreError("Credential Manager is unavailable")

    def set(self, name: str, value: str) -> None:
        raise SecretStoreError("Credential Manager is unavailable")

    def delete(self, name: str) -> None:
        raise SecretStoreError("Credential Manager is unavailable")


def _say(text: str) -> None:
    sys.stdout.write(text + "\n")


def remove_data(paths: DataPaths, store: SecretStore | None = None, lock: InstanceLock | None = None) -> int:
    """The whole job; returns the exit code."""
    if not looks_like_data_folder(paths.root):
        _say(f"Refused: {paths.root} doesn't look like ShelfSync's data folder.")
        return EXIT_REFUSED
    if is_link(paths.root):
        # Checked before the lock: a dangling junction can't hold a lock file, and that must never read as "running".
        _say(f"{paths.root} is a link to {link_target(paths.root)}; it was left alone, and nothing else was removed.")
        return EXIT_INCOMPLETE
    try:
        instance = lock if lock is not None else default_instance_lock(paths)
        free = instance.acquire()
    except OSError:
        free = False  # can't tell: treat it as running, touch nothing
    if not free:
        _say("ShelfSync is running, or its lock couldn't be checked; nothing was removed.")
        return EXIT_RUNNING
    try:
        problems = 0
        try:
            secret_store = store if store is not None else KeyringSecretStore(SERVICE_NAME)
            failed_secrets = remove_secrets(secret_store)
        except SecretStoreError:
            failed_secrets = list(OWNED_SECRET_NAMES)
        for name in failed_secrets:
            _say(f"Couldn't remove the Credential Manager entry {name}.")
            problems += 1
        for name in remove_data_folder(paths.root, instance, paths.instance_lock.name):
            _say(f"Couldn't remove {name} in {paths.root}.")
            problems += 1
        return EXIT_OK if problems == 0 else EXIT_INCOMPLETE
    finally:
        instance.release()  # a second release is harmless


def service_name(text: str) -> str:
    """`--service` must look like ShelfSync's own (or a throwaway variant of it): never another program's service."""
    if _SERVICE.fullmatch(text) is None:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a ShelfSync service name")
    return text


def main(
    argv: Sequence[str] | None = None, *, store: SecretStore | None = None, lock: InstanceLock | None = None
) -> int:
    parser = argparse.ArgumentParser(prog="shelfsync.uninstall", allow_abbrev=False)
    parser.add_argument(
        "--remove-data", action="store_true", required=True, help="remove the data and the stored secrets"
    )
    parser.add_argument("--service", type=service_name, default=SERVICE_NAME, help="Credential Manager service name")
    arguments = parser.parse_args(argv)
    try:
        paths = resolve_data_paths()
    except RuntimeError:
        _say("Refused: the data folder is unknown.")
        return EXIT_REFUSED
    if store is None:
        try:
            store = KeyringSecretStore(arguments.service)
        except SecretStoreError:
            store = UnavailableStore()  # remove_data reports every entry as not removed
    return remove_data(paths, store, lock)


if __name__ == "__main__":
    raise SystemExit(main())
