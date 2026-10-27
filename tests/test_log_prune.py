"""LOG-01: rotated log files are pruned by age, whatever their count."""

import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from shelfsync import logs
from shelfsync.logs import prune_logs, set_log_retention

TODAY = date(2026, 10, 28)


def make(folder: Path, *names: str) -> None:
    for name in names:
        (folder / name).write_text("x", encoding="utf-8")


def test_a_file_past_the_retention_goes_and_the_edge_stays(tmp_path: Path) -> None:
    """LOG-01: with 3 days, the file of the day 3 days ago is kept and the one of 4 days ago is not."""
    make(tmp_path, "shelfsync.log.2026-10-25", "shelfsync.log.2026-10-24", "shelfsync.log.2026-10-27")
    removed = prune_logs(tmp_path, 3, TODAY)
    assert removed == ["shelfsync.log.2026-10-24"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["shelfsync.log.2026-10-25", "shelfsync.log.2026-10-27"]


def test_many_old_files_all_go_whatever_their_count(tmp_path: Path) -> None:
    """LOG-01: age, not a count of files."""
    make(tmp_path, *(f"shelfsync.log.2025-01-{day:02d}" for day in range(1, 29)))
    assert len(prune_logs(tmp_path, 30, TODAY)) == 28


def test_the_current_file_and_foreign_names_are_kept(tmp_path: Path) -> None:
    """LOG-01: only `shelfsync.log.<date>` is ours."""
    keep = [
        "shelfsync.log",
        "shelfsync.log.2000-01-01.bak",
        "other.log.2000-01-01",
        "shelfsync.log.20000101",
        "shelfsync.log.2000-13-45",  # not a date
        "notes.txt",
        "xshelfsync.log.2000-01-01",
    ]
    make(tmp_path, *keep)
    assert prune_logs(tmp_path, 1, TODAY) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(keep)


def test_a_link_is_removed_itself_and_never_followed(tmp_path: Path) -> None:
    """LOG-01: a link with an old rotated name is removed, its target and the target's content stay."""
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "precious.txt").write_text("keep", encoding="utf-8")
    folder = tmp_path / "logs"
    folder.mkdir()
    from shelfsync.platform.junction import default_links

    default_links().create(folder / "shelfsync.log.2000-01-01", target)
    assert prune_logs(folder, 1, TODAY) == ["shelfsync.log.2000-01-01"]
    assert not os.path.lexists(folder / "shelfsync.log.2000-01-01")
    assert (target / "precious.txt").read_text(encoding="utf-8") == "keep"


def test_a_real_folder_with_a_rotated_name_is_left_alone(tmp_path: Path) -> None:
    """LOG-01: the handler writes files only."""
    folder = tmp_path / "shelfsync.log.2000-01-01"
    folder.mkdir()
    (folder / "inside.txt").write_text("x", encoding="utf-8")
    assert prune_logs(tmp_path, 1, TODAY) == []
    assert (folder / "inside.txt").exists()


def test_a_file_that_cant_be_removed_is_logged_and_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """LOG-01: one locked file doesn't stop the rest, and the log line names the error type only."""
    make(tmp_path, "shelfsync.log.2000-01-01", "shelfsync.log.2000-01-02")
    real = logs.remove_entry

    def refuse_first(entry: Path) -> None:
        if entry.name.endswith("01-01"):
            raise PermissionError(13, "in use", str(entry))
        real(entry)

    monkeypatch.setattr(logs, "remove_entry", refuse_first)
    with caplog.at_level(logging.WARNING, logger="shelfsync.logs.prune"):
        removed = prune_logs(tmp_path, 1, TODAY)
    assert removed == ["shelfsync.log.2000-01-02"]
    assert (tmp_path / "shelfsync.log.2000-01-01").exists()
    assert "PermissionError" in caplog.text
    assert "in use" not in caplog.text


def test_a_missing_folder_is_not_an_error(tmp_path: Path) -> None:
    """LOG-01."""
    assert prune_logs(tmp_path / "nope", 1, TODAY) == []


def test_today_defaults_to_the_utc_date(tmp_path: Path) -> None:
    """LOG-01."""
    make(tmp_path, f"shelfsync.log.{datetime.now(UTC).date().isoformat()}", "shelfsync.log.2000-01-01")
    assert prune_logs(tmp_path, 1) == ["shelfsync.log.2000-01-01"]


def test_set_log_retention_sets_the_handler_and_prunes(tmp_path: Path) -> None:
    """LOG-01: what start-up and a saved setting both call."""
    handler = logs.configure_logging(tmp_path, 30)
    try:
        make(tmp_path, "shelfsync.log.2000-01-01")
        assert set_log_retention(handler, 5) == ["shelfsync.log.2000-01-01"]
        assert handler.backupCount == 5
    finally:
        logs.remove_logging(handler)


def test_configuring_the_handler_does_not_prune(tmp_path: Path) -> None:
    """LOG-01: the retention isn't known until the settings are read, so the default must not delete anything."""
    make(tmp_path, "shelfsync.log.2000-01-01")
    handler = logs.configure_logging(tmp_path, 1)
    logs.remove_logging(handler)
    assert (tmp_path / "shelfsync.log.2000-01-01").exists()


def test_a_rollover_prunes_afterwards(tmp_path: Path) -> None:
    """LOG-01: after each rotation, files past the retention go, the fresh rotated file stays."""
    handler = logs.configure_logging(tmp_path, 3)
    try:
        make(tmp_path, "shelfsync.log.2000-01-01")
        logging.getLogger("shelfsync.test").info("a line")
        handler.doRollover()
    finally:
        logs.remove_logging(handler)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert "shelfsync.log.2000-01-01" not in names
    assert "shelfsync.log" in names
    assert any(name.startswith("shelfsync.log.20") for name in names)


@pytest.mark.parametrize("days", [0, -1])
def test_prune_and_set_retention_refuse_less_than_one_day(tmp_path: Path, days: int) -> None:
    """LOG-01: a 0 would delete every rotated file."""
    (tmp_path / "shelfsync.log.2000-01-01").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        prune_logs(tmp_path, days, TODAY)
    handler = logs.configure_logging(tmp_path, 30)
    try:
        with pytest.raises(ValueError):
            set_log_retention(handler, days)
        assert handler.backupCount == 30
    finally:
        logs.remove_logging(handler)
    assert (tmp_path / "shelfsync.log.2000-01-01").exists()


def test_set_log_retention_holds_the_handlers_lock(tmp_path: Path) -> None:
    """LOG-01: the change and the prune run under the handler's lock."""
    handler = logs.configure_logging(tmp_path, 30)
    seen: list[bool] = []
    real = logs.prune_logs

    def spy(*args: object, **kwargs: object) -> list[str]:
        seen.append(handler.lock._is_owned())  # type: ignore[union-attr, attr-defined]
        return real(*args, **kwargs)  # type: ignore[arg-type]

    try:
        logs.prune_logs = spy  # type: ignore[assignment]
        set_log_retention(handler, 5)
    finally:
        logs.prune_logs = real
        logs.remove_logging(handler)
    assert seen == [True]
