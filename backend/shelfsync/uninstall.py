"""`python -m shelfsync.uninstall --remove-data` (SYS-08): what the uninstaller runs, from `current\\python.exe`, before
any program file is removed and only when "Remove my data" is ticked.

It removes every Credential Manager entry ShelfSync owns (`platform.secrets.OWNED_SECRET_NAMES`), then the data folder,
without following any link or junction in it (`paths.remove_entry`). It carries on after a failure so one locked file
doesn't leave the rest behind, and reports what is left. Exit codes: 0 everything removed; 1 something couldn't be
removed (the uninstaller says so, names the folder and goes on removing the program); 3 refused (the folder
doesn't look like ShelfSync's data folder, or no data folder is known). Output names entries and folders, never a
secret.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from shelfsync.paths import DataPaths, remove_entry, resolve_data_paths
from shelfsync.platform.secrets import OWNED_SECRET_NAMES, SecretStore, SecretStoreError, default_secret_store

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_REFUSED = 3


def looks_like_data_folder(root: Path) -> bool:
    """Deny by default: only a folder named like ShelfSync's, or one that holds its database, is ever emptied. A
    SHELFSYNC_DATA_DIR left pointing at the wrong place must never turn "Remove my data" into a wider delete."""
    if root.parent == root or not root.name:  # a drive root
        return False
    return root.name.lower().startswith("shelfsync") or (root / DataPaths(root).database.name).is_file()


def remove_secrets(store: SecretStore, names: Sequence[str] = OWNED_SECRET_NAMES) -> list[str]:
    """Delete each owned entry; return the names that couldn't be removed."""
    failed: list[str] = []
    for name in names:
        try:
            store.delete(name)
        except SecretStoreError:
            failed.append(name)
    return failed


def remove_data_folder(root: Path) -> list[str]:
    """Remove everything in `root`, then `root`. A link inside is removed itself, never followed. Returns the names
    of the entries that couldn't be removed ("." for the folder itself)."""
    is_link = root.is_symlink() or os.path.isjunction(root)
    if not root.exists() and not is_link:
        return []
    if is_link:
        remove_entry(root)  # only the link: its target isn't ours
        return []
    failed: list[str] = []
    for entry in sorted(root.iterdir()):
        try:
            remove_entry(entry)
        except OSError:
            failed.append(entry.name)
    try:
        root.rmdir()
    except OSError:
        failed.append(".")
    return failed


def _say(text: str) -> None:
    sys.stdout.write(text + "\n")


def remove_data(paths: DataPaths, store: SecretStore | None = None) -> int:
    """The whole job; returns the exit code."""
    if not looks_like_data_folder(paths.root):
        _say(f"Refused: {paths.root} doesn't look like ShelfSync's data folder.")
        return EXIT_REFUSED
    problems = 0
    try:
        secret_store = store if store is not None else default_secret_store()
        failed_secrets = remove_secrets(secret_store)
    except SecretStoreError:
        failed_secrets = list(OWNED_SECRET_NAMES)
    for name in failed_secrets:
        _say(f"Couldn't remove the Credential Manager entry {name}.")
        problems += 1
    for name in remove_data_folder(paths.root):
        _say(f"Couldn't remove {name} in {paths.root}.")
        problems += 1
    return EXIT_OK if problems == 0 else EXIT_INCOMPLETE


def main(argv: Sequence[str] | None = None, *, store: SecretStore | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shelfsync.uninstall", allow_abbrev=False)
    parser.add_argument(
        "--remove-data", action="store_true", required=True, help="remove the data and the stored secrets"
    )
    parser.parse_args(argv)
    try:
        paths = resolve_data_paths()
    except RuntimeError:
        _say("Refused: the data folder is unknown.")
        return EXIT_REFUSED
    return remove_data(paths, store)


if __name__ == "__main__":
    raise SystemExit(main())
