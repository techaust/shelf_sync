"""The backup export and import API (SET-05): the settings, the stores and, with a passphrase, the secrets in one file.

Behind the guard in `secure/middleware.py` (a session, and Origin plus `X-ShelfSync: 1` for both writes). A wrong shape
is the fixed 422 `invalid_request` that never echoes the request.

    POST /api/backup/export   {passphrase: str | null} -> 200 `application/json`, the `.ssbak` file, with
                              `Content-Disposition: attachment; filename="shelfsync-export-<local date>.ssbak"` and,
                              when a secret had to be left out, `X-ShelfSync-Left-Out` (below); 409 busy (one key
                              derivation or file parse at a time, process-wide); 503 secrets_unavailable, backup_failed
    POST /api/backup/import   {file: <the file's text, up to 1 MiB>, passphrase: str | null} -> 200
                              `{stores, settings, secrets, encrypted}` (counts, and whether the file was encrypted);
                              422 export_invalid, passphrase_required, wrong_passphrase, export_not_encrypted (a
                              passphrase was sent with a plain file); 409 export_too_new, import_needs_empty, busy;
                              503 secrets_unavailable, backup_failed

`X-ShelfSync-Left-Out` lists the kinds of secret an encrypted export could not include because they weren't in the
shape an import accepts or were half a pair, as `stores:SA,SB;s3:rw,ro;github` (store codes only, never a value); the
header is absent when nothing was left out.

The file format and its crypto are in `secure/backup_crypto.py`, the database side in `db/export.py`. The payload
(version 1) is `{settings, stores, storage, catalog: null, secrets}`; `secrets` (each store's key pair by code, the two
S3 pairs, the GitHub token) is in **encrypted files only**, and the install token is never exported. A plain file that
holds `secrets`, or an encrypted one that doesn't, is refused.

**Import order:** size cap, parse, header check (format, version, exact KDF costs, schema), decrypt and check the tag
(or the SHA-256), validate the whole payload with the same models the settings and store APIs use, and only then one
database transaction in which the Credential Manager entries are written **before** the commit. On any failure the
transaction is rolled back, the store entries written are deleted and the S3 and GitHub entries are put back as they
were. An import is for a fresh install or a new PC: with a live store it is refused (`import_needs_empty`). A secret
the file doesn't hold is left as it is (a missing S3 pair or token is not deleted).

The passphrase is registered with the log redaction for the request only, and is never logged. The three secrets of a
store, the S3 keys and the token are registered as they are written (`secure/credentials.py`, `register_secret`).
"""

import logging
import sqlite3
import threading
import uuid
import weakref
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictStr, model_validator

from shelfsync import __version__
from shelfsync.api.app_settings import AppSettingsValues, stored_values, validators_for
from shelfsync.api.backup_settings import BackupSettingsValues
from shelfsync.api.errors import ApiError, ErrorResponse
from shelfsync.api.storage import KeyPairRequest, StorageValues
from shelfsync.api.stores import Button, Code, Color, KeysRequest, Name, Shape, Spacing, StoreFields
from shelfsync.clock import to_iso, utc_now
from shelfsync.db.export import (
    SETTINGS_KEYS,
    STORAGE_KEYS,
    STORE_FIELDS,
    StoreImport,
    highest_applied_schema,
    highest_known_schema,
    read_stores,
    write_import,
)
from shelfsync.db.migrate import migrate
from shelfsync.db.stores import CodeTaken, UrlTaken, live_store_count
from shelfsync.platform.secrets import MemorySecretStore, SecretStore, SecretStoreError
from shelfsync.secure.backup_crypto import (
    MAX_FILE_CHARS,
    PASSPHRASE_MAX,
    PASSPHRASE_MIN,
    ExportInvalid,
    ExportTooNew,
    KeyDerivationFailed,
    PassphraseInvalid,
    PassphraseRequired,
    WrongPassphrase,
    canonical,
    check_header,
    check_passphrase,
    dumps,
    open_envelope,
    parse_envelope,
    seal,
    strict_loads,
)
from shelfsync.secure.credentials import (
    S3_SLOTS,
    SECRETS_WRITE_LOCK,
    S3Credentials,
    StoreCredentials,
    is_valid_pair,
    is_valid_s3_pair,
    s3_entries,
)
from shelfsync.secure.redact import register_secret, temporary_secret
from shelfsync.store_service import MAX_STORES
from shelfsync.update.service import GITHUB_TOKEN_ENTRY, is_valid_token

_log = logging.getLogger("shelfsync.backup")

