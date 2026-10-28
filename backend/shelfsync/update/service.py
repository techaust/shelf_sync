"""The update service (SYS-06, SYS-07, SET-04): what the Updates API talks to.

- A check 60 s after start, then every 24 h, and on "Check now" (refused for 60 s after a check). A found update is
  downloaded, verified (signature first) and unpacked in the background. Installing happens only when the owner
  asks.
- One install or roll back at a time (409 otherwise). A kept folder is re-checked against its signed manifest, file by
  file, before any switch to it.
- The switch itself is a separate process (`switch.py`) started from the version being left; this service starts it,
  then asks the tray to quit through `app.state.request_quit` (published by the launcher). With no such function (the
  developer entry) or a refusal, the switcher is ended and the answer is 409.
- A copy that isn't installed (no install layout, `layout.py`) is the *development* service: it reports
  `development: true`, makes no network call, and refuses check, install and roll back with 409.
- The optional GitHub token lives in Credential Manager (`github-token`), is written but never read back through the
  API, and is registered with the log redaction when it is set and at start.
"""

import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import httpx

from shelfsync import __version__
from shelfsync.clock import to_iso, utc_now
from shelfsync.db.backup import check_backup, database_schema
from shelfsync.paths import DataPaths
from shelfsync.platform.junction import DirectoryLinks, default_links
from shelfsync.platform.process import Processes, default_processes
from shelfsync.platform.secrets import MemorySecretStore, SecretStore, SecretStoreError
from shelfsync.secure.credentials import SECRETS_WRITE_LOCK
from shelfsync.secure.redact import register_secret
from shelfsync.update import release_key
from shelfsync.update.download import (
    DownloadFailed,
    clear_downloads,
    download_zip,
    fetch_signature,
    fetch_small,
    free_bytes,
)
from shelfsync.update.github import (
    CheckResult,
    DownloadRefused,
    GitHubClient,
    Outcome,
    Release,
    expiry_notice,
    parse_expiry,
)
from shelfsync.update.kept import KeptVersionError, load_manifest, verify_kept_version, write_manifest
from shelfsync.update.layout import InstallLayout, UpdatePaths, resolve_install_layout
from shelfsync.update.manifest import (
    MANIFEST_NAME,
    MAX_MANIFEST_BYTES,
    SIGNATURE_NAME,
    Manifest,
    ManifestError,
    check_acceptable,
    check_is_version,
    verify_and_parse,
    zip_asset_name,
)
from shelfsync.update.state import LastCheck, PendingUpdate, ResultStore, State, StateStore, SwitchResult
from shelfsync.update.switch import SWITCH_FORMAT, repair_current
from shelfsync.update.unpack import UnpackError, remove_incoming_leftovers, unpack_release
from shelfsync.update.versions import is_newer

_log = logging.getLogger("shelfsync.update")

GITHUB_TOKEN_ENTRY = "github-token"  # the Credential Manager entry's name, not a secret  # nosec B105
# Fine-grained tokens only (owner decision, M1b.2 brief 8): `github_pat_` and 20 to 255 more characters.
_TOKEN_SHAPE = re.compile(r"github_pat_[A-Za-z0-9_]{20,255}")

FIRST_CHECK_SECONDS = 60.0
CHECK_EVERY_SECONDS = 24 * 3600.0
CHECK_NOW_COOLDOWN_SECONDS = 60.0


class UpdateConflict(Exception):
    """The request can't be done now: the API answers 409. `code`: `development_build`, `busy`, `no_key`,
    `nothing_to_install`, `no_previous`, `no_backup`, `files_changed`, `manifest_invalid`, `manifest_missing`,
    `cannot_restart`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class UpdateTooSoon(Exception):
    """A check was asked for within 60 s of the last one: the API answers 429."""


class UpdateNeedsConfirmation(Exception):
    """A roll back that loses data needs `confirm_data_loss`: the API answers 422."""


class InvalidToken(ValueError):
    """The value isn't a fine-grained GitHub token. The message never holds the value."""


@dataclass(frozen=True)
class TokenStatus:
    is_set: bool
    expires_at: str | None
    notice: bool


@dataclass(frozen=True)
class Available:
    version: str
    ready: bool


@dataclass(frozen=True)
class UpdateStatus:
    development: bool
    key_available: bool
    installed: str
    previous: str | None
    can_roll_back: bool
    database_changed: bool
    backup_at: str | None
    backup_available: bool
    checking: bool
    busy: bool
    last_check: LastCheck | None
    available: Available | None
    token: TokenStatus
    last_result: SwitchResult | None


