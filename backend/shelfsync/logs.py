"""Logs (LOG-01): JSON lines in logs\\shelfsync.log, rotated daily at UTC midnight."""

import json
import logging
import sys
import threading
import warnings
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any

from shelfsync.clock import to_iso
from shelfsync.secure.redact import redact as _redact

LOG_FILE_NAME = "shelfsync.log"


def redact(text: str) -> str:
    """THE ONE PLACE the redaction plugs in (LOG-01): delegates to `secure.redact`.

    Every record's final message, with any traceback appended, and the job_id and step fields, pass through here
    (JsonFormatter.format) before they are written.
    """
    return _redact(text)


def _redacted_field(value: object) -> object:
    """Text is redacted; None, booleans and numbers pass through unchanged (they can't hold a secret). Anything
    else is turned into text first, so it is redacted too."""
    if value is None or isinstance(value, bool | int | float):
        return value
    return redact(value if isinstance(value, str) else str(value))


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


def _report_write_failure() -> None:
    """One fixed line to stderr, through the redacting handler, when a log line couldn't be written. It names the
    exception type and nothing from the record (the stdlib's own report prints the raw message and arguments)."""
    kind = sys.exc_info()[0]
    text = f"A log line couldn't be written ({kind.__name__ if kind is not None else 'unknown error'})"
    record = logging.LogRecord("shelfsync.logs", logging.ERROR, __file__, 0, text, None, None)
    RedactingStderrHandler().emit(record)


class RedactingFileHandler(TimedRotatingFileHandler):
    """The log file handler. A failed write (bad arguments, a rollover refused by Windows) is reported as one fixed
    line instead of the stdlib's dump of the message and arguments."""

    def handleError(self, record: logging.LogRecord) -> None:
        _report_write_failure()


def configure_logging(logs_dir: Path, retention_days: int) -> TimedRotatingFileHandler:
    """Send every log record (ShelfSync's and uvicorn's) to logs\\shelfsync.log; return the handler.

    Rotation at UTC midnight keeps `retention_days` rotated files. uvicorn's loggers have no handlers of their own
    here (the server is started with log_config=None) and propagate to the root logger, where this handler sits.
    """
    handler = RedactingFileHandler(
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


# ---- Every output goes through redact (LOG-01, 06 section 3) -----------------------------------------------------
#
# The file handler above redacts everything it writes. These guards cover the other places text can leave the
# process: Python's handler of last resort (records logged before logging is set up or after it is removed), the
# uncaught-exception hooks, and warnings.

_UNCAUGHT = logging.getLogger("shelfsync.uncaught")
_originals: dict[str, Any] = {}


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class RedactingStderrHandler(logging.Handler):
    """Writes WARNING and above to stderr, redacted. Does nothing when there is no stderr (`sys.stderr` is None
    under pythonw), and never reports its own failures: Python's default error report would print the unredacted
    message and arguments."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.setFormatter(_RedactingFormatter("%(levelname)s: %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        stream = sys.stderr
        if stream is None:
            return
        try:
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)

    def handleError(self, record: logging.LogRecord) -> None:
        return None


def _exc_info(
    exc_type: type[BaseException], exc_value: BaseException | None, traceback: TracebackType | None
) -> tuple[type[BaseException], BaseException, TracebackType | None] | None:
    return None if exc_value is None else (exc_type, exc_value, traceback)


def _log_uncaught(exc_type: type[BaseException], exc_value: BaseException, traceback: TracebackType | None) -> None:
    if issubclass(exc_type, KeyboardInterrupt):  # Ctrl+C is not a crash: leave it to Python's own hook
        _originals.get("excepthook", sys.__excepthook__)(exc_type, exc_value, traceback)
        return
    _UNCAUGHT.critical("Uncaught exception", exc_info=(exc_type, exc_value, traceback))


def _log_uncaught_in_thread(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:  # the default hook ignores it too
        return
    name = args.thread.name if args.thread is not None else "unknown"
    _UNCAUGHT.critical(
        "Uncaught exception in thread %s", name, exc_info=_exc_info(args.exc_type, args.exc_value, args.exc_traceback)
    )


def _log_unraisable(unraisable: "sys.UnraisableHookArgs") -> None:
    _UNCAUGHT.error(
        "Unraisable exception: %s",
        unraisable.err_msg or "exception ignored",
        exc_info=_exc_info(unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback),
    )


def _warnings_captured() -> bool:
    """Whether `logging.captureWarnings(True)` is already in force: then `warnings.showwarning` is the logging
    module's own function (the stdlib has no public way to ask)."""
    return getattr(warnings.showwarning, "__module__", None) == "logging"


def install_output_guards() -> None:
    """Called first in `server.main()`. Replaces `logging.lastResort` with a redacting stderr handler, sends
    uncaught exceptions (main thread, other threads, unraisable ones) through the logger, and sends warnings to the
    log (`logging.captureWarnings`). Calling it again does nothing."""
    if _originals:
        return
    _originals.update(
        capture_warnings=_warnings_captured(),
        last_resort=logging.lastResort,
        excepthook=sys.excepthook,
        thread_excepthook=threading.excepthook,
        unraisablehook=sys.unraisablehook,
    )
    logging.lastResort = RedactingStderrHandler()
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_uncaught_in_thread
    sys.unraisablehook = _log_unraisable
    logging.captureWarnings(True)


def remove_output_guards() -> None:
    """Put back what `install_output_guards` replaced (for tests)."""
    if not _originals:
        return
    logging.lastResort = _originals["last_resort"]
    sys.excepthook = _originals["excepthook"]
    threading.excepthook = _originals["thread_excepthook"]
    sys.unraisablehook = _originals["unraisablehook"]
    logging.captureWarnings(_originals["capture_warnings"])
    _originals.clear()
