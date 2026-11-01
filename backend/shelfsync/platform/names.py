"""The app's own Windows names (SYS-04, SYS-05): the Start with Windows Run value and the toast AppUserModelID.

A normal build, a development run and every test use `ShelfSync` and `TecHaust.ShelfSync`, the names the installer
writes. A build made with a suffix (`packaging/build.py --suffix=-rehearsal`, the local rehearsal) writes it into
`build-suffix.txt` next to this file, and its installer (`/DSUFFIX`) suffixes the same two names, so a rehearsal copy
uses `ShelfSync-rehearsal` and `TecHaust.ShelfSync-rehearsal` and never the real ones. The file is plain text, read
once at import; it is data, never code.

A file that is there but can't be read or breaks the suffix rule never falls back to the real names: `BUILD_SUFFIX`,
`RUN_VALUE_NAME` and `AUMID` are then None, so the Run value is left alone (logged by `autostart`) and toasts are sent
with no AUMID (windows-toasts' default).
"""

import os
import re
from pathlib import Path

SUFFIX_FILE_NAME = "build-suffix.txt"
SUFFIX_FILE = Path(__file__).with_name(SUFFIX_FILE_NAME)
# Empty, or `-` then 1 to 32 of these. packaging/build.py and release-build.ps1 check the same rule (a test compares).
SUFFIX_PATTERN = r"-[A-Za-z0-9._-]{1,32}"
_SUFFIX = re.compile(SUFFIX_PATTERN)
_MAX_FILE_BYTES = 64  # the longest valid suffix is 33 characters; anything far past that isn't one

BASE_RUN_VALUE_NAME = "ShelfSync"
BASE_AUMID = "TecHaust.ShelfSync"


def is_valid_suffix(suffix: str) -> bool:
    """The suffix rule: empty, or `-` followed by 1 to 32 of `A-Z a-z 0-9 . _ -`."""
    return suffix == "" or _SUFFIX.fullmatch(suffix) is not None


def read_build_suffix(path: Path = SUFFIX_FILE) -> str | None:
    """`""` when there is no file (a normal build, a development run); the suffix the file holds when it is a valid,
    non-empty one (one trailing line end is allowed); None for anything else: an empty file, a suffix that breaks the
    rule, text that isn't ASCII, or a file that can't be read (a link whose target is missing included)."""
    try:
        with path.open("rb") as handle:
            data = handle.read(_MAX_FILE_BYTES + 1)
    except FileNotFoundError:
        # Something is there (a link whose target is missing) but can't be read: never "" (the real names).
        return None if os.path.lexists(path) else ""
    except OSError:
        return None
    if len(data) > _MAX_FILE_BYTES:
        return None
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return None
    suffix = text.removesuffix("\n").removesuffix("\r")
    return suffix if suffix and is_valid_suffix(suffix) else None


def run_value_name(suffix: str | None) -> str | None:
    """`ShelfSync<suffix>`, or None for a missing or invalid suffix (never the real name)."""
    return None if suffix is None or not is_valid_suffix(suffix) else BASE_RUN_VALUE_NAME + suffix


def aumid_for(suffix: str | None) -> str | None:
    """`TecHaust.ShelfSync<suffix>`, or None for a missing or invalid suffix (never the real AUMID)."""
    return None if suffix is None or not is_valid_suffix(suffix) else BASE_AUMID + suffix


BUILD_SUFFIX = read_build_suffix()
RUN_VALUE_NAME = run_value_name(BUILD_SUFFIX)
AUMID = aumid_for(BUILD_SUFFIX)
