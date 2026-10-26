"""SYS-03, ERR-06: the whole start (single instance first, clean exit, Ctrl+C) and the M1a.1 carry-overs."""

import socket
from pathlib import Path

import pytest
from fastapi import FastAPI

from shelfsync import logs, messages, server
from shelfsync.paths import DATA_DIR_ENV, DataPaths
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.token import INSTALL_TOKEN_NAME
from shelfsync.tray.instance import FakeInstanceLock
from tests.test_server import RecordingServe


def go(
    serve: server.Serve,
    taken: set[str] | None = None,
    second: server.SecondLaunch | None = None,
    store: MemorySecretStore | None = None,
    on_settings: server.OnSettings | None = None,
) -> tuple[int, FakeNotifier, list[DataPaths], MemorySecretStore, FakeInstanceLock]:
    notifier = FakeNotifier()
    seen: list[DataPaths] = []

    def on_second(paths: DataPaths) -> int:
        seen.append(paths)
        return 0 if second is None else second(paths)

    secrets_store = store if store is not None else MemorySecretStore()
    lock = FakeInstanceLock(taken if taken is not None else set())
    code = server.run_application(
        serve, notifier, on_second, lock=lock, secrets=secrets_store, on_settings=on_settings, retry_seconds=0.0
    )
    return code, notifier, seen, secrets_store, lock


def test_the_first_copy_runs_holds_the_lock_while_serving_and_frees_it_after(data_paths: DataPaths) -> None:
    """SYS-03."""
    taken: set[str] = set()
    during: list[bool] = []

    def serve(app: FastAPI, sock: socket.socket) -> None:
        during.append("ShelfSync" in taken)

    code, notifier, seen, _, _ = go(serve, taken)
    assert code == server.EXIT_OK and during == [True]
    assert seen == [] and notifier.messages == []
    assert taken == set()


def test_a_second_launch_touches_nothing_and_never_starts_a_server(data_paths: DataPaths) -> None:
    """SYS-03 (M1a.1 re-check, medium): it doesn't empty the first copy's tmp, make a database, create the install
    token or bind a port."""
    data_paths.tmp.mkdir(parents=True)
    keep = data_paths.tmp / "running-job.zip"
    keep.write_bytes(b"x")
    serve = RecordingServe()
    store = MemorySecretStore()
    code, _, seen, _, _ = go(serve, taken={"ShelfSync"}, second=lambda paths: 17, store=store)
    assert code == 17  # whatever the second-launch handler returns
    assert seen == [data_paths]
    assert keep.exists()  # tmp\ untouched
    assert not data_paths.database.exists()
    assert not data_paths.logs.exists()
    assert store.get(INSTALL_TOKEN_NAME) is None  # only the lock holder may create the token (M1a.2 review #6)
    assert serve.sockname is None and serve.app is None


def test_runtime_json_is_removed_on_a_clean_exit(data_paths: DataPaths) -> None:
    """SYS-03 (M1a.1 #12)."""
    serve = RecordingServe()
    code, *_ = go(serve)
    assert code == server.EXIT_OK
    assert serve.runtime_json is not None  # it was there while serving
    assert not data_paths.runtime_json.exists()


def test_runtime_json_is_removed_when_serving_fails(data_paths: DataPaths) -> None:
    """SYS-03: also after a crash while serving."""

    def serve(app: FastAPI, sock: socket.socket) -> None:
        raise RuntimeError("the server fell over")

    code, notifier, *_ = go(serve)
    assert code == server.EXIT_START_FAILED
    assert notifier.messages == [messages.START_FAILED]
    assert not data_paths.runtime_json.exists()


def test_a_leftover_runtime_json_is_removed_before_the_port_is_bound(data_paths: DataPaths) -> None:
    """SYS-03 (M1a.1 #12): a crash left it; the lock holder is the only live copy, so it is stale. When no port can
    be bound it must not stay behind pointing a second launch at a dead port."""
    data_paths.root.mkdir(parents=True)
    data_paths.runtime_json.write_text('{"port": 47615, "pid": 1}', encoding="utf-8")
    held = []
    for port in range(47615, 47625):
        sock = socket.socket()
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
        held.append(sock)
    try:
        code, *_ = go(RecordingServe())
    finally:
        for sock in held:
            sock.close()
    assert code == server.EXIT_PORTS_IN_USE
    assert not data_paths.runtime_json.exists()


