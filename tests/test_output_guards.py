"""LOG-01: every output goes through redact. One secret per path; none may appear unmasked.

Each secret is a different key-shaped value, so a leak names the path that let it through. The guards change
process-wide state (`logging.lastResort`, the excepthooks), so each test installs them in its own body and removes
them in `finally`, never through a fixture (pytest installs its own thread hook around the test body).
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from shelfsync import logs, server
from shelfsync.paths import DataPaths
from shelfsync.platform.notify import FakeNotifier, LogNotifier
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.token import INSTALL_TOKEN_NAME
from tests.support import WRITE_HEADERS, make_harness
from tests.test_server import RecordingServe

BACKEND = Path(__file__).parents[1] / "backend"


def key(number: int) -> str:
    """A WooCommerce-shaped key, different for each path."""
    return "c" + "k_" + f"{number:040x}"


@contextmanager
def guards() -> Iterator[None]:
    logs.install_output_guards()
    try:
        yield
    finally:
        logs.remove_output_guards()


@contextmanager
def file_log(folder: Path) -> Iterator[Path]:
    handler = logs.configure_logging(folder, retention_days=1)
    try:
        yield folder / logs.LOG_FILE_NAME
    finally:
        handler.flush()
        logs.remove_logging(handler)


def lonely_logger() -> logging.Logger:
    """A logger with no handler anywhere above it, so its records go to `logging.lastResort` (inside pytest the root
    logger always has pytest's own handlers)."""
    logger = logging.getLogger("shelfsync.lonely")
    logger.handlers.clear()
    logger.propagate = False
    return logger


# ---- the file log ------------------------------------------------------------------------------------------------


def test_message_and_args(tmp_path: Path) -> None:
    """LOG-01."""
    secret = key(1)
    with file_log(tmp_path) as log_file:
        logging.getLogger("shelfsync.t").warning("saw %s and %s", "ok", secret)
        logging.getLogger("shelfsync.t").warning(f"formatted {secret}")
    text = log_file.read_text(encoding="utf-8")
    assert secret not in text
    assert text.count("ck_[redacted]") == 2


def test_exception_message_and_traceback(tmp_path: Path) -> None:
    """LOG-01."""
    secret = key(2)
    with file_log(tmp_path) as log_file:
        try:
            raise ValueError(f"bad value {secret}")
        except ValueError:
            logging.getLogger("shelfsync.t").exception("failed")
    text = log_file.read_text(encoding="utf-8")
    assert secret not in text
    assert "ValueError: bad value ck_[redacted]" in json.loads(text.splitlines()[0])["message"]


def test_extra_fields(tmp_path: Path) -> None:
    """LOG-01: job_id and step."""
    first, second = key(3), key(4)
    with file_log(tmp_path) as log_file:
        logging.getLogger("shelfsync.t").info("scan", extra={"job_id": first, "step": second})
    text = log_file.read_text(encoding="utf-8")
    assert first not in text and second not in text


def test_uvicorn_error_records(tmp_path: Path) -> None:
    """LOG-01."""
    secret = key(5)
    with file_log(tmp_path) as log_file:
        logging.getLogger("uvicorn.error").error("Exception in ASGI application %s", secret)
    assert secret not in log_file.read_text(encoding="utf-8")


def test_a_warning(tmp_path: Path) -> None:
    """LOG-01: captureWarnings sends warnings to the log, where they are redacted."""
    secret = key(6)
    with guards(), file_log(tmp_path) as log_file, warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.warn(f"careful with {secret}", UserWarning, stacklevel=1)
    text = log_file.read_text(encoding="utf-8")
    assert secret not in text
    assert "careful with ck_[redacted]" in text


def test_the_log_notifier(tmp_path: Path) -> None:
    """LOG-01: the stand-in notifier writes to the log."""
    secret = key(7)
    with file_log(tmp_path) as log_file:
        LogNotifier().notify(f"Something about {secret}")
    text = log_file.read_text(encoding="utf-8")
    assert secret not in text and "ck_[redacted]" in text


# ---- before logging is set up, and after it is removed: logging.lastResort ----------------------------------------


def test_a_record_before_logging_is_set_up(capsys: pytest.CaptureFixture[str]) -> None:
    """LOG-01: with no handler the record goes to logging.lastResort, which the guards replace with a redacting one."""
    secret = key(8)
    with guards():
        lonely_logger().error("early failure with %s", secret)
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert "ck_[redacted]" in captured.err


def test_a_record_after_logging_is_removed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """LOG-01: server.run() removes its handler in `finally`; later records go to lastResort again."""
    secret = key(9)
    with guards():
        with file_log(tmp_path):
            pass
        lonely_logger().error("late failure with %s", secret)
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert "ck_[redacted]" in captured.err


def test_without_the_guards_the_default_last_resort_would_leak(capsys: pytest.CaptureFixture[str]) -> None:
    """The control for the two tests above: Python's own handler of last resort writes the key as it is."""
    secret = key(10)
    lonely_logger().error("early failure with %s", secret)
    assert secret in capsys.readouterr().err


def test_the_last_resort_handler_does_nothing_without_a_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    """LOG-01: under pythonw sys.stderr is None; a record must not raise."""
    with guards():
        monkeypatch.setattr(sys, "stderr", None)
        lonely_logger().error("nowhere to write %s", key(11))


def test_the_last_resort_handler_never_reports_its_own_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """LOG-01: Python's default error report prints the unredacted message and arguments."""

    class Broken:
        def write(self, text: str) -> int:
            raise OSError("closed")

        def flush(self) -> None:
            raise OSError("closed")

    with guards():
        monkeypatch.setattr(sys, "stderr", Broken())
        lonely_logger().error("failing with %s", key(12))
        monkeypatch.undo()
    captured = capsys.readouterr()
    assert key(12) not in captured.out + captured.err


def test_install_and_remove_put_everything_back_and_install_is_idempotent() -> None:
    """LOG-01: the guards are installed once and fully removed."""
    before = (logging.lastResort, sys.excepthook, threading.excepthook, sys.unraisablehook)
    logs.install_output_guards()
    try:
        assert isinstance(logging.lastResort, logs.RedactingStderrHandler)
        assert sys.excepthook is not before[1]
        assert threading.excepthook is not before[2]
        installed = (logging.lastResort, sys.excepthook, threading.excepthook, sys.unraisablehook)
        logs.install_output_guards()  # again: nothing changes
        assert (logging.lastResort, sys.excepthook, threading.excepthook, sys.unraisablehook) == installed
    finally:
        logs.remove_output_guards()
    assert (logging.lastResort, sys.excepthook, threading.excepthook, sys.unraisablehook) == before


# ---- uncaught exceptions -------------------------------------------------------------------------------------------


def run_script(code: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run a separate Python process (the exception is really uncaught there). It starts in an empty folder and is
    given the backend folder through sys.path, never through the current directory."""
    prelude = (
        f"import sys; sys.path.insert(0, {str(BACKEND)!r}); from shelfsync import logs; logs.install_output_guards()\n"
    )
    return subprocess.run(
        [sys.executable, "-c", prelude + code], cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False
    )


def test_an_uncaught_exception_in_the_main_thread(tmp_path: Path) -> None:
    """LOG-01: a real uncaught exception in another process; its stderr holds the key masked."""
    secret = key(13)
    result = run_script(f"raise RuntimeError('startup failed with {secret}')", tmp_path)
    assert result.returncode == 1
    assert secret not in result.stdout + result.stderr
    assert "RuntimeError: startup failed with ck_[redacted]" in result.stderr


def test_an_uncaught_exception_with_no_stderr_is_silent(tmp_path: Path) -> None:
    """LOG-01: as under pythonw: no stderr, nothing printed, and still a failing exit code."""
    secret = key(14)
    result = run_script(f"sys.stderr = None\nraise RuntimeError('quiet {secret}')", tmp_path)
    assert result.returncode == 1
    assert secret not in result.stdout + result.stderr
    assert result.stderr == ""


def test_an_uncaught_exception_in_another_thread(tmp_path: Path) -> None:
    """LOG-01: threading.excepthook logs through the redacting logger."""
    secret = key(15)

    def boom() -> None:
        raise RuntimeError(f"thread failed with {secret}")

    with guards(), file_log(tmp_path) as log_file:
        thread = threading.Thread(target=boom, name="worker-1")
        thread.start()
        thread.join()
    text = log_file.read_text(encoding="utf-8")
    assert secret not in text
    assert "Uncaught exception in thread worker-1" in text
    assert "RuntimeError: thread failed with ck_[redacted]" in json.loads(text.splitlines()[0])["message"]


def test_a_thread_that_exits_with_system_exit_is_not_logged(tmp_path: Path) -> None:
    """LOG-01: like the default hook, SystemExit in a thread is ignored."""

    def leave() -> None:
        raise SystemExit(0)

    with guards(), file_log(tmp_path) as log_file:
        thread = threading.Thread(target=leave)
        thread.start()
        thread.join()
    assert not log_file.exists() or log_file.read_text(encoding="utf-8") == ""


def test_the_main_thread_hook_logs_through_the_redacting_logger(tmp_path: Path) -> None:
    """LOG-01: in-process check of sys.excepthook itself."""
    secret = key(16)
    with guards(), file_log(tmp_path) as log_file:
        try:
            raise RuntimeError(f"top level {secret}")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())  # type: ignore[arg-type]
    text = log_file.read_text(encoding="utf-8")
    assert secret not in text and "ck_[redacted]" in text


def test_an_unraisable_exception_is_logged_redacted(tmp_path: Path) -> None:
    """LOG-01: errors in __del__ and the like."""
    secret = key(17)
    error = RuntimeError(f"in a destructor {secret}")
    unraisable = SimpleNamespace(
        exc_type=RuntimeError, exc_value=error, exc_traceback=None, err_msg="Exception ignored"
    )
    with guards(), file_log(tmp_path) as log_file:
        sys.unraisablehook(unraisable)  # type: ignore[arg-type]
    text = log_file.read_text(encoding="utf-8")
    assert secret not in text and "Exception ignored" in text


# ---- bodies and start-up -----------------------------------------------------------------------------------------


def test_the_422_and_500_bodies() -> None:
    """LOG-01: bodies are fixed and hold nothing from the request or the error."""
    secret = key(18)
    harness = make_harness()

    @harness.app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError(f"broke on {secret}")

    unprocessable = harness.client().post("/api/session", json={"ticket": [secret]}, headers=WRITE_HEADERS)
    assert unprocessable.status_code == 422 and secret not in unprocessable.text
    broken = harness.signed_in_client(raise_server_exceptions=False).get("/api/boom")
    assert broken.status_code == 500 and secret not in broken.text


def test_run_with_a_start_up_exception_that_holds_the_token(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01: the install token is registered when loaded, so a failure after that can't write it out."""
    store = MemorySecretStore()

    def failing_bind(ports: list[int], retry_seconds: float = 0.0) -> None:
        token = store.get(INSTALL_TOKEN_NAME)
        raise RuntimeError(f"cannot bind with {token}")

    monkeypatch.setattr(server, "bind_first_free", failing_bind)
    notifier = FakeNotifier()
    with guards():
        code = server.run(data_paths, notifier, RecordingServe(), 0.0, store)
    assert code == server.EXIT_START_FAILED
    token = store.get(INSTALL_TOKEN_NAME)
    assert token
    text = (data_paths.logs / logs.LOG_FILE_NAME).read_text(encoding="utf-8")
    assert token not in text
    assert "cannot bind with [redacted]" in text
    captured = capfd.readouterr()
    assert token not in captured.out + captured.err
    assert token not in " ".join(notifier.messages)


def test_main_installs_the_guards_before_anything_else(monkeypatch: pytest.MonkeyPatch) -> None:
    """LOG-01: install_output_guards() is the first call in main(), ahead of resolve_data_paths()."""
    order: list[str] = []

    def fake_guards() -> None:
        order.append("guards")

    def fake_resolve() -> DataPaths:
        order.append("resolve")
        raise RuntimeError("no data folder")

    monkeypatch.setattr(server, "install_output_guards", fake_guards)
    monkeypatch.setattr(server, "resolve_data_paths", fake_resolve)
    assert server.main() == server.EXIT_START_FAILED  # now inside the start-up try: a plain exit code, no traceback
    assert order == ["guards", "resolve"]


# ---- review round 1 -----------------------------------------------------------------------------------------------


@contextmanager
def only_the_file_handler() -> Iterator[logging.Logger]:
    """A logger that reaches ShelfSync's file handler and nothing else (pytest's own capture handler on the root
    logger would raise on bad arguments before the file handler is asked)."""
    logger = logging.getLogger("shelfsync.badwrite")
    root_handlers = [h for h in logging.getLogger().handlers if isinstance(h, logs.RedactingFileHandler)]
    logger.handlers[:] = root_handlers
    logger.propagate = False
    try:
        yield logger
    finally:
        logger.handlers.clear()
        logger.propagate = True


def test_a_failed_log_write_prints_one_fixed_line_and_nothing_from_the_record(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01: bad arguments make `record.getMessage()` fail; the stdlib's own report would print the message and
    arguments (here a key) to stderr."""
    secret = key(30)
    with guards(), file_log(tmp_path) as log_file, only_the_file_handler() as logger:
        logger.error("%s and %s", secret)  # one argument too few
    captured = capfd.readouterr()
    assert secret not in captured.out + captured.err
    assert "A log line couldn't be written (TypeError)" in captured.err
    assert secret not in (log_file.read_text(encoding="utf-8") if log_file.exists() else "")


def test_a_failed_log_write_is_reported_even_without_the_guards(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01: the file handler's own handleError does not depend on install_output_guards()."""
    secret = key(31)
    with file_log(tmp_path), only_the_file_handler() as logger:
        logger.error("%s and %s", secret)
    captured = capfd.readouterr()
    assert secret not in captured.out + captured.err
    assert "A log line couldn't be written (TypeError)" in captured.err


def test_ctrl_c_prints_one_fixed_line_and_never_the_chained_traceback(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01 (M1a.2 re-check R2): a KeyboardInterrupt isn't a CRITICAL crash, and Python's own hook would print its
    chained exception (here holding a key) unredacted."""
    secret = key(40)
    with guards(), file_log(tmp_path) as log_file:
        interrupt = KeyboardInterrupt()
        interrupt.__context__ = RuntimeError(f"failed with {secret}")
        sys.excepthook(KeyboardInterrupt, interrupt, None)
    captured = capfd.readouterr()
    assert captured.err.strip() == f"WARNING: shelfsync.logs: {logs.CTRL_C_LINE}"
    assert secret not in captured.out + captured.err
    assert not log_file.exists() or "Uncaught" not in log_file.read_text(encoding="utf-8")


def test_ctrl_c_with_no_stderr_prints_nothing_and_does_not_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LOG-01: under pythonw `sys.stderr` is None."""
    with guards(), file_log(tmp_path):
        monkeypatch.setattr(sys, "stderr", None)
        sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)


def test_one_stderr_handler_is_reused_for_every_report(tmp_path: Path) -> None:
    """LOG-01 (R6): a failed write doesn't build a new handler each time."""
    with guards():
        first = logs._stderr_handler()
        assert logs.logging.lastResort is first
        assert logs._stderr_handler() is first


def test_the_first_failed_log_write_calls_the_notice_once(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """LOG-01 (R6): under pythonw nobody sees stderr, so the first failure also reaches the owner, once."""
    told: list[int] = []
    logs.set_write_failure_notice(lambda: told.append(1))
    try:
        with guards(), file_log(tmp_path), only_the_file_handler() as logger:
            logger.error("%s and %s", "x")
            logger.error("%s and %s", "y")
    finally:
        logs.set_write_failure_notice(None)
    assert told == [1]
    assert capfd.readouterr().err.count("A log line couldn't be written") == 2  # the stderr line is every time


def test_a_notice_that_fails_does_not_break_the_report(tmp_path: Path) -> None:
    """LOG-01 (R6)."""

    def broken() -> None:
        raise RuntimeError("no toast")

    logs.set_write_failure_notice(broken)
    try:
        with guards(), file_log(tmp_path), only_the_file_handler() as logger:
            logger.error("%s and %s", "x")  # must not raise
    finally:
        logs.set_write_failure_notice(None)


def test_a_rollover_that_windows_refuses_keeps_logging_into_the_current_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01 (R6): the stdlib closes the stream and, when the rename fails, leaves it closed, so every later line
    was lost. Now the file is reopened, the next try waits for the next rollover time, and the failure is reported."""
    told: list[int] = []
    logs.set_write_failure_notice(lambda: told.append(1))

    def refused(self: object, source: str, dest: str) -> None:
        raise PermissionError("file in use")

    try:
        with file_log(tmp_path) as log_file:
            handler = next(h for h in logging.getLogger().handlers if isinstance(h, logs.RedactingFileHandler))
            logging.getLogger("shelfsync.rollover").warning("before")
            monkeypatch.setattr(logs.RedactingFileHandler, "rotate", refused)
            handler.rolloverAt = int(time.time()) - 10  # a rollover is due now
            logging.getLogger("shelfsync.rollover").warning("during")
            logging.getLogger("shelfsync.rollover").warning("after")
            handler.flush()
            text = log_file.read_text(encoding="utf-8")
            assert handler.rolloverAt > time.time()
    finally:
        logs.set_write_failure_notice(None)
    assert "before" in text and "during" in text and "after" in text
    assert told == [1]
    assert "A log line couldn't be written (PermissionError)" in capfd.readouterr().err


@pytest.mark.parametrize("before", [False, True])
def test_removing_the_guards_restores_the_earlier_warnings_capture(before: bool) -> None:
    """LOG-01: captureWarnings goes back to what it was, not always to off."""
    logging.captureWarnings(before)
    try:
        logs.install_output_guards()
        logs.remove_output_guards()
        assert (warnings.showwarning.__module__ == "logging") is before
    finally:
        logs.remove_output_guards()
        logging.captureWarnings(False)


def _age(path: Path, days: int) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_the_second_launchs_handler_never_rotates_or_prunes_the_running_copys_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01 (review 2): a short-lived second process shares the file. A rotating handler built on an old file would
    rename it under the running copy (a refusal by Windows would toast a false "can't write its log"), and would prune
    with retention 30. The append handler only adds lines."""
    log_file = tmp_path / logs.LOG_FILE_NAME
    log_file.write_text('{"message": "from the running copy"}\n', encoding="utf-8")
    _age(log_file, 3)
    told: list[int] = []
    logs.set_write_failure_notice(lambda: told.append(1))

    def refused(self: object, source: str, dest: str) -> None:
        raise PermissionError("the running copy has it open")

    monkeypatch.setattr(logs.RedactingFileHandler, "rotate", refused)
    secret = key(50)
    handler = logs.configure_append_logging(tmp_path)
    try:
        logging.getLogger("shelfsync.launcher").warning("second launch %s", secret)
        handler.flush()
    finally:
        logs.remove_logging(handler)
        logs.set_write_failure_notice(None)
    assert [p.name for p in tmp_path.iterdir()] == [logs.LOG_FILE_NAME]  # nothing rotated, nothing pruned
    text = log_file.read_text(encoding="utf-8")
    assert "from the running copy" in text and "second launch" in text
    assert secret not in text  # still redacted
    assert told == []
    assert "couldn't be written" not in capfd.readouterr().err


def test_the_rotating_handler_on_the_same_old_file_would_have_rotated_it(tmp_path: Path) -> None:
    """LOG-01 (review 2): the control for the test above, so it can't pass for the wrong reason."""
    log_file = tmp_path / logs.LOG_FILE_NAME
    log_file.write_text('{"message": "from the running copy"}\n', encoding="utf-8")
    _age(log_file, 3)
    with file_log(tmp_path):
        logging.getLogger("shelfsync.launcher").warning("second launch")
    assert len(list(tmp_path.iterdir())) == 2  # the old file was renamed away


def test_the_append_handler_reports_a_failed_write_like_the_other_one(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """LOG-01: a bad-arguments record gives the fixed line, nothing from the record."""
    secret = key(51)
    handler = logs.configure_append_logging(tmp_path)
    logger = logging.getLogger("shelfsync.badappend")
    logger.handlers[:] = [handler]
    logger.propagate = False
    try:
        logger.error("%s and %s", secret)
    finally:
        logger.handlers.clear()
        logger.propagate = True
        logs.remove_logging(handler)
    captured = capfd.readouterr()
    assert "A log line couldn't be written (TypeError)" in captured.err
    assert secret not in captured.out + captured.err
