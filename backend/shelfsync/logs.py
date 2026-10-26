"""Logs (LOG-01): JSON lines in logs\\shelfsync.log, rotated daily at UTC midnight."""

import json
import logging
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from shelfsync.clock import to_iso
from shelfsync.secure.redact import redact as _redact

LOG_FILE_NAME = "shelfsync.log"


def redact(text: str) -> str:
    """THE ONE PLACE the redaction plugs in (LOG-01): delegates to `secure.redact`.

    Every record's final message, with any traceback appended, and the job_id and step fields, pass through here
    (JsonFormatter.format) before they are written.
    """
    return _redact(text)


def _redacted_field(value: object) -> str | None:
    return None if value is None else redact(str(value))


class JsonFormatter(logging.Formatter):
    """One JSON object per line with exactly: time (UTC, ISO 8601, Z), level, job_id, step, message.

    job_id and step come from `logger.info("...", extra={"job_id": ..., "step": ...})`; missing ones are null.
    All three text fields go through `redact`.
    """

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        entry = {
            "time": to_iso(datetime.fromtimestamp(record.created, UTC)),
            "level": record.levelname,
            "job_id": _redacted_field(getattr(record, "job_id", None)),
            "step": _redacted_field(getattr(record, "step", None)),
            "message": redact(message),
        }
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(logs_dir: Path, retention_days: int) -> TimedRotatingFileHandler:
    """Send every log record (ShelfSync's and uvicorn's) to logs\\shelfsync.log; return the handler.

    Rotation at UTC midnight keeps `retention_days` rotated files. uvicorn's loggers have no handlers of their own
    here (the server is started with log_config=None) and propagate to the root logger, where this handler sits.
    """
    handler = TimedRotatingFileHandler(
        logs_dir / LOG_FILE_NAME, when="midnight", utc=True, backupCount=retention_days, encoding="utf-8"
    )
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return handler


def remove_logging(handler: logging.Handler) -> None:
    logging.getLogger().removeHandler(handler)
    handler.close()
