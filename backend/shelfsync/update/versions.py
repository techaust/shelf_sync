"""Version numbers: strict `X.Y.Z` (SYS-06). No leading zeros, no pre-release or build part, compared as integers."""

import re

# fullmatch + ASCII digits only: `\d` would accept other scripts' digits and `$` would accept a trailing newline
_VERSION = re.compile(r"(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})")

Version = tuple[int, int, int]


class VersionError(ValueError):
    """The text isn't a version this updater accepts."""


def parse_version(text: object) -> Version:
    if not isinstance(text, str):
        raise VersionError("a version must be text")
    match = _VERSION.fullmatch(text)
    if match is None:
        raise VersionError("a version must be X.Y.Z with no leading zeros")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_valid_version(text: object) -> bool:
    try:
        parse_version(text)
    except VersionError:
        return False
    return True


def is_newer(candidate: str, installed: str) -> bool:
    """True only if `candidate` is strictly higher than `installed`. The updater never goes down this way."""
    return parse_version(candidate) > parse_version(installed)


def tag_for(version: str) -> str:
    """The release tag for a version: `v` + the version."""
    parse_version(version)
    return f"v{version}"
