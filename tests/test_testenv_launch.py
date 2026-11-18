"""m3.2 item 8: the test-only launcher (`testenv/launch.py`), offline (a fake WooCommerce behind the site's transport
seam, a certificate made here): it builds ShelfSync on a throwaway folder with its scheduler on, binds 127.0.0.1 off the
app's ports, refuses the real data folder, serves the test site only, and never writes the harness's keys. And the
shipped app has no way in: nothing under `backend/shelfsync` imports `testenv`, the release build copies no `testenv`,
and the app reads no new environment variable."""

import ast
import importlib.util
import os
import ssl
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from shelfsync.catalog.runner import RunPlan
from shelfsync.db.connection import connect
from shelfsync.db.stores import insert_store
from shelfsync.logs import remove_logging
from shelfsync.ports import DEFAULT_PORT, LAST_PORT
from testenv import laragon, launch
from tests.laragon_support import RO_KEY, RO_SECRET, SITE, store_with_keys, write_site_cert
from tests.sync_support import FakeSyncStore, row

REPO = Path(__file__).resolve().parents[1]
SHIPPED = REPO / "backend" / "shelfsync"
SITE_URL = f"https://{SITE}"


# ---- the shipped app has no way in ---------------------------------------------------------------------------------


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in (
            "import_module",
            "__import__",
        ):
            found.update(arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
    return found


def test_nothing_the_app_ships_imports_testenv() -> None:
    offenders = [
        str(path.relative_to(REPO))
        for path in sorted(SHIPPED.rglob("*.py"))
        if any(name == "testenv" or name.startswith("testenv.") for name in _imports(path))
    ]
    assert offenders == []
    assert not any("testenv" in path.read_text(encoding="utf-8") for path in SHIPPED.rglob("*.py") if path.suffix)


def _load_build() -> ModuleType:
    spec = importlib.util.spec_from_file_location("shelfsync_packaging_build", REPO / "packaging" / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_release_build_copies_no_testenv(tmp_path: Path) -> None:
    """The build copies `backend/shelfsync` (and the UI, the icons, the wheels): its file list holds no `testenv`."""
    build = _load_build()
    assert "testenv" not in (REPO / "packaging" / "build.py").read_text(encoding="utf-8")
    target = tmp_path / "app" / "shelfsync"
    build.copy_tree(SHIPPED, target)
    names = [entry.path for entry in build.file_listing(tmp_path / "app")]
    assert names and not [name for name in names if "testenv" in name]


ENVIRON_READS = Counter({"paths.py": 2, "junction.py": 1, "layout.py": 1})  # SHELFSYNC_DATA_DIR, LOCALAPPDATA, ...


def test_the_app_reads_no_new_environment_variable() -> None:
    """`os.environ` and `os.getenv` in shipped code, by file: exactly the reads that were there before m3.2."""
    found: Counter[str] = Counter()
    for path in SHIPPED.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv", "putenv"):
                found[path.name] += 1
    assert found == ENVIRON_READS


# ---- the launcher --------------------------------------------------------------------------------------------------


@pytest.fixture
def cert(tmp_path: Path) -> Path:
    return write_site_cert(tmp_path / "trust", laragon.make_site_certificate(SITE))


def fake_transports(store: FakeSyncStore) -> laragon.TransportFactory:
    def make(context: ssl.SSLContext, host: str) -> httpx.BaseTransport:
        return laragon.LoopbackOnlyTransport(httpx.MockTransport(store), host)

    return make


def test_it_builds_shelfsync_on_a_throwaway_folder_with_its_scheduler_on(tmp_path: Path, cert: Path) -> None:
    store = FakeSyncStore(rows=[row(1, "aurora")])
    harness = store_with_keys()
    before = dict(harness._values)
    made = launch.build(
        laragon.parse_site(SITE_URL),
        cert,
        tmp_path / "data",
        harness,
        transport_factory=fake_transports(store),
        real=tmp_path / "real" / "ShelfSync",
    )
    try:
        host, port = made.sock.getsockname()
        assert host == "127.0.0.1" and not DEFAULT_PORT <= port <= LAST_PORT
        assert made.catalog._scheduled is True
        assert made.paths.database.is_file() and made.paths.root == tmp_path / "data"
        assert made.url.startswith(f"http://127.0.0.1:{port}/#t=")
        assert RO_KEY not in made.url and RO_SECRET not in made.url
        assert made.catalog.start_sync("full") == "full"
        made.catalog.runner.join(30.0)
        assert made.catalog.runner.state().outcomes == {made.store_id: None}
        auth = {request.headers["Authorization"] for request in store.requests}
        assert len(auth) == 1  # the site's Read pair, and nothing else
        assert made.stores.test(made.store_id).outcome.ok  # Test connection through the site's transport too
        assert dict(harness._values) == before  # the harness's keys never written
    finally:
        made.sock.close()
        remove_logging(made.handler)


def test_it_reads_no_store_but_the_test_site(tmp_path: Path, cert: Path) -> None:
    store = FakeSyncStore(rows=[row(1)])
    made = launch.build(
        laragon.parse_site(SITE_URL),
        cert,
        tmp_path / "data",
        store_with_keys(),
        transport_factory=fake_transports(store),
    )
    try:
        with closing(connect(made.paths.database)) as connection:
            other = insert_store(
                connection,
                name="A real store",
                url="https://store-a.example",
                code="SA",
                shape="circle",
                color="indigo",
                spacing_ms=150,
                main_button="Download",
                created_at="2026-11-18T00:00:00.000000Z",
            )
        assert made.catalog.runner.start(RunPlan("full", stores=frozenset({other})))
        made.catalog.runner.join(30.0)
        assert made.catalog.runner.state().outcomes == {other: "internal"}  # the factory refused it
        assert store.requests == []
    finally:
        made.sock.close()
        remove_logging(made.handler)


@pytest.mark.parametrize("where", ["itself", "inside", "holding"])
def test_it_refuses_the_real_data_folder(tmp_path: Path, cert: Path, where: str) -> None:
    real = tmp_path / "Local" / "ShelfSync"
    data = {"itself": real, "inside": real / "x", "holding": tmp_path / "Local"}[where]
    with pytest.raises(laragon.HarnessError, match="real data folder"):
        launch.build(laragon.parse_site(SITE_URL), cert, data, store_with_keys(), real=real)
    assert not real.exists()


def test_main_refuses_the_real_folder_by_its_windows_place(
    tmp_path: Path, cert: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    served: list[object] = []
    code = launch.main(
        ["--data", str(tmp_path / "Local" / "ShelfSync"), "--cert", str(cert), "--no-browser"],
        secrets_factory=store_with_keys,
        serve=lambda app, sock: served.append(app),
    )
    assert code == 1 and served == [] and "real data folder" in capsys.readouterr().err


def test_main_refuses_a_site_that_isnt_a_test_site(capsys: pytest.CaptureFixture[str]) -> None:
    assert launch.main(["--site", "https://gplfamily.example", "--no-browser"], secrets_factory=store_with_keys) == 1
    assert "isn't the test site" in capsys.readouterr().err


def test_main_serves_and_opens_the_signed_in_address(
    tmp_path: Path, cert: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    served: list[tuple[object, int]] = []
    opened: list[str] = []
    code = launch.main(
        ["--data", str(tmp_path / "throwaway"), "--cert", str(cert)],
        secrets_factory=store_with_keys,
        serve=lambda app, sock: served.append((app, sock.getsockname()[1])),
        open_browser=opened.append,
        transport_factory=fake_transports(FakeSyncStore(rows=[row(1)])),
    )
    assert code == 0 and len(served) == 1
    [url] = opened
    assert url.startswith(f"http://127.0.0.1:{served[0][1]}/#t=")


def test_without_the_read_pair_it_stops_before_making_anything(tmp_path: Path, cert: Path) -> None:
    from shelfsync.platform.secrets import MemorySecretStore

    with pytest.raises(laragon.HarnessError, match="read-only key pair"):
        launch.build(laragon.parse_site(SITE_URL), cert, tmp_path / "data", MemorySecretStore())
    assert not (tmp_path / "data").exists()


def test_it_is_run_as_a_module_from_testenv_only() -> None:
    assert (REPO / "testenv" / "launch.py").is_file()
    assert os.path.basename(launch.__file__) == "launch.py"
