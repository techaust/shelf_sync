"""Where the program files are (04 section 8):

    <root>\versions\\<v>\\       one folder per version (the embedded Python, the app, the UI)
    <root>\\current             a directory junction to the active version
    <root>\\current.next / current.old   exist only while the switch runs
    <root>\\manifests\\<v>.json (and .json.sig)   each kept version's signed manifest, outside the version folders

and where the updater keeps its own files in the data folder (`update\\state.json`, `update\result.json`,
`update\\downloads\\`).

An installed copy finds its root from where its own Python is (`<root>\versions\\<v>\\pythonw.exe`). A copy that isn't
installed (development, tests, the rehearsal) has no layout unless SHELFSYNC_INSTALL_DIR names one; an installed copy
ignores that variable, so no setting can point an installed copy's updater somewhere else.
"""

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from shelfsync import __version__
from shelfsync.paths import DataPaths
from shelfsync.update.versions import parse_version

INSTALL_DIR_ENV = "SHELFSYNC_INSTALL_DIR"  # for tests and rehearsals only; ignored by an installed copy
INTERPRETER_NAME = "pythonw.exe"
CONSOLE_INTERPRETER_NAME = "python.exe"


@dataclass(frozen=True)
class InstallLayout:
    root: Path

    @property
    def versions(self) -> Path:
        return self.root / "versions"

    @property
    def manifests(self) -> Path:
        return self.root / "manifests"

    @property
    def current(self) -> Path:
        return self.root / "current"

    @property
    def current_next(self) -> Path:
        return self.root / "current.next"

    @property
    def current_old(self) -> Path:
        return self.root / "current.old"

    def version_dir(self, version: str) -> Path:
        parse_version(version)  # never build a path from text that isn't a version
        return self.versions / version

    def incoming_dir(self, version: str) -> Path:
        parse_version(version)
        return self.versions / f".incoming-{version}"

    def manifest_path(self, version: str) -> Path:
        parse_version(version)
        return self.manifests / f"{version}.json"

    def signature_path(self, version: str) -> Path:
        parse_version(version)
        return self.manifests / f"{version}.json.sig"

    def interpreter(self, version: str, *, console: bool = False) -> Path:
        name = CONSOLE_INTERPRETER_NAME if console else INTERPRETER_NAME
        return self.version_dir(version) / name

    @property
    def current_interpreter(self) -> Path:
        return self.current / INTERPRETER_NAME


def installed_root(executable: str | None = None) -> Path | None:
    """The install root if `executable` sits in `<root>\\versions\\<v>\\` (reached through the `current` junction or
    not: the path is resolved first) AND `<v>` is this code's own version, otherwise None. The version check keeps a
    copy that merely runs from some folder called `versions` (a developer's, or one named by mistake) from counting as
    installed: an installed copy's folder is named for the version it holds."""
    resolved = Path(os.path.realpath(executable or sys.executable))
    folder = resolved.parent  # versions\<v>
    if folder.parent.name.casefold() == "versions" and folder.name == __version__:
        return folder.parent.parent
    return None


def resolve_install_layout(
    executable: str | None = None, environ: Mapping[str, str] | None = None
) -> InstallLayout | None:
    """The layout of the installed copy; for a copy that isn't installed, the one SHELFSYNC_INSTALL_DIR names; else
    None (a development copy: updates are off)."""
    root = installed_root(executable)
    if root is not None:
        return InstallLayout(root)
    value = (environ if environ is not None else os.environ).get(INSTALL_DIR_ENV)
    if value and Path(value).is_absolute():
        return InstallLayout(Path(value))
    return None


@dataclass(frozen=True)
class UpdatePaths:
    """The updater's files inside the data folder."""

    data: DataPaths

    @property
    def root(self) -> Path:
        return self.data.root / "update"

    @property
    def state_json(self) -> Path:
        return self.root / "state.json"

    @property
    def result_json(self) -> Path:
        return self.root / "result.json"

    @property
    def downloads(self) -> Path:
        return self.root / "downloads"
