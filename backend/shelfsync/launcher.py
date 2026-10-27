"""`python -m shelfsync.launcher`: the installed entry point (04 section 8); the work is in `tray.launcher`."""

from shelfsync.paths import resolve_data_paths
from shelfsync.tray.exit_guard import ExitGuard
from shelfsync.tray.launcher import main


def real_exit_guard() -> ExitGuard | None:
    """The one real safety exit (only here: an armed guard would end a test run). No data folder, no guard: the
    start-up reports that itself."""
    try:
        return ExitGuard(resolve_data_paths().tmp)
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main(exit_guard=real_exit_guard()))
