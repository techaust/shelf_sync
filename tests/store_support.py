"""Helpers for the store tests (M2.1): a fake WooCommerce built from its REST docs (httpx.MockTransport, RFC 2606 host
names only), a fake clock, a secret store that can be made to fail, and an app wired to them."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from shelfsync.api.app import create_app
from shelfsync.platform.secrets import MemorySecretStore, SecretStoreError
from shelfsync.secure.token import InstallToken
from shelfsync.store_service import StoreService
from tests.support import FakeClock, Harness

KEY = "ck_" + "a1B2c3D4e5" * 3
SECRET = "cs_" + "f6G7h8I9j0" * 3
KEY_2 = "ck_" + "k1L2m3N4o5" * 3
SECRET_2 = "cs_" + "p6Q7r8S9t0" * 3
STORE_URL = "https://store-a.example"
OTHER_URL = "https://store-b.example"

SYSTEM_STATUS = "/wp-json/wc/v3/system_status"
PRODUCTS = "/wp-json/wc/v3/products"


def system_status(version: str = "9.4.1", wp: str = "6.7.1") -> httpx.Response:
    """What `system_status?_fields=environment` answers (WooCommerce REST docs: `environment.version`, `.wp_version`)."""
    return httpx.Response(200, json={"environment": {"version": version, "wp_version": wp}})


def products(total: int | str | None = 42, body: Any = None) -> httpx.Response:
    headers = {} if total is None else {"X-WP-Total": str(total), "X-WP-TotalPages": "42"}
    return httpx.Response(200, headers=headers, json=[{"id": 7}] if body is None else body)


def wp_error(status: int, code: str) -> httpx.Response:
    """WordPress's own JSON error, as WooCommerce answers a refused or unknown request."""
    return httpx.Response(status, json={"code": code, "message": "text", "data": {"status": status}})


def html(status: int) -> httpx.Response:
    return httpx.Response(
        status, headers={"Content-Type": "text/html"}, content=b"<html><body>Just a moment</body></html>"
    )


class FakeTime:
    """A clock and a sleep that only move when told to."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@dataclass
class FakeWoo:
    """The two endpoints Test connection reads. `status` and `products_answer` give the answers (a response, or a
    callable that gets the request and returns one or raises)."""

    time: FakeTime = field(default_factory=FakeTime)
    status: Callable[[httpx.Request], httpx.Response] | httpx.Response | None = None
    products_answer: Callable[[httpx.Request], httpx.Response] | httpx.Response | None = None
    latency: float = 0.2
    requests: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith(SYSTEM_STATUS):
            answer = self.status if self.status is not None else system_status()
        elif path.endswith(PRODUCTS):
            self.time.now += self.latency
            answer = self.products_answer if self.products_answer is not None else products()
        else:
            return httpx.Response(404, json={"code": "rest_no_route", "message": "x", "data": {"status": 404}})
        return answer(request) if callable(answer) else answer

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


class FailingSecretStore(MemorySecretStore):
    """A secret store whose `set` fails on the n-th call and whose `delete` can be made to fail for given names."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_set_on: int | None = None
        self.sets = 0
        self.fail_delete: set[str] = set()
        self.fail_get = False

    def get(self, name: str) -> str | None:
        if self.fail_get:
            raise SecretStoreError("Credential Manager read failed (Fake)")
        return super().get(name)

    def set(self, name: str, value: str) -> None:
        self.sets += 1
        if self.fail_set_on is not None and self.sets == self.fail_set_on:
            raise SecretStoreError("Credential Manager write failed (Fake)")
        super().set(name, value)

    def delete(self, name: str) -> None:
        if name in self.fail_delete:
            raise SecretStoreError("Credential Manager delete failed (Fake)")
        super().delete(name)


@dataclass
class StoreRig:
    harness: Harness
    service: StoreService
    secrets: MemorySecretStore
    woo: FakeWoo


def make_store_rig(secrets: MemorySecretStore | None = None, woo: FakeWoo | None = None) -> StoreRig:
    secret_store = secrets if secrets is not None else MemorySecretStore()
    fake = woo if woo is not None else FakeWoo()
    service = StoreService.in_memory(secret_store, fake.transport)
    service._sleep = fake.time.sleep
    service._monotonic = fake.time.monotonic
    install_secrets = MemorySecretStore()
    clock = FakeClock()
    app = create_app(47615, InstallToken(install_secrets), clock, ui_dir=None, stores=service)
    return StoreRig(Harness(app=app, store=install_secrets, clock=clock), service, secret_store, fake)


def new_store_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Store A",
        "url": STORE_URL,
        "code": "SA",
        "shape": "circle",
        "color": "indigo",
        "consumer_key": KEY,
        "consumer_secret": SECRET,
    }
    body.update(changes)
    return body


def dumps(value: Any) -> str:
    return json.dumps(value)
