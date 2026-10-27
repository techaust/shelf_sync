"""Directory links for the `current` junction (04 section 8, 04-A V39).

A directory junction needs no admin right (`cmd /c mklink /J`). The switch makes `current.next`, renames `current` to
`current.old`, renames `current.next` to `current` and removes the `current.old` link: no single step moves the
junction atomically. Every switcher run begins by repairing a `current` that an earlier, killed switcher left missing
(`update/switch.py`), and Setup.exe does the same; the app's own start only clears leftovers.

`remove` removes the link itself and refuses anything that isn't a link, so it can never delete a version folder.
`SymlinkLinks` is the stand-in for systems without junctions (the Linux CI, developers on other systems).
"""

import os
import subprocess  # nosec B404  # one fixed program, cmd.exe, with a list of arguments and no shell
import sys
from pathlib import Path
from typing import Protocol

# cmd.exe by its full path under the Windows folder, so nothing earlier on PATH can stand in for it
_CMD = str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "cmd.exe")
_MKLINK_TIMEOUT_SECONDS = 15
# cmd.exe reads these as syntax even when a path is quoted in some cases, so a path holding one is refused outright
_UNSAFE_FOR_CMD = frozenset('"%&^|<>!\r\n\x00')


class LinkError(Exception):
    """A link couldn't be made, renamed or removed. The message names the step, never a path's content."""


class DirectoryLinks(Protocol):
    def create(self, link: Path, target: Path) -> None:
        """Make `link` point at the existing folder `target`. `link` must not exist."""
        ...

    def exists(self, path: Path) -> bool:
        """True if something is at `path`, a link whose target is gone included."""
        ...

    def target(self, link: Path) -> Path | None:
        """Where the link points, or None if `path` isn't a link."""
        ...

    def rename(self, source: Path, destination: Path) -> None:
        """Rename a link. `destination` must not exist."""
        ...

    def remove(self, link: Path) -> None:
        """Remove the link itself, never its target. Refuses anything that isn't a link."""
        ...


def _is_link(path: Path) -> bool:
    return os.path.islink(path) or os.path.isjunction(path)


def _strip_extended_prefix(text: str) -> str:
    return text[4:] if text.startswith("\\\\?\\") and not text.startswith("\\\\?\\UNC\\") else text


class WindowsJunctions:
    def create(self, link: Path, target: Path) -> None:
        if sys.platform != "win32":
            raise LinkError("Junctions are available on Windows only")
        if any(ch in _UNSAFE_FOR_CMD for ch in f"{link}{target}"):
            raise LinkError("A path holds a character the junction command can't take")
        if not target.is_dir():
            raise LinkError("The junction target is not a folder")
        try:
            completed = subprocess.run(  # nosec B603  # fixed program and arguments, no shell
                [_CMD, "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True,
                timeout=_MKLINK_TIMEOUT_SECONDS,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            raise LinkError("The junction could not be made") from None
        if completed.returncode != 0 or not os.path.isjunction(link):
            raise LinkError("The junction could not be made")

    def exists(self, path: Path) -> bool:
        return os.path.lexists(path)

    def target(self, link: Path) -> Path | None:
        if not os.path.isjunction(link) and not os.path.islink(link):
            return None
        try:
            return Path(_strip_extended_prefix(os.readlink(link)))
        except OSError:
            return None

    def rename(self, source: Path, destination: Path) -> None:
        if not _is_link(source) or os.path.lexists(destination):
            raise LinkError("The link could not be renamed")
        try:
            os.rename(source, destination)
        except OSError:
            raise LinkError("The link could not be renamed") from None

    def remove(self, link: Path) -> None:
        if not _is_link(link):
            raise LinkError("Refused to remove something that is not a link")
        try:
            if os.path.isjunction(link):
                os.rmdir(link)  # how Windows removes a junction: the link, not what it points at
            else:
                link.unlink()
        except OSError:
            raise LinkError("The link could not be removed") from None


class SymlinkLinks:
    """Symbolic links as the stand-in for junctions off Windows."""

    def create(self, link: Path, target: Path) -> None:
        if not target.is_dir():
            raise LinkError("The link target is not a folder")
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError:
            raise LinkError("The link could not be made") from None

    def exists(self, path: Path) -> bool:
        return os.path.lexists(path)

    def target(self, link: Path) -> Path | None:
        if not os.path.islink(link):
            return None
        try:
            return Path(os.readlink(link))
        except OSError:
            return None

    def rename(self, source: Path, destination: Path) -> None:
        if not os.path.islink(source) or os.path.lexists(destination):
            raise LinkError("The link could not be renamed")
        try:
            os.rename(source, destination)
        except OSError:
            raise LinkError("The link could not be renamed") from None

    def remove(self, link: Path) -> None:
        if not os.path.islink(link):
            raise LinkError("Refused to remove something that is not a link")
        try:
            link.unlink()
        except OSError:
            raise LinkError("The link could not be removed") from None


def default_links() -> DirectoryLinks:
    return WindowsJunctions() if sys.platform == "win32" else SymlinkLinks()
