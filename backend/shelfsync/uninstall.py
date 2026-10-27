"""`python -m shelfsync.uninstall --remove-data` (SYS-08): what the uninstaller runs, from `current\\python.exe`, before
any program file is removed and only when "Remove my data" is ticked.

It takes the single-instance lock for the whole job (and refuses if ShelfSync runs), removes every Credential Manager
entry ShelfSync owns (`platform.secrets.OWNED_SECRET_NAMES`), then the data folder, without following any link or
junction in it (`paths.remove_entry`). It carries on after a failure so one locked file doesn't leave the rest behind,
and reports what is left. The lock file is the last thing removed, after the lock is let go.

Exit codes: 0 everything removed; 1 data was left behind (an entry in the data folder couldn't be removed, or the
data folder is itself a link and was left alone); 5 only a Credential Manager entry couldn't be removed; 6 both
(the uninstaller says so, names the folder and goes on removing the program); 7 the module crashed before it
took the lock (nothing was removed); 8 whether ShelfSync runs couldn't be checked (nothing was removed); a crash
after the lock is held is 6 (both may be left); 3 refused (the folder doesn't look
like ShelfSync's data folder, or no data folder is known: nothing was touched); 4 ShelfSync is running (nothing was
touched). Output names entries and folders, never a secret. `--service` names the Credential Manager service (the
default is ShelfSync's own; a throwaway build of the installer passes its own so it never touches the real one).
"""

import argparse
import contextlib
import os
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from shelfsync.paths import DataPaths, remove_entry, resolve_data_paths
from shelfsync.platform.secrets import (
    OWNED_SECRET_NAMES,
    SERVICE_NAME,
    KeyringSecretStore,
    SecretStore,
    SecretStoreError,
)
from shelfsync.platform.sockets import OwnerLookupError
from shelfsync.tray.instance import InstanceLock, WindowsInstanceLock, default_instance_lock

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_REFUSED = 3
EXIT_RUNNING = 4
EXIT_SECRETS = 5  # only a Credential Manager entry couldn't be removed (the data is gone)
EXIT_BOTH = 6  # data was left behind and an entry couldn't be removed
EXIT_ERROR = 7  # the module crashed BEFORE the lock was taken: nothing was removed
EXIT_CANT_CHECK = 8  # whether ShelfSync runs couldn't be checked (the user's SID couldn't be read): nothing was removed

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
    try:
        entries = sorted(root.iterdir())
    except OSError:
        entries = []
        failed.append(".")  # the folder can't even be listed: nothing in it was removed
    for entry in entries:
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


def remove_data(
    paths: DataPaths,
    store: SecretStore | None = None,
    lock: InstanceLock | None = None,
    session_lock: Callable[[], InstanceLock] = WindowsInstanceLock,
) -> int:
    """The whole job; returns the exit code."""
    if not looks_like_data_folder(paths.root):
        _say(f"Refused: {paths.root} doesn't look like ShelfSync's data folder.")
        return EXIT_REFUSED
    link = is_link(paths.root)
    instance: InstanceLock | None = None
    try:
        if link and not paths.root.exists():
            # A dangling link can't hold a lock file, so the file lock is skipped (that must never read as "running"),
            # but the session mutex is still taken on its own: a running copy holds it.
            instance = session_lock()
        else:
            # A live link takes the lock through it, as a plain folder does.
            instance = lock if lock is not None else default_instance_lock(paths)
        free = instance.acquire()
    except OwnerLookupError:
        # The user's SID (for the mutex name) couldn't be read: can't tell whether ShelfSync runs. Nothing is removed;
        # the uninstaller says so and still removes the program.
        _say("Couldn't check whether ShelfSync is running; nothing was removed.")
        return EXIT_CANT_CHECK
    except OSError:
        free = False  # no lock could be made: treat it as running, touch nothing
    if not free:
        _say("ShelfSync is running, or its lock couldn't be checked; nothing was removed.")
        return EXIT_RUNNING
    try:
        try:
            try:
                secret_store = store if store is not None else KeyringSecretStore(SERVICE_NAME)
                failed_secrets = remove_secrets(secret_store)
            except SecretStoreError:
                failed_secrets = list(OWNED_SECRET_NAMES)
            for name in failed_secrets:
                _say(f"Couldn't remove the Credential Manager entry {name}.")
            data_left = False
            if link:
                _say(f"{paths.root} is a link to {link_target(paths.root)}; the data behind it was left alone.")
                data_left = True
            else:
                for name in remove_data_folder(paths.root, instance, paths.instance_lock.name):
                    _say(f"Couldn't remove {name} in {paths.root}.")
                    data_left = True
            if data_left:
                return EXIT_BOTH if failed_secrets else EXIT_INCOMPLETE
            return EXIT_SECRETS if failed_secrets else EXIT_OK
        except Exception as error:
            # The lock is held, so the removal may have started: never exit 7 ("nothing was removed") from here. Exit 6
            # makes the uninstaller say both that data and the stored token may still be there.
            _say(f"The removal stopped unexpectedly ({type(error).__name__}); some data and the token may be left.")
            return EXIT_BOTH
    finally:
        if instance is not None:
            instance.release()  # a second release is harmless


def service_name(text: str) -> str:
    """`--service` must look like ShelfSync's own (or a throwaway variant of it): never another program's service."""
    if _SERVICE.fullmatch(text) is None:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a ShelfSync service name")
    return text


def main(
    argv: Sequence[str] | None = None, *, store: SecretStore | None = None, lock: InstanceLock | None = None
) -> int:
    for stream in (sys.stdout, sys.stderr):
        # A path or message with characters the console's code page lacks must not crash the report. A stream that
        # can't be reconfigured (None under pythonw, a test harness's capture) is left as it is.
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(prog="shelfsync.uninstall", allow_abbrev=False)
    parser.add_argument(
        "--remove-data", action="store_true", required=True, help="remove the data and the stored secrets"
    )
    parser.add_argument("--service", type=service_name, default=SERVICE_NAME, help="Credential Manager service name")
    arguments = parser.parse_args(argv)
    try:
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

    except Exception as error:  # a crash must not look like "data left behind" (exit 1) to the uninstaller
        _say(f"The removal stopped unexpectedly ({type(error).__name__}); nothing is known to have been removed.")
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
