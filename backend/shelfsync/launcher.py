"""`python -m shelfsync.launcher`: the installed entry point (04 section 8); the work is in `tray.launcher`."""

from shelfsync.tray.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
