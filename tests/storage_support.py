"""Helpers for the storage tests (M2.3): fake S3 key values and an app wired to a storage service with a secret store
that can be made to fail. No S3 call exists in this code, so there is no fake S3."""

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from shelfsync.api.app import create_app
from shelfsync.api.storage import StorageService
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.token import InstallToken
from tests.store_support import FailingSecretStore
from tests.support import FakeClock, Harness

RW_ID = "AKIA" + "RW1A2B3C4D5E6F7"  # 19 characters, a made-up value of the right shape
RW_SECRET = "rw/Secret+" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1e" + "="  # 41 characters
RO_ID = "AKIA" + "RO9Z8Y7X6W5V4U3"
RO_SECRET = "ro/Secret+" + "Zy8xW6vU4tS2rQ0pO8nM6lK4jI2hG0f" + "="
RW_ID_2 = "AKIA" + "NEWRW1A2B3C4D5E"
RW_SECRET_2 = "new/Rw+Secret" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ" + "=="

GOOD_SETTINGS: dict[str, Any] = {
    "s3_endpoint": "",
    "s3_region": "ap-south-1",
    "s3_bucket": "example-bucket",
    "keep_previous_files": 2,
    "download_link_template": '[amazon_s3 object="{key}"]',
}


@dataclass
class StorageRig:
    harness: Harness
    service: StorageService
    secrets: FailingSecretStore
    client: TestClient


def make_storage_rig(secrets: FailingSecretStore | None = None) -> StorageRig:
    secret_store = secrets if secrets is not None else FailingSecretStore()
    service = StorageService.development(secret_store)
    install = MemorySecretStore()
    clock = FakeClock()
    app = create_app(47615, InstallToken(install), clock, ui_dir=None, storage=service)
    harness = Harness(app=app, store=install, clock=clock)
    return StorageRig(harness, service, secret_store, harness.signed_in_client())


def key_body(key_id: str = RW_ID, secret: str = RW_SECRET) -> dict[str, str]:
    return {"access_key_id": key_id, "secret_access_key": secret}


def api_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Every (method, path) under /api. FastAPI 0.143 keeps included routers as one lazy object, so the walk goes
    through `iter_route_contexts`, as `tests/test_guard.py` does."""
    found: list[tuple[str, str]] = []
    for context in iter_route_contexts(app.routes):
        path = getattr(context, "path", None)
        methods = getattr(context, "methods", None)
        if isinstance(path, str) and path.startswith("/api") and isinstance(methods, set):
            found.extend((method, path) for method in sorted(methods))
    return found
