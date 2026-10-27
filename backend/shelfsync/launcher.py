"""`python -m shelfsync.launcher`: the installed entry point (04 section 8); the work is in `tray.launcher`."""

from shelfsync.paths import DataPaths
from shelfsync.tray.exit_guard import ExitGuard
from shelfsync.tray.launcher import main


def make_real_exit_guard(paths: DataPaths) -> ExitGuard:
    """The one real safety exit, built from the data folder `run_application` resolved. Only `__main__` passes it
    (an armed guard would end a test run); building it opens nothing until it is armed."""
    return ExitGuard(paths.tmp)


if __name__ == "__main__":
    raise SystemExit(main(make_exit_guard=make_real_exit_guard))