def is_valid_token(value: str) -> bool:
    return _TOKEN_SHAPE.fullmatch(value) is not None


Starter = Callable[[Callable[[], None]], None]


def _thread_starter(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="update-check", daemon=True).start()


class UpdateService:
    def __init__(
        self,
        *,
        secrets: SecretStore,
        paths: DataPaths | None = None,
        layout: InstallLayout | None = None,
        github: GitHubClient | None = None,
        installed_version: str = __version__,
        links: DirectoryLinks | None = None,
        processes: Processes | None = None,
        now: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        starter: Starter = _thread_starter,
        free: Callable[[Path], int] = free_bytes,
    ) -> None:
        self._secrets = secrets
        self._paths = paths
        self._layout = layout
        self._installed = installed_version
        self._links = links or default_links()
        self._processes = processes or default_processes()
        self._now = now
        self._monotonic = monotonic
        self._starter = starter
        self._free = free
        self._github = github or GitHubClient(self._token)
        self._quit_provider: Callable[[], Callable[[], bool] | None] = lambda: None
        self._action_lock = threading.Lock()  # one install or roll back at a time
        self._check_lock = threading.Lock()  # one check at a time
        self._checking = False
        self._switching = False
        self._switch_started: str | None = None
        self._last_check_started: float | None = None
        self._available: Available | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if paths is not None:
            update_paths = UpdatePaths(paths)
            self._store: StateStore | None = StateStore(update_paths)
            self._results: ResultStore | None = ResultStore(update_paths)
        else:
            self._store = None
            self._results = None

    @classmethod
    def development(cls, secrets: SecretStore | None = None, paths: DataPaths | None = None) -> UpdateService:
        """The service for a copy that isn't installed: no layout, no network."""
        return cls(secrets=secrets if secrets is not None else MemorySecretStore(), paths=paths)

    @property
    def is_development(self) -> bool:
        return self._layout is None

    def bind_quit(self, provider: Callable[[], Callable[[], bool] | None]) -> None:
        """`provider()` returns the app's `request_quit` (or None). Looked up at the moment of use: the launcher may
        publish it after the app is built."""
        self._quit_provider = provider

    # ---- the token -------------------------------------------------------------------------------------------------

    def _token(self) -> str | None:
        try:
            return self._secrets.get(GITHUB_TOKEN_ENTRY)
        except SecretStoreError as error:
            _log.warning("The GitHub token couldn't be read (%s); checking without it", type(error).__name__)
            return None

    def set_token(self, value: str) -> None:
        if not is_valid_token(value):
            raise InvalidToken("not a fine-grained GitHub token")
        with SECRETS_WRITE_LOCK:  # not while a backup import is writing or putting back the same entry
            self._secrets.set(GITHUB_TOKEN_ENTRY, value)
            register_secret(value)
            self.forget_expiry()

    def delete_token(self) -> None:
        with SECRETS_WRITE_LOCK:
            self._secrets.delete(GITHUB_TOKEN_ENTRY)
            self.forget_expiry()

    def forget_expiry(self) -> None:
        """The stored token's expiry no longer says anything (the token was replaced or removed): forget it. The backup
        import calls this after it commits a token."""
        if self._store is not None:
            self._store.update(lambda state: replace(state, token_expires_at=None))

    def token_status(self) -> TokenStatus:
        token = self._token()
        state = self._store.load() if self._store is not None else State()
        expires = parse_expiry(state.token_expires_at) if token and state.token_expires_at else None
        return TokenStatus(token is not None, to_iso(expires) if expires else None, expiry_notice(expires, self._now()))

    # ---- status ----------------------------------------------------------------------------------------------------

    def status(self) -> UpdateStatus:
        state = self._store.load() if self._store is not None else State()
        layout = self._layout
        previous = state.previous
        can_roll_back = (
            layout is not None
            and previous is not None
            and layout.version_dir(previous).is_dir()
            and layout.manifest_path(previous).is_file()
        )
        # "The database changed" is decided by schema numbers, never by times: the database's highest migration is
        # above the previous version's `schema_version` (from its signed manifest). The backup that undoes it is the
        # recorded one only if it goes from the previous version's schema to the database's.
        previous_schema = (
            self._previous_schema(layout, previous) if can_roll_back and layout is not None and previous else None
        )
        database = database_schema(self._paths.database) if self._paths is not None else None
        changed = previous_schema is not None and database is not None and database > previous_schema
        record = state.backup
        matching = (
            record is not None and changed and record.from_schema == previous_schema and record.to_schema == database
        )
        backup_ok = matching and record is not None and Path(record.path).is_file()
        result = self._results.load() if self._results is not None else None
        if (
            self._switching
            and result is not None
            and self._switch_started is not None
            and result.at >= self._switch_started
        ):
            # the switch has reported and this copy is still running, so nothing was switched: the owner may try again
            self._switching = False
        available = self._available
        if available is None and state.pending is not None:
            available = Available(state.pending.version, True)
        return UpdateStatus(
            development=layout is None,
            key_available=release_key.PUBLIC_KEY is not None,
            installed=self._installed,
            previous=previous if can_roll_back else None,
            can_roll_back=bool(can_roll_back),
            database_changed=bool(changed),
            backup_at=record.at if matching and record is not None else None,
            backup_available=bool(backup_ok),
            checking=self._checking,
            busy=self._switching,
            last_check=state.last_check,
            available=available,
            token=self.token_status(),
            last_result=result,
        )

    # ---- start and stop --------------------------------------------------------------------------------------------

    def start(self) -> None:
        """At application start: register the token for redaction, then (installed copies only) clear what a crashed
        update left (downloads, `.incoming-*`, a stale `current.next` or `current.old`), tidy the state, and begin the
        check schedule. A missing `current` is not repaired here (an app that is running was started through it): every
        switcher run repairs it, and so does Setup.exe. Nothing in the tidy-up may stop the schedule or the app."""
        token = self._token()
        if token:
            register_secret(token)
        layout, paths = self._layout, self._paths
        if layout is None or paths is None or self._store is None:
            return
        try:
            clear_downloads(UpdatePaths(paths).downloads)
            remove_incoming_leftovers(layout)
            if repair_current(layout, self._links):
                _log.warning("The current link had leftovers or was missing, and was repaired")
            self._reconcile_state(layout)
        except Exception as error:  # nothing here may stop the app or the schedule; the type only is logged
            _log.warning("Update start-up tidying failed: %s", type(error).__name__)
        self._thread = threading.Thread(target=self._loop, name="update-schedule", daemon=True)
        self._thread.start()

    def _reconcile_state(self, layout: InstallLayout) -> None:
        installed = self._installed

        def change(state: State) -> State:
            previous = state.previous
            if previous is not None and (previous == installed or not layout.version_dir(previous).is_dir()):
                previous = None
            pending = state.pending
            if pending is not None and (
                not is_newer(pending.version, installed)
                or not layout.version_dir(pending.version).is_dir()
                or not layout.manifest_path(pending.version).is_file()
                or not layout.signature_path(pending.version).is_file()
            ):
                pending = None  # nothing to install any more: the folder or its signed manifest is gone
            return replace(state, installed=installed, previous=previous, pending=pending, switch=None)

        if self._store is not None:
            self._store.update(change)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)

    def _loop(self) -> None:
        delay = FIRST_CHECK_SECONDS
        while not self._stop.wait(delay):
            self.run_check()
            delay = CHECK_EVERY_SECONDS

    # ---- checking --------------------------------------------------------------------------------------------------

    def check_now(self) -> None:
        """Start a check in the background. UpdateConflict if development or busy, UpdateTooSoon within 60 s."""
        self._require_installed()
        if self._switching:
            raise UpdateConflict("busy")
        started = self._last_check_started
        if self._checking or (started is not None and self._monotonic() - started < CHECK_NOW_COOLDOWN_SECONDS):
            raise UpdateTooSoon
        self._last_check_started = self._monotonic()
        self._starter(self.run_check)

    def run_check(self) -> None:
        """One check, start to finish: GitHub's latest release, then (if newer) its manifest, signature and zip,
        verified and unpacked. Every failure is recorded in `last_check` as a fixed code; nothing is installed."""
        layout, store = self._layout, self._store
        if layout is None or store is None or not self._check_lock.acquire(blocking=False):
            return
        self._checking = True
        self._last_check_started = self._monotonic()
        try:
            result = self._github.latest()
            self._record(result.outcome.value, None, result)
            if result.outcome is not Outcome.OK or result.release is None:
                return
            self._after_release(result.release, layout, store)
        except Exception:  # a failure here must never stop the schedule
            _log.exception("The update check failed unexpectedly")
            self._record("update_failed", "unexpected", None)
        finally:
            self._checking = False
            self._check_lock.release()

    def _record(self, outcome: str, detail: str | None, result: CheckResult | None) -> None:
        if self._store is None:
            return
        moment = to_iso(self._now())
        expires = result.token_expires_at if result is not None else None
        had_token = result is not None and self._token() is not None

        def change(state: State) -> State:
            expiry = state.token_expires_at
            if result is not None:  # a check ran: the header answers for the token in use now
                expiry = to_iso(expires) if (expires is not None and had_token) else None
            return replace(state, last_check=LastCheck(moment, outcome, detail), token_expires_at=expiry)

        self._store.update(change)

    def _after_release(self, release: Release, layout: InstallLayout, store: StateStore) -> None:
        version = release.tag[1:]
        if release_key.PUBLIC_KEY is None:
            self._available = Available(version, False) if is_newer(version, self._installed) else None
            return  # no key in this build: nothing could be verified, so nothing is downloaded
        self._ensure_own_manifest(release, layout)
        if not is_newer(version, self._installed):
            self._available = None
            return
        pending = store.load().pending
        if pending is not None and pending.version == version and layout.version_dir(version).is_dir():
            self._available = Available(version, True)
            return
        self._available = Available(version, False)
        try:
            self._fetch_update(release, version, layout, store)
        except ManifestError as error:
            self._record("update_refused", error.code, None)
        except UnpackError as error:
            self._record("update_refused" if error.code != "disk_error" else "update_failed", error.code, None)
        except DownloadFailed as error:
            refused = error.code in ("hash_mismatch", "size_mismatch", "too_large", "bad_name")
            self._record("update_refused" if refused else "update_failed", error.code, None)
        except DownloadRefused as error:
            self._record("update_refused" if error.code == "host_not_allowed" else "update_failed", error.code, None)

    def _fetch_update(self, release: Release, version: str, layout: InstallLayout, store: StateStore) -> None:
        if self._paths is None:
            raise UpdateConflict("development_build")
        manifest_asset = release.assets.get(MANIFEST_NAME)
        signature_asset = release.assets.get(SIGNATURE_NAME)
        zip_asset = release.assets.get(zip_asset_name(version))
        if manifest_asset is None or signature_asset is None or zip_asset is None:
            self._record("update_refused", "assets_missing", None)
            return
        manifest_bytes = fetch_small(self._github, manifest_asset, MAX_MANIFEST_BYTES)
        signature = fetch_signature(self._github, signature_asset)
        manifest = verify_and_parse(manifest_bytes, signature)  # the signature first, then the parse
        check_acceptable(manifest, installed=self._installed, release_tag=release.tag)
        downloads = UpdatePaths(self._paths).downloads
        archive = download_zip(
            self._github, zip_asset, manifest.assets[zip_asset.name], downloads, layout.root, self._free
        )
        try:
            folder = unpack_release(archive, manifest, layout)
        finally:
            archive.unlink(missing_ok=True)
        write_manifest(layout, version, manifest_bytes, signature)
        verified = to_iso(self._now())
        store.update(lambda state: replace(state, pending=PendingUpdate(version, str(folder), verified)))
        self._available = Available(version, True)
        _log.info("Update %s was downloaded and verified; it waits for the owner's go-ahead", version)

    def _ensure_own_manifest(self, latest: Release, layout: InstallLayout) -> None:
        """The first install (by Setup.exe) has no manifest on disk: fetch the running version's own signed manifest
        from its release, verify it and keep it, so a later roll back to this version can be checked."""
        installed = self._installed
        if layout.manifest_path(installed).is_file() and layout.signature_path(installed).is_file():
            return
        try:
            release = latest
            if latest.tag != f"v{installed}":
                found = self._github.release_for(installed)
                if found.outcome is not Outcome.OK or found.release is None:
                    return
                release = found.release
            manifest_asset = release.assets.get(MANIFEST_NAME)
            signature_asset = release.assets.get(SIGNATURE_NAME)
            if manifest_asset is None or signature_asset is None:
                return
            manifest_bytes = fetch_small(self._github, manifest_asset, MAX_MANIFEST_BYTES)
            signature = fetch_signature(self._github, signature_asset)
            manifest = verify_and_parse(manifest_bytes, signature)
            check_is_version(manifest, version=installed, release_tag=f"v{installed}")
            write_manifest(layout, installed, manifest_bytes, signature)
        except (ManifestError, DownloadFailed, DownloadRefused, httpx.HTTPError, OSError) as error:
            _log.warning("The running version's manifest could not be kept (%s)", getattr(error, "code", "io"))

    # ---- install and roll back -------------------------------------------------------------------------------------

    def _require_installed(self) -> InstallLayout:
        if self._layout is None or self._paths is None or self._store is None:
            raise UpdateConflict("development_build")
        return self._layout

    def install(self) -> None:
        layout = self._require_installed()
        if release_key.PUBLIC_KEY is None:
            raise UpdateConflict("no_key")
        if self._store is None:
            raise UpdateConflict("development_build")
        if self._switching or not self._action_lock.acquire(blocking=False):
            raise UpdateConflict("busy")
        try:
            pending = self._store.load().pending
            if pending is None or not is_newer(pending.version, self._installed):
                raise UpdateConflict("nothing_to_install")
            self._check_kept(layout, pending.version)
            self._launch("install", pending.version, restore=False)
        finally:
            self._action_lock.release()

    def rollback(self, confirm_data_loss: bool) -> None:
        layout = self._require_installed()
        if release_key.PUBLIC_KEY is None:
            raise UpdateConflict("no_key")
        paths = self._paths
        if self._store is None or paths is None:
            raise UpdateConflict("development_build")
        if self._switching or not self._action_lock.acquire(blocking=False):
            raise UpdateConflict("busy")
        try:
            status = self.status()
            if not status.can_roll_back or status.previous is None:
                raise UpdateConflict("no_previous")
            manifest = self._check_kept(layout, status.previous)
            database = database_schema(paths.database)
            restore = database is not None and database > manifest.schema_version
            if restore:
                record = self._store.load().backup
                if (
                    record is None
                    or record.from_schema != manifest.schema_version
                    or record.to_schema != database
                    or not check_backup(Path(record.path), record.from_schema)
                ):
                    raise UpdateConflict("no_backup")  # without the right backup the old version couldn't open the data
                if not confirm_data_loss:
                    raise UpdateNeedsConfirmation
            self._launch("rollback", status.previous, restore=restore)
        finally:
            self._action_lock.release()

    def _previous_schema(self, layout: InstallLayout, version: str) -> int | None:
        """The previous version's `schema_version` from its signature-checked manifest, or None if that can't be had."""
        try:
            return load_manifest(layout, version).schema_version
        except KeptVersionError:
            return None

    def _check_kept(self, layout: InstallLayout, version: str) -> Manifest:
        try:
            return verify_kept_version(layout, version)
        except KeptVersionError as error:
            _log.warning("Version %s was refused before a switch (%s)", version, error.code)
            raise UpdateConflict("manifest_invalid" if error.code == "no_key" else error.code) from None

    def _launch(self, mode: str, target: str, *, restore: bool) -> None:
        layout, paths = self._layout, self._paths
        if layout is None or paths is None:
            raise UpdateConflict("development_build")
        request_quit = self._quit_provider()
        if request_quit is None:
            raise UpdateConflict("cannot_restart")  # the developer entry has no tray to ask
        interpreter = layout.interpreter(self._installed)
        if not interpreter.is_file():
            raise UpdateConflict("cannot_restart")
        argv = [
            str(interpreter),
            "-m",
            "shelfsync.update.switch",
            "--format",
            str(SWITCH_FORMAT),
            "--mode",
            mode,
            "--from",
            self._installed,
            "--to",
            target,
            "--install-root",
            str(layout.root),
            "--data-dir",
            str(paths.root),
            "--old-pid",
            str(os.getpid()),
        ]
        if restore:
            argv.append("--restore-backup")
        try:
            switcher = self._processes.spawn_detached(argv, layout.version_dir(self._installed))
        except OSError:
            raise UpdateConflict("cannot_restart") from None
        try:
            accepted = bool(request_quit())
        except Exception:
            _log.exception("The quit request failed")
            accepted = False
        if not accepted:
            switcher.terminate()
            if switcher.wait(5.0) is None:
                switcher.kill()
            raise UpdateConflict("cannot_restart")
        self._switch_started = to_iso(self._now())
        self._switching = True
        _log.info("The switch to %s was started (%s); ShelfSync is closing", target, mode)


def build_update_service(paths: DataPaths, secrets: SecretStore) -> UpdateService:
    """The service the running app uses: the installed layout (or the one SHELFSYNC_INSTALL_DIR names, for tests and
    rehearsals), or the development service when there is none."""
    layout = resolve_install_layout()
    if layout is None:
        return UpdateService.development(secrets, paths)
    return UpdateService(secrets=secrets, paths=paths, layout=layout)


__all__ = [
    "GITHUB_TOKEN_ENTRY",
    "Available",
    "InvalidToken",
    "TokenStatus",
    "UpdateConflict",
    "UpdateNeedsConfirmation",
    "UpdateService",
    "UpdateStatus",
    "UpdateTooSoon",
    "build_update_service",
    "is_valid_token",
]