def test_ctrl_c_is_a_normal_stop_with_exit_0_and_one_fixed_line(
    data_paths: DataPaths, capfd: pytest.CaptureFixture[str]
) -> None:
    """SYS-03 (M1a.1 carry-over, M1a.2 re-check R2): no traceback, exit 0, the lock freed, runtime.json removed."""
    logs.install_output_guards()
    try:

        def serve(app: FastAPI, sock: socket.socket) -> None:
            raise KeyboardInterrupt

        taken: set[str] = set()
        code, *_ = go(serve, taken)
    finally:
        logs.remove_output_guards()
    assert code == server.EXIT_OK
    assert taken == set()
    assert not data_paths.runtime_json.exists()
    err = capfd.readouterr().err
    assert err.strip() == f"WARNING: shelfsync.logs: {logs.CTRL_C_LINE}"


def test_ctrl_c_during_a_second_launch_is_also_exit_0(data_paths: DataPaths) -> None:
    """SYS-03."""

    def interrupted(paths: DataPaths) -> int:
        raise KeyboardInterrupt

    code, *_ = go(RecordingServe(), taken={"ShelfSync"}, second=interrupted)
    assert code == server.EXIT_OK


def test_an_unknown_data_folder_is_a_plain_exit_code_with_its_own_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    """ERR-06 (M1a.1 carry-over): `resolve_data_paths()` is inside the start-up try, so the default excepthook never
    prints a traceback."""
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    code, notifier, seen, *_ = go(RecordingServe())
    assert code == server.EXIT_START_FAILED
    assert notifier.messages == [messages.START_FAILED_DATA_FOLDER]
    assert seen == []


def test_a_data_folder_that_cant_be_made_doesnt_point_to_a_missing_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ERR-06 (M1a.1 carry-over): there is no log yet, so the notice says so in other words."""
    blocker = tmp_path / "file-in-the-way"
    blocker.write_text("x")
    monkeypatch.setenv(DATA_DIR_ENV, str(blocker / "ShelfSync"))
    code, notifier, *_ = go(RecordingServe())
    assert code == server.EXIT_START_FAILED
    assert notifier.messages == [messages.START_FAILED_DATA_FOLDER]
    assert "shelfsync.log" not in messages.START_FAILED_DATA_FOLDER
    assert messages.START_FAILED not in notifier.messages


def test_the_settings_reach_the_hook_after_logging_is_up(data_paths: DataPaths) -> None:
    """SYS-04: the launcher applies Start with Windows from the settings (default on)."""
    seen: list[dict[str, object]] = []
    code, *_ = go(RecordingServe(), on_settings=seen.append)
    assert code == server.EXIT_OK
    assert seen[0]["start_with_windows"] is True and seen[0]["notifications"] is True


def test_a_settings_hook_that_raises_is_a_start_up_failure_not_a_traceback(data_paths: DataPaths) -> None:
    """SYS-04: the launcher's hook catches its own errors, but a bug in one must still end in an exit code."""

    def broken(settings: dict[str, object]) -> None:
        raise RuntimeError("boom")

    code, notifier, *_ = go(RecordingServe(), on_settings=broken)
    assert code == server.EXIT_START_FAILED and notifier.messages == [messages.START_FAILED]


def test_the_developer_entry_says_so_when_already_running_and_exits_0(
    data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """SYS-03: `python -m shelfsync` while ShelfSync runs: no second server, exit 0."""
    taken = {"ShelfSync"}
    monkeypatch.setattr(server, "default_instance_lock", lambda: FakeInstanceLock(taken))
    monkeypatch.setattr(server, "install_output_guards", lambda: None)
    with caplog.at_level("WARNING", logger="shelfsync.server"):
        assert server.main() == server.EXIT_OK
    assert "already running" in caplog.text
    assert not data_paths.database.exists()
