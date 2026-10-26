"""LOG-01 (without redaction): JSON lines, the five fields, a Z time, rotation."""

import json
import logging
import logging.handlers
from collections.abc import Iterator
from pathlib import Path

import pytest

from shelfsync import logs


@pytest.fixture
def handler(tmp_path: Path) -> Iterator[logging.Handler]:
    h = logs.configure_logging(tmp_path, retention_days=3)
    yield h
    logs.remove_logging(h)


def read_lines(folder: Path) -> list[dict[str, object]]:
    text = (folder / logs.LOG_FILE_NAME).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_line_is_json_with_the_five_fields_and_a_z_time(tmp_path: Path, handler: logging.Handler) -> None:
    logging.getLogger("shelfsync.test").info("hello %s", "world")
    handler.flush()
    (entry,) = read_lines(tmp_path)
    assert list(entry) == ["time", "level", "job_id", "step", "message"]
    assert entry["level"] == "INFO"
    assert entry["message"] == "hello world"
    assert entry["job_id"] is None and entry["step"] is None  # missing fields are null
    assert isinstance(entry["time"], str) and entry["time"].endswith("Z")
    assert len(entry["time"]) == len("2026-10-26T09:05:03.000120Z")


def test_job_id_and_step_come_from_extra(tmp_path: Path, handler: logging.Handler) -> None:
    logging.getLogger("shelfsync.test").info("scanning", extra={"job_id": "j-1", "step": "scan"})
    handler.flush()
    (entry,) = read_lines(tmp_path)
    assert (entry["job_id"], entry["step"]) == ("j-1", "scan")


def test_exception_goes_into_the_message(tmp_path: Path, handler: logging.Handler) -> None:
    try:
        raise ValueError("bad")
    except ValueError:
        logging.getLogger("shelfsync.test").exception("failed")
    handler.flush()
    (entry,) = read_lines(tmp_path)
    assert "ValueError: bad" in str(entry["message"])


def test_uvicorn_records_land_in_the_same_file(tmp_path: Path, handler: logging.Handler) -> None:
    logging.getLogger("uvicorn.error").info("Started server process")
    handler.flush()
    (entry,) = read_lines(tmp_path)
    assert entry["message"] == "Started server process"


def test_redaction_hook_sees_every_message(
    tmp_path: Path, handler: logging.Handler, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logs, "redact", lambda text: text.upper())
    logging.getLogger("shelfsync.test").info("quiet")
    handler.flush()
    (entry,) = read_lines(tmp_path)
    assert entry["message"] == "QUIET"


def test_rotation_keeps_the_set_number_of_files(tmp_path: Path, handler: logging.Handler) -> None:
    for day in range(1, 9):  # eight old rotated files; the handler keeps 3
        (tmp_path / f"{logs.LOG_FILE_NAME}.2026-01-0{day}").write_text("{}\n")
    logging.getLogger("shelfsync.test").info("today")
    assert isinstance(handler, logging.handlers.TimedRotatingFileHandler)
    handler.doRollover()
    rotated = sorted(p.name for p in tmp_path.glob(f"{logs.LOG_FILE_NAME}.*"))
    assert len(rotated) == 3
    # the newest three survive: the file just rotated, and the two newest old ones
    assert f"{logs.LOG_FILE_NAME}.2026-01-08" in rotated
    assert f"{logs.LOG_FILE_NAME}.2026-01-07" in rotated
    assert not (tmp_path / f"{logs.LOG_FILE_NAME}.2026-01-01").exists()
