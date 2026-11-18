"""`python -m testenv.launch`: ShelfSync from source, on a **throwaway data folder**, reading the Laragon test site
(m3.2 item 8; [11] 2026-11-17, M3 Q1), so the exit test sees test-stack results in the real screens.

How it gets in without the app gaining a way in: it **builds the server itself** from the app's own parts, the way
`server._start` does, and hands the catalog service `testenv.catalog.site_clients` through its existing seam (the
client factory, `CatalogService(client_factory=...)`), and the stores service the site's transport through its existing
`transport=` argument. ShelfSync itself gains no setting, environment variable, flag or import: nothing under
`backend/shelfsync` imports `testenv` (`tests/test_testenv_launch.py` checks it, and that the release build ships no
`testenv`).

What it refuses or keeps apart:
- **the real data folder** (`%LOCALAPPDATA%\\ShelfSync`, or anything inside it): a new temporary folder is used unless
  `--data` names another one;
- **any store but the test site:** the client factory serves the site's address only, and every connection goes to
  127.0.0.1 for the site's host only (`laragon.LoopbackOnlyTransport`), so a store added in the screens is never read;
- **ShelfSync's own secrets:** the install token and the store's keys live in memory only (`MemorySecretStore`); the
  site's **Read** pair is read once from the harness's Credential Manager service (`ShelfSync-TestStack`), never
  written, never ShelfSync's own service;
- **the app's port:** it binds 127.0.0.1 on a free port outside 47615-47624, so a running ShelfSync is never touched.

The catalog service is built with its scheduler on (`scheduled=True`), so the incrementals and the night's snapshot
run as they would in the app. It prints the signed-in address (a single-use, 60-second ticket) and opens it unless
`--no-browser`. Developer tooling for the test stack: never shipped with the app.
"""

import argparse
import os
import socket
import sqlite3
import sys
import tempfile
import webbrowser
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from fastapi import FastAPI

from shelfsync.api.app import create_app
from shelfsync.api.app_settings import AppSettingsService
from shelfsync.catalog.service import CatalogService, WizardService
from shelfsync.db.connection import connect
from shelfsync.db.migrate import migrate
from shelfsync.db.stores import insert_store, list_live
from shelfsync.logs import configure_logging, remove_logging
from shelfsync.paths import DataPaths, create_data_folders, source_ui_dir
from shelfsync.platform.autostart import FakeRunKey
from shelfsync.platform.secrets import KeyringSecretStore, MemorySecretStore, SecretStore
from shelfsync.ports import DEFAULT_PORT, LAST_PORT
from shelfsync.secure.credentials import StoreCredentials
from shelfsync.secure.redact import register_secret
from shelfsync.secure.sessions import SessionStore, sign_in_url
from shelfsync.secure.token import InstallToken
from shelfsync.server import HOST, serve_with_uvicorn
from shelfsync.store_service import StoreService
from testenv.catalog import site_clients
from testenv.laragon import (
    DEFAULT_SITE,
    SERVICE,
    STORE_CODE,
    HarnessError,
    Site,
    TransportFactory,
    default_cert,
    make_transport,
    pairs_for,
    parse_site,
    read_pair,
    say,
    tls_context,
)

Serve = Callable[[FastAPI, socket.socket], None]


def real_data_folder() -> Path | None:
    """The app's own data folder (`paths.resolve_data_paths` without its override), when it can be known."""
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "ShelfSync" if local else None


def check_data_folder(folder: Path, real: Path | None) -> None:
    """`HarnessError` for the real data folder, a folder inside it, or one that holds it."""
    if real is None:
        return
    mine, theirs = folder.resolve(), real.resolve()
    if mine == theirs or theirs in mine.parents or mine in theirs.parents:
        raise HarnessError("That is (or holds) ShelfSync's real data folder. The launcher uses a throwaway one.")


def bind_free_port() -> socket.socket:
    """127.0.0.1 on a free port the system picks, never one of the app's 47615-47624."""
    for _ in range(20):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((HOST, 0))
        except OSError:
            sock.close()
            raise
        if not DEFAULT_PORT <= sock.getsockname()[1] <= LAST_PORT:
            sock.listen(128)
            return sock
        sock.close()
    raise HarnessError("No free port outside 47615-47624 was found.")


@dataclass
class Launch:
    """What `build` made: the app, its open socket, its services and its throwaway data folder."""

    app: FastAPI
    sock: socket.socket
    catalog: CatalogService
    stores: StoreService
    paths: DataPaths
    store_id: int
    handler: TimedRotatingFileHandler
    url: str