BACKUP_EXPORT_PATH = "/api/backup/export"
BACKUP_IMPORT_PATH = "/api/backup/import"
# The body an import may carry, in bytes: the file text (1 MiB at most, `MAX_FILE_CHARS`; a v1 file is tens of
# kilobytes) and the JSON around it. `secure/body_limit.py` enforces it before the app reads a byte. Format v2 (the
# catalog, M3) raises both numbers.
IMPORT_BODY_MAX = MAX_FILE_CHARS + 64 * 1024
EXPORT_BODY_MAX = 64 * 1024  # a passphrase of at most 4096 characters, escaped, and the field names
LEFT_OUT_HEADER = "X-ShelfSync-Left-Out"


def _passphrase_rule(value: str) -> str:
    try:
        return check_passphrase(value)
    except PassphraseInvalid:
        raise ValueError("not an acceptable passphrase") from None


# 12 to 1024 characters after NFC (the NFC form can be shorter than the typed one, so the typed length is capped wider).
Passphrase = Annotated[StrictStr, Field(max_length=4 * PASSPHRASE_MAX), AfterValidator(_passphrase_rule)]


def _token_rule(value: str) -> str:
    if not is_valid_token(value):
        raise ValueError("not a fine-grained GitHub token")
    return value


GithubToken = Annotated[StrictStr, Field(max_length=300), AfterValidator(_token_rule)]


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passphrase: Passphrase | None


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: StrictStr  # its length is checked by the service, which answers `export_invalid` (not `invalid_request`)
    passphrase: Passphrase | None


class ImportResult(BaseModel):
    stores: int  # stores added
    settings: int  # settings written
    secrets: int  # Credential Manager entries written (two per key pair, one for the token)
    encrypted: bool  # the file was encrypted (so it could carry secrets)


# ---- the payload, version 1 ----------------------------------------------------------------------------------------


class ImportedSettings(AppSettingsValues, BackupSettingsValues):
    """The seven settings that aren't storage settings: the App settings' model and the Backup settings' model, so the
    limits are the ones those two screens enforce."""


class StoreEntry(StoreFields):
    """A store as exported: the fields the Stores API's create request has, with the same checks, and its state."""

    code: Code
    name: Name
    url: Annotated[str, Field(max_length=200)]
    shape: Shape
    color: Color
    spacing_ms: Spacing
    main_button: Button
    state: Literal["active", "paused"]


class S3Pairs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rw: KeyPairRequest | None
    ro: KeyPairRequest | None


class PayloadSecrets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stores: dict[Code, KeysRequest]  # by store code
    s3: S3Pairs
    github_token: GithubToken | None


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    settings: ImportedSettings
    stores: Annotated[list[StoreEntry], Field(max_length=MAX_STORES)]
    storage: StorageValues
    catalog: None  # M3 adds one as format version 2
    secrets: PayloadSecrets | None = None  # encrypted files only

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        codes = [store.code for store in self.stores]
        if len(set(codes)) != len(codes) or len({store.url for store in self.stores}) != len(codes):
            raise ValueError("a store code or address is repeated")
        if self.secrets is not None and not set(self.secrets.stores) <= set(codes):
            raise ValueError("keys for a store that isn't in the file")
        return self


_SETTINGS_VALIDATORS = validators_for(ImportedSettings)
_STORAGE_VALIDATORS = validators_for(StorageValues)

# ---- one key derivation at a time, in the whole process ------------------------------------------------------------

_KDF_SLOT = threading.Lock()


@contextmanager
def _one_derivation() -> Iterator[None]:
    """scrypt takes about 128 MiB and a second: a second request while one runs is `busy`, never queued."""
    if not _KDF_SLOT.acquire(blocking=False):
        raise ApiError(409, "busy")
    try:
        yield
    finally:
        _KDF_SLOT.release()


@dataclass(frozen=True)
class ExportedFile:
    text: str
    filename: str
    left_out: str = ""  # the `X-ShelfSync-Left-Out` value; "" when nothing was left out


def _refusal(error: Exception) -> ApiError:
    if isinstance(error, ExportTooNew):
        return ApiError(409, "export_too_new")
    if isinstance(error, PassphraseRequired):
        return ApiError(422, "passphrase_required")
    if isinstance(error, WrongPassphrase):
        return ApiError(422, "wrong_passphrase")
    if isinstance(error, KeyDerivationFailed):
        _log.warning("A backup key couldn't be derived (%s)", error)  # the message is the exception's type name
        return ApiError(503, "backup_failed")
    return ApiError(422, "export_invalid")


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")


