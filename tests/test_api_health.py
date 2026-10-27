"""API-health: exactly two fields, and no public docs or schema routes."""

import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import shelfsync
from shelfsync.api.app import create_app
from shelfsync.platform.secrets import MemorySecretStore
from shelfsync.secure.token import InstallToken
from tests.support import PORT, make_harness


@pytest.fixture
def client() -> TestClient:
    # The Host check refuses TestClient's default host (testserver), so the client talks as 127.0.0.1:<port>.
    return make_harness().client()


def test_health_returns_exactly_app_and_version(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"app": "shelfsync", "version": shelfsync.__version__}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
def test_docs_and_schema_routes_are_not_served(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_schema_is_still_available_in_code() -> None:
    schema = create_app(PORT, InstallToken(MemorySecretStore()), ui_dir=None).openapi()
    assert "/api/health" in schema["paths"]


def test_package_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == shelfsync.__version__