def _site_store(open_connection: Callable[[], sqlite3.Connection], site: Site) -> int:
    """The one store row: the test site (added once; a reused folder keeps its row)."""
    with closing(open_connection()) as connection:
        for row in list_live(connection):
            if row.url == site.url:
                return row.id
        return insert_store(
            connection,
            name="Test site",
            url=site.url,
            code=STORE_CODE,
            shape="circle",
            color="indigo",
            spacing_ms=150,
            main_button="Download",
            created_at="2026-11-18T00:00:00.000000Z",
        )


def build(
    site: Site,
    cert: Path,
    data: Path,
    harness_secrets: SecretStore,
    *,
    transport_factory: TransportFactory = make_transport,
    real: Path | None = None,
) -> Launch:
    """Build the server on `data` for `site` (the module text says how). Nothing is served yet."""
    check_data_folder(data, real)
    pair = read_pair(harness_secrets, pairs_for(site)[0])
    if pair is None:
        raise HarnessError(f"No read-only key pair is saved for {site.host}. Run the keys command first.")
    key, secret = pair
    register_secret(key)
    register_secret(secret)
    paths = DataPaths(data)
    create_data_folders(paths)
    handler = configure_logging(paths.logs, 1)
    try:

        def open_connection() -> sqlite3.Connection:
            return connect(paths.database)

        with closing(open_connection()) as connection:
            migrate(connection)
        store_id = _site_store(open_connection, site)
        app_secrets = MemorySecretStore()  # never Credential Manager's ShelfSync service
        StoreCredentials(app_secrets).save(store_id, key, secret)
        context = tls_context(cert)
        stores = StoreService(
            open_connection=open_connection, secrets=app_secrets, transport=transport_factory(context, site.host)
        )
        catalog = CatalogService(
            open_connection,
            site_clients(site, cert, harness_secrets, transport_factory),
            slots=stores.slots,
            scheduled=True,
        )
        sock = bind_free_port()
        port = sock.getsockname()[1]
        ui = source_ui_dir()
        app = create_app(
            port,
            InstallToken(app_secrets),
            ui_dir=ui if (ui / "index.html").is_file() else None,
            app_settings=AppSettingsService(open_connection, port, handler, FakeRunKey(), lambda: False),
            stores=stores,
            catalog=catalog,
            wizard=WizardService(open_connection, lambda: False),
        )
        sessions: SessionStore = app.state.sessions
        url = sign_in_url(port, sessions.issue_ticket())
    except BaseException:
        remove_logging(handler)
        raise
    return Launch(app, sock, catalog, stores, paths, store_id, handler, url)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m testenv.launch", description=__doc__.split("\n\n")[0])
    parser.add_argument("--site", default=DEFAULT_SITE, help=f"the test site (default {DEFAULT_SITE})")
    parser.add_argument("--cert", type=Path, default=None, help="the certificate to trust (default: the harness's)")
    parser.add_argument("--data", type=Path, default=None, help="the data folder (default: a new temporary one)")
    parser.add_argument("--no-browser", action="store_true", help="print the address only")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    secrets_factory: Callable[[], SecretStore] = lambda: KeyringSecretStore(SERVICE),
    serve: Serve = serve_with_uvicorn,
    open_browser: Callable[[str], object] = webbrowser.open,
    transport_factory: TransportFactory = make_transport,
) -> int:
    args = parse_args(argv)
    try:
        site = parse_site(args.site)
    except ValueError:
        say(f"{args.site!r} isn't the test site: use https:// on a name ending in .test.", sys.stderr)
        return 1
    data = args.data if args.data is not None else Path(tempfile.mkdtemp(prefix="shelfsync-launch-"))
    try:
        launch = build(
            site,
            args.cert if args.cert is not None else default_cert(site),
            data,
            secrets_factory(),
            transport_factory=transport_factory,
            real=real_data_folder(),
        )
    except HarnessError as error:
        say(str(error), sys.stderr)
        return 1
    say(f"ShelfSync (test stack) on a throwaway data folder: {launch.paths.root}")
    say(f"Sign in (single use, 60 seconds): {launch.url}")
    if not args.no_browser:
        open_browser(launch.url)
    try:
        serve(launch.app, launch.sock)
    except KeyboardInterrupt:
        pass
    finally:
        launch.sock.close()
        remove_logging(launch.handler)
    return 0


if __name__ == "__main__":
    sys.exit(main())
