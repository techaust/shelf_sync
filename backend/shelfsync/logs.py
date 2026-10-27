"""Logs (LOG-01): JSON lines in logs\\shelfsync.log, rotated daily at UTC midnight."""

import json
import logging
import os
import re
import sys
import threading
import time
import warnings
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any, Final

from shelfsync.clock import to_iso
from shelfsync.paths import remove_entry
from shelfsync.secure.redact import redact as _redact

LOG_FILE_NAME = "shelfsync.log"
CTRL_C_LINE = "Stopped with Ctrl+C."


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


# Told once, the first time a log line can't be written (the launcher sets it to a toast: under pythonw nobody sees
# stderr). Nothing is passed to it: the owner-facing text is fixed.
_write_failure_notice: Callable[[], None] | None = None
_write_failure_told = False


def set_write_failure_notice(notice: Callable[[], None] | None) -> None:
    """Call `notice` once, the first time a log write fails (the count starts again each time this is called)."""
    global _write_failure_notice, _write_failure_told
    _write_failure_notice = notice
    _write_failure_told = False


def _report_write_failure() -> None:
    """One fixed line to stderr, through the redacting handler, when a log line couldn't be written, and the notice,
    once. It names the exception type and nothing from the record (the stdlib's own report prints the raw message and
    arguments)."""
    global _write_failure_told
    kind = sys.exc_info()[0]
    text = f"A log line couldn't be written ({kind.__name__ if kind is not None else 'unknown error'})"
    record = logging.LogRecord("shelfsync.logs", logging.ERROR, __file__, 0, text, None, None)
    _stderr_handler().emit(record)
    if _write_failure_notice is not None and not _write_failure_told:
        _write_failure_told = True
        try:
            _write_failure_notice()
        except Exception:  # a notification that can't be shown must not add a second failure
            return


class RedactingAppendHandler(logging.FileHandler):
    """Appends to the log file and never rotates or prunes it, with the same redaction and the same fixed report of a
    failed write. For a short-lived second process that shares the running copy's file."""

    def emit(self, record: logging.LogRecord) -> None:
        # With delay=True the stdlib opens the file inside emit(), outside its own error handling: a file that can't be
        # opened would raise out of the logging call. Report it like any other failed write instead.
        try:
            super().emit(record)
        except RecursionError:
            raise  # like the stdlib: logging that logs itself for ever is not a write failure to report
        except Exception:
            self.handleError(record)

    def handleError(self, record: logging.LogRecord) -> None:
        _report_write_failure()


class RedactingFileHandler(TimedRotatingFileHandler):
    """The log file handler. A failed write (bad arguments) is reported as one fixed line instead of the stdlib's
    dump of the message and arguments. A rollover that Windows refuses (the old file is open in another program)
    keeps logging into the current file and tries again at the next rollover time, instead of losing every later
    line. After each rollover the rotated files older than the retention are pruned (`prune_logs`)."""

    def handleError(self, record: logging.LogRecord) -> None:
        _report_write_failure()

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError:
            if self.stream is None:  # the stdlib closed it before the rename failed
                self.stream = self._open()
            self.rolloverAt = self.computeRollover(int(time.time()))
            _report_write_failure()
            return
        prune_logs(Path(self.baseFilename).parent, self.backupCount)


# `TimedRotatingFileHandler` names a rotated file `<base>.<YYYY-MM-DD>` for "midnight" rotation: the UTC date of the
# day the file holds. Only a name of exactly this shape is ever pruned.
_ROTATED_NAME = re.compile(rf"^{re.escape(LOG_FILE_NAME)}\.(\d{{4}})-(\d{{2}})-(\d{{2}})$")
_prune_log = logging.getLogger("shelfsync.logs.prune")


