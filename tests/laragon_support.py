"""Shared bits of the Laragon harness tests (`test_testenv_laragon.py`, `test_testenv_seed.py`): made-up keys of the
right shape, a secret store holding them under the site's own entries, and a certificate file for the site."""

import base64
import json
from pathlib import Path
from typing import Any

from shelfsync.platform.secrets import MemorySecretStore
from testenv import laragon

SITE = "shelfsync-test.test"
RO_KEY = "ck_" + "r0Read0nly" * 3
RO_SECRET = "cs_" + "r0S3cretRO" * 3
RW_KEY = "ck_" + "rWr1teKey0" * 3
RW_SECRET = "cs_" + "rWS3cretRW" * 3
ALL_VALUES = (RO_KEY, RO_SECRET, RW_KEY, RW_SECRET)


def site(port: int | None = None, host: str = SITE) -> laragon.Site:
    return laragon.parse_site(f"https://{host}" + ("" if port is None else f":{port}"))


def store_with_keys(
    host: str = SITE, ro: tuple[str, str] = (RO_KEY, RO_SECRET), rw: tuple[str, str] = (RW_KEY, RW_SECRET)
) -> MemorySecretStore:
    store = MemorySecretStore()
    read_only, read_write = laragon.pairs_for(site(host=host))
    store.set(read_only.key_entry, ro[0])
    store.set(read_only.secret_entry, ro[1])
    store.set(read_write.key_entry, rw[0])
    store.set(read_write.secret_entry, rw[1])
    return store


def basic(key: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode()


def write_site_cert(folder: Path, made: laragon.SiteCertificate, host: str = SITE) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{host}.crt"
    path.write_bytes(made.cert_pem)
    return path


def json_answer(status: int, body: Any, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    return status, {"Content-Type": "application/json", **(headers or {})}, json.dumps(body).encode()