class ExportService:
    """What the routes talk to. `connect` opens a connection to the database (one per call, closed after); `secrets` is
    Credential Manager (a fake in tests). An export reads, and an import writes, under `SECRETS_WRITE_LOCK`, the lock
    every other secrets write takes, so neither interleaves with a key write. `forget_expiry` is called after an import
    commits a GitHub token (the cached expiry belonged to the old one)."""

    def __init__(
        self,
        connect: Callable[[], sqlite3.Connection],
        secrets: SecretStore,
        *,
        now: Callable[[], datetime] = utc_now,
        forget_expiry: Callable[[], None] | None = None,
    ) -> None:
        self._connect = connect
        self._secrets = secrets
        self._store_keys = StoreCredentials(secrets)
        self._s3 = S3Credentials(secrets)
        self._now = now
        self._forget_expiry = forget_expiry
        self._keeper: sqlite3.Connection | None = None  # holds a development database's memory open

    @classmethod
    def development(cls, secrets: SecretStore | None = None) -> ExportService:
        """A database in memory and, by default, an in-memory secret store: no test reaches a file or Credential Manager
        by accident."""
        uri = f"file:shelfsync-export-{uuid.uuid4().hex}?mode=memory&cache=shared"

        def connect() -> sqlite3.Connection:
            return sqlite3.connect(uri, uri=True, isolation_level=None, check_same_thread=False)

        keeper = connect()
        migrate(keeper)
        service = cls(connect, secrets if secrets is not None else MemorySecretStore())
        service._keeper = keeper
        weakref.finalize(service, keeper.close)
        return service

    # ---- export ----------------------------------------------------------------------------------------------------

    def export(self, passphrase: str | None) -> ExportedFile:
        with temporary_secret(passphrase, minimum=PASSPHRASE_MIN) if passphrase is not None else nullcontext():
            payload, schema, left_out = self._collect(include_secrets=passphrase is not None)
            created = self._now()
            body = canonical(payload)
            if passphrase is None:
                envelope = seal(body, None, created_at=to_iso(created), app_version=__version__, schema=schema)
            else:
                try:
                    with _one_derivation():
                        envelope = seal(
                            body, passphrase, created_at=to_iso(created), app_version=__version__, schema=schema
                        )
                except KeyDerivationFailed as error:
                    raise _refusal(error) from None
        name = f"shelfsync-export-{created.astimezone().strftime('%Y-%m-%d')}.ssbak"
        _log.info("A backup file was exported (%s)", "encrypted" if passphrase is not None else "without secrets")
        return ExportedFile(dumps(envelope), name, left_out)

    def _collect(self, *, include_secrets: bool) -> tuple[dict[str, Any], int, str]:
        """The payload, the schema number and the left-out line, read under the secrets lock so a key write can't land
        half way through. A Credential Manager failure while secrets are wanted is `secrets_unavailable`; a database
        that can't be read is `backup_failed`."""
        left_out = ""
        with SECRETS_WRITE_LOCK, closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN")  # one read snapshot for the settings, the stores and the schema
            except sqlite3.OperationalError as error:
                _log.warning("A backup couldn't read the database (%s)", type(error).__name__)
                raise ApiError(503, "backup_failed") from None
            try:
                settings = stored_values(connection, _SETTINGS_VALIDATORS, SETTINGS_KEYS)
                storage = stored_values(connection, _STORAGE_VALIDATORS, STORAGE_KEYS)
                rows = read_stores(connection)
                schema = highest_applied_schema(connection)
            finally:
                _rollback(connection)
            payload: dict[str, Any] = {
                "settings": settings,
                "stores": [{field: getattr(row, field) for field in STORE_FIELDS} for row in rows],
                "storage": storage,
                "catalog": None,
            }
            if include_secrets:
                try:
                    payload["secrets"], left_out = self._read_secrets([(row.id, row.code) for row in rows])
                except SecretStoreError:
                    raise ApiError(503, "secrets_unavailable") from None
        try:
            Payload.model_validate(payload)  # what is written is what an import accepts
        except ValueError:  # its text would hold the values: never passed on
            _log.error("The data to export isn't in the shape an import accepts")
            raise RuntimeError("The data to export isn't in the shape an import accepts.") from None
        return payload, schema, left_out

    def _read_secrets(self, stores: list[tuple[int, str]]) -> tuple[dict[str, Any], str]:
        """Every secret ShelfSync keeps for the owner, and nothing else (the install token is not among them), and the
        `X-ShelfSync-Left-Out` line. A value that isn't in the shape the file requires, or one half of a pair, is left
        out, with a warning that names no value."""
        stores_out: list[str] = []
        s3_out: list[str] = []
        github_out = False
        by_store: dict[str, Any] = {}
        for store_id, code in stores:
            key, secret = self._store_keys.read(store_id)
            for value in (key, secret):
                if value is not None:
                    register_secret(value)
            if key is None and secret is None:
                continue  # no keys saved: nothing to leave out
            if key is not None and secret is not None and is_valid_pair(key, secret):
                by_store[code] = {"consumer_key": key, "consumer_secret": secret}
            else:
                _log.warning("The keys of store %s aren't in a shape that can be exported; they were left out", code)
                stores_out.append(code)
        s3: dict[str, Any] = {}
        for slot in S3_SLOTS:
            key_id, secret = self._s3.read(slot)
            for value in (key_id, secret):
                if value is not None:
                    register_secret(value)
            pair = None
            if key_id is not None and secret is not None and is_valid_s3_pair(key_id, secret):
                pair = {"access_key_id": key_id, "secret_access_key": secret}
            elif key_id is not None or secret is not None:
                _log.warning("The %s S3 keys aren't in a shape that can be exported; they were left out", slot)
                s3_out.append(slot)
            s3[slot] = pair
        token = self._secrets.get(GITHUB_TOKEN_ENTRY)
        if token is not None:
            register_secret(token)
            if not is_valid_token(token):
                _log.warning("The GitHub token isn't in a shape that can be exported; it was left out")
                token = None
                github_out = True
        parts = []
        if stores_out:
            parts.append("stores:" + ",".join(stores_out))
        if s3_out:
            parts.append("s3:" + ",".join(s3_out))
        if github_out:
            parts.append("github")
        return {"stores": by_store, "s3": s3, "github_token": token}, ";".join(parts)

    # ---- import ----------------------------------------------------------------------------------------------------

    def import_file(self, text: str, passphrase: str | None) -> ImportResult:
        """The whole import, in the order the module's docstring gives. Nothing is written until everything before the
        write has passed. The parse, the key derivation and the validation run one at a time in the whole process (a
        second request is `busy`), so concurrent imports can't add up their memory."""
        with temporary_secret(passphrase, minimum=PASSPHRASE_MIN) if passphrase is not None else nullcontext():
            try:
                if len(text) > MAX_FILE_CHARS:
                    raise ExportInvalid("The file is too long.")
                with _one_derivation():
                    envelope = parse_envelope(text)
                    check_header(envelope, max_schema=highest_known_schema())
                    encrypted = envelope["encryption"] is not None
                    if encrypted and passphrase is None:
                        raise PassphraseRequired("The file is encrypted.")
                    if not encrypted and passphrase is not None:
                        # Not ignored: a passphrase for a plain file may mean the file was swapped for a plain one.
                        raise ApiError(422, "export_not_encrypted")
                    body = open_envelope(envelope, passphrase)
                    payload = self._validated(body, encrypted=encrypted)
            except (ExportInvalid, ExportTooNew, PassphraseRequired, WrongPassphrase, KeyDerivationFailed) as error:
                raise _refusal(error) from None
            return self._write(payload, encrypted=encrypted)

    @staticmethod
    def _validated(body: bytes, *, encrypted: bool) -> Payload:
        try:
            payload = Payload.model_validate(strict_loads(body))
        except ValueError, RecursionError:  # includes pydantic's validation error; its text holds the input: dropped
            raise ExportInvalid("The payload isn't valid.") from None
        if (payload.secrets is not None) != encrypted:  # secrets in a plain file, or none in an encrypted one
            raise ExportInvalid("The file's secrets don't match its encryption.")
        return payload

    def _write(self, payload: Payload, *, encrypted: bool) -> ImportResult:
        stores = [StoreImport(**entry.model_dump()) for entry in payload.stores]
        settings = {**payload.settings.model_dump(), **payload.storage.model_dump()}
        wrote_token = False
        with SECRETS_WRITE_LOCK:  # the lock first, then the database's write lock, as everywhere
            try:
                before = self._entries_before(payload.secrets)
            except SecretStoreError:
                raise ApiError(503, "secrets_unavailable") from None
            written: list[int] = []
            touched_secrets = False
            connection = self._connect()
            try:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    if live_store_count(connection) > 0:
                        raise ApiError(409, "import_needs_empty")
                    written = write_import(connection, settings=settings, stores=stores, created_at=to_iso(self._now()))
                    touched_secrets = True
                    entries = self._write_secrets(payload.secrets, stores, written)  # before the commit
                    connection.execute("COMMIT")
                    wrote_token = payload.secrets is not None and payload.secrets.github_token is not None
                except BaseException as error:
                    _rollback(connection)
                    self._undo(written, before if touched_secrets else {})
                    if isinstance(error, SecretStoreError):
                        raise ApiError(503, "secrets_unavailable") from None
                    if isinstance(error, UrlTaken | CodeTaken):
                        raise ApiError(422, "export_invalid") from None
                    if isinstance(error, sqlite3.OperationalError):  # a locked or failing database: no detail
                        _log.warning("A backup import couldn't use the database (%s)", type(error).__name__)
                        raise ApiError(503, "backup_failed") from None
                    raise
            finally:
                connection.close()
            if wrote_token and self._forget_expiry is not None:  # committed: the cached expiry was the old token's
                try:
                    self._forget_expiry()
                except Exception as error:  # the import is done; a stale expiry corrects itself at the next check
                    _log.warning("The token's expiry couldn't be reset (%s)", type(error).__name__)
        _log.info("A backup file was imported (%d stores)", len(stores))
        return ImportResult(stores=len(stores), settings=len(settings), secrets=entries, encrypted=encrypted)

    def _entries_before(self, secrets: PayloadSecrets | None) -> dict[str, str | None]:
        """What the entries an import may overwrite hold now (the S3 pairs and the token it will write), so a failure
        puts them back. Raises `SecretStoreError`."""
        if secrets is None:
            return {}
        names: list[str] = []
        for slot in S3_SLOTS:
            if getattr(secrets.s3, slot) is not None:
                names.extend(s3_entries(slot))
        if secrets.github_token is not None:
            names.append(GITHUB_TOKEN_ENTRY)
        return {name: self._secrets.get(name) for name in names}

    def _write_secrets(self, secrets: PayloadSecrets | None, stores: list[StoreImport], ids: list[int]) -> int:
        """Credential Manager writes for one import; returns how many entries. Raises `SecretStoreError`."""
        if secrets is None:
            return 0
        count = 0
        for store, store_id in zip(stores, ids, strict=True):
            keys = secrets.stores.get(store.code)
            if keys is not None:
                self._store_keys.save(store_id, keys.consumer_key, keys.consumer_secret)
                count += 2
        for slot in S3_SLOTS:
            pair = getattr(secrets.s3, slot)
            if pair is not None:
                self._s3.save(slot, pair.access_key_id, pair.secret_access_key)
                count += 2
        if secrets.github_token is not None:
            register_secret(secrets.github_token)
            self._secrets.set(GITHUB_TOKEN_ENTRY, secrets.github_token)
            count += 1
        return count

    def _undo(self, ids: list[int], before: dict[str, str | None]) -> None:
        """After a failed import (best effort, nothing raised): the new stores' entries go, the others come back."""
        for store_id in ids:
            self._store_keys.discard(store_id)
        for name, old in before.items():
            try:
                if old is None:
                    self._secrets.delete(name)
                else:
                    self._secrets.set(name, old)
            except SecretStoreError as error:
                _log.warning("A stored entry couldn't be put back (%s)", type(error).__name__)


_ERRORS: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}
_FILE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The .ssbak file, as a download.",
        "content": {"application/json": {"schema": {"type": "object"}}},
    },
    **_ERRORS,
}


def make_backup_router(service: ExportService) -> APIRouter:
    router = APIRouter()

    @router.post(BACKUP_EXPORT_PATH, response_model=None, responses=_FILE_RESPONSE)
    def export_backup(body: ExportRequest) -> Response:
        exported = service.export(body.passphrase)
        headers = {"Content-Disposition": f'attachment; filename="{exported.filename}"'}
        if exported.left_out:
            headers[LEFT_OUT_HEADER] = exported.left_out
        return Response(content=exported.text, media_type="application/json", headers=headers)

    @router.post(BACKUP_IMPORT_PATH, response_model=ImportResult, responses=_ERRORS)
    def import_backup(body: ImportRequest) -> ImportResult:
        return service.import_file(body.file, body.passphrase)

    return router


__all__ = [
    "BACKUP_EXPORT_PATH",
    "BACKUP_IMPORT_PATH",
    "EXPORT_BODY_MAX",
    "IMPORT_BODY_MAX",
    "ExportService",
    "ImportResult",
    "make_backup_router",
]