def prune_logs(logs_dir: Path, retention_days: int, today: date | None = None) -> list[str]:
    """Delete the rotated log files (`shelfsync.log.<date>`) whose day is more than `retention_days` before today (UTC),
    whatever their count (the handler's `backupCount` counts files, not days; LOG-01). Returns the names removed.

    Never the current file, never a name the handler doesn't write, never a folder; a link with such a name is
    removed itself, not followed (`paths.remove_entry`). An error is logged and the file skipped."""
    cutoff = (today if today is not None else datetime.now(UTC).date()) - timedelta(days=retention_days)
    removed: list[str] = []
    try:
        entries = list(logs_dir.iterdir())
    except OSError as error:
        _prune_log.warning("Couldn't list the logs folder (%s)", type(error).__name__)
        return removed
    for entry in entries:
        match = _ROTATED_NAME.match(entry.name)
        if match is None or entry.name == LOG_FILE_NAME:
            continue
        try:
            day = date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:  # 2026-13-45: not a date, so not one of ours
            continue
        if day >= cutoff:
            continue
        try:
            if entry.is_dir() and not (entry.is_symlink() or os.path.isjunction(entry)):
                continue  # the handler writes files only
            remove_entry(entry)
        except OSError as error:
            _prune_log.warning("Couldn't remove an old log file (%s)", type(error).__name__)
            continue
        removed.append(entry.name)
    return removed


def set_log_retention(handler: TimedRotatingFileHandler, retention_days: int) -> list[str]:
    """Keep `retention_days` of logs from now on and prune at once. Returns the names removed."""
    handler.backupCount = retention_days
    return prune_logs(Path(handler.baseFilename).parent, retention_days)


def configure_logging(logs_dir: Path, retention_days: int) -> TimedRotatingFileHandler:
    """Send every log record (ShelfSync's and uvicorn's) to logs\\shelfsync.log; return the handler.

    Rotation at UTC midnight keeps `retention_days` rotated files (and `prune_logs` removes older ones by date). It
    doesn't prune here: the retention is the default until the settings are read (`set_log_retention`).
    uvicorn's loggers have no handlers of their own here (the server is started with log_config=None) and
    propagate to the root logger, where this handler sits.
    """
    handler = RedactingFileHandler(
        logs_dir / LOG_FILE_NAME, when="midnight", utc=True, backupCount=retention_days, encoding="utf-8"
    )
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return handler


def configure_append_logging(logs_dir: Path) -> logging.Handler:
    """Like `configure_logging`, but the handler only appends (see `RedactingAppendHandler`)."""
    # delay=True: the file is opened at the first line, so building the handler can't fail and a file that can't be
    # opened is one reported write failure, not a failed start.
    handler = RedactingAppendHandler(logs_dir / LOG_FILE_NAME, encoding="utf-8", delay=True)
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


_STDERR_HANDLER: Final = RedactingStderrHandler()


def _stderr_handler() -> RedactingStderrHandler:
    """The one redacting stderr handler. It holds no state, so it is built once and reused."""
    return _STDERR_HANDLER


def _exc_info(
    exc_type: type[BaseException], exc_value: BaseException | None, traceback: TracebackType | None
) -> tuple[type[BaseException], BaseException, TracebackType | None] | None:
    return None if exc_value is None else (exc_type, exc_value, traceback)


def report_ctrl_c() -> None:
    """Ctrl+C is not a crash: one fixed line through the redacting handler. Never Python's own hook, which would
    print the chained traceback unredacted."""
    record = logging.LogRecord("shelfsync.logs", logging.WARNING, __file__, 0, CTRL_C_LINE, None, None)
    _stderr_handler().emit(record)


def _log_uncaught(exc_type: type[BaseException], exc_value: BaseException, traceback: TracebackType | None) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        report_ctrl_c()
        return
    _UNCAUGHT.critical("Uncaught exception", exc_info=(exc_type, exc_value, traceback))


def _log_uncaught_in_thread(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:  # the default hook ignores it too
        return
    name = args.thread.name if args.thread is not None else "unknown"
    _UNCAUGHT.critical(
        "Uncaught exception in thread %s", name, exc_info=_exc_info(args.exc_type, args.exc_value, args.exc_traceback)
    )


def _log_unraisable(unraisable: sys.UnraisableHookArgs) -> None:
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
    logging.lastResort = _stderr_handler()
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
