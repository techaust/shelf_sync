"""04-A V31 (INS-06): does Windows Defender real-time protection remove or lock a file written to a temp folder, and
how fast? PREPARED, NOT RUN BY THE BUILDER.

Writing the EICAR test string raises a Defender alert, so this check is run by the lead with the owner present. It is
deselected three ways: the `windows` and `defender` markers (`addopts` leaves both out), and it also skips unless the
environment variable `SHELFSYNC_RUN_V31=1` is set. To run it on purpose:

    $env:SHELFSYNC_RUN_V31 = "1"; uv run pytest tests/test_defender_v31.py -m defender --no-cov -s

It never changes a Defender setting and adds no exclusion (CLAUDE.md rule 12). The test string is built from pieces
at run time so this source file doesn't itself contain the signature. The file is written under pytest's temp folder
and removed at the end if it is still there. The observation is printed; the assertions only check that one of the
three outcomes was seen, because the answer is what V31 is for.
"""

import os
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.windows,
    pytest.mark.defender,
    pytest.mark.skipif(sys.platform != "win32", reason="Windows only"),
    pytest.mark.skipif(
        os.environ.get("SHELFSYNC_RUN_V31") != "1", reason="run by the lead with the owner: SHELFSYNC_RUN_V31=1"
    ),
]

WATCH_SECONDS = 30.0
STEP_SECONDS = 0.1


def eicar_bytes() -> bytes:
    """The standard antivirus test string (68 ASCII characters), assembled from pieces."""
    head = "X5O!P%@AP[4\\PZX54(P^)7CC)7}$"
    middle = "EICAR-STANDARD-ANTIVIRUS" + "-TEST-FILE!"
    tail = "$H+H*"
    return (head + middle + tail).encode("ascii")


def observe(path: Path) -> dict[str, object]:
    """Write the file, then watch it: gone (removed), unreadable (locked) or readable for the whole time."""
    written_at = time.monotonic()
    path.write_bytes(eicar_bytes())
    first_locked: float | None = None
    gone_after: float | None = None
    while time.monotonic() - written_at < WATCH_SECONDS:
        elapsed = time.monotonic() - written_at
        if not path.exists():
            gone_after = elapsed
            break
        try:
            with path.open("rb") as handle:
                handle.read(1)
        except OSError:
            if first_locked is None:
                first_locked = elapsed
        time.sleep(STEP_SECONDS)
    if gone_after is not None:
        outcome = "removed"
    elif first_locked is not None:
        outcome = "locked"
    else:
        outcome = "untouched"
    return {
        "outcome": outcome,
        "removed_after_seconds": gone_after,
        "first_unreadable_after_seconds": first_locked,
        "watched_seconds": WATCH_SECONDS,
    }


def test_v31_record_whether_defender_removes_or_locks_a_file_written_to_a_temp_folder(tmp_path: Path) -> None:
    """V31: records the outcome and the time; the lead copies the printed line into 04-A."""
    path = tmp_path / "eicar-test.zip"
    try:
        result = observe(path)
    finally:
        path.unlink(missing_ok=True)
    print(f"V31 observation: {result}")
    assert result["outcome"] in {"removed", "locked", "untouched"}
