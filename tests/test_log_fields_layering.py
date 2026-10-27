"""LOG-01: the JSON fields of a log line; and the layering of secure/ and api/."""

import json
import logging
from pathlib import Path

import pytest

from shelfsync import logs
from shelfsync.api import errors
from shelfsync.secure import headers


def _log_one(folder: Path, **extra: object) -> dict[str, object]:
    handler = logs.configure_logging(folder, retention_days=1)
    try:
        logging.getLogger("shelfsync.test").info("x", extra=extra)
        handler.flush()
    finally:
        logs.remove_logging(handler)
    entry: dict[str, object] = json.loads((folder / logs.LOG_FILE_NAME).read_text(encoding="utf-8").splitlines()[0])
    return entry


def test_numbers_booleans_and_none_pass_through_the_json_fields_unchanged(tmp_path: Path) -> None:
    """LOG-01: only text is redacted; an int job_id stays an int."""
    entry = _log_one(tmp_path, job_id=7, step=True)
    assert entry["job_id"] == 7 and entry["step"] is True
    # an int must not become the string "7"
    assert isinstance(entry["job_id"], int) and not isinstance(entry["job_id"], bool)


def test_none_stays_null(tmp_path: Path) -> None:
    """LOG-01."""
    entry = _log_one(tmp_path)
    assert entry["job_id"] is None and entry["step"] is None


def test_other_objects_are_turned_into_text_and_redacted(tmp_path: Path) -> None:
    """LOG-01: an object in job_id is not written as it is."""

    class Job:
        def __str__(self) -> str:
            return "job with " + "c" + "k_" + "0123456789abcdef0123"

    entry = _log_one(tmp_path, job_id=Job())
    assert entry["job_id"] == "job with ck_[redacted]"


def test_text_fields_are_still_redacted(tmp_path: Path) -> None:
    """LOG-01."""
    entry = _log_one(tmp_path, job_id="c" + "k_" + "0123456789abcdef0123", step="ok")
    assert entry["job_id"] == "ck_[redacted]" and entry["step"] == "ok"


def test_secure_never_imports_from_api() -> None:
    """The layering: api/ builds on secure/, never the other way round."""
    root = Path(__file__).parents[1] / "backend" / "shelfsync" / "secure"
    for source in root.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "shelfsync.api" not in text, source.name
        assert "from shelfsync import api" not in text, source.name


@pytest.mark.parametrize("name", ["error_response", "forbidden", "signed_out"])
def test_api_errors_re_exports_the_secure_helpers(name: str) -> None:
    """The same objects are reachable from both places."""
    assert getattr(errors, name) is getattr(headers, name)
