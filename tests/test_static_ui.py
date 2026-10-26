"""UI-SHELL, NFR-1, SYS-03: the built UI (frontend/dist) is served by the app itself, inside the Host check and the
security headers, with no session needed for the files and no catch-all that could answer under /api."""

import logging
from pathlib import Path

import pytest

from shelfsync.api import app as app_module
from shelfsync.secure.headers import CONTENT_SECURITY_POLICY
from tests.support import ORIGIN, PORT, Harness, make_harness

INDEX = "<!doctype html><html><head><title>ShelfSync</title></head><body><div id=root></div></body></html>"
SCRIPT = "export const shelf = 1;\n"


@pytest.fixture
def ui_dir(tmp_path: Path) -> Path:
    """A stand-in for frontend/dist: index.html and one hashed asset."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_bytes(INDEX.encode())
    (dist / "assets" / "index-abc123.js").write_bytes(SCRIPT.encode())
    (tmp_path / "secret.txt").write_bytes(b"outside the UI folder")
    return dist


@pytest.fixture
def harness(ui_dir: Path) -> Harness:
    return make_harness(ui_dir=ui_dir)


def test_the_root_serves_index_html_without_a_session(harness: Harness) -> None:
    """UI-SHELL: "/" gives the page (html mode); loading it needs no session (06 section 2)."""
    response = harness.client().get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == INDEX


def test_a_built_asset_is_served(harness: Harness) -> None:
    """NFR-1: scripts come from the app itself, never a CDN."""
    response = harness.client().get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert response.text == SCRIPT
    assert "javascript" in response.headers["content-type"]


@pytest.mark.parametrize("path", ["/", "/index.html", "/assets/index-abc123.js", "/nope"])
def test_ui_files_carry_every_security_header(harness: Harness, path: str) -> None:
    """SYS-03: the UI is mounted inside the middleware, so the CSP and the other headers apply to it too."""
    headers = harness.client().get(path).headers
    assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cross-origin-resource-policy"] == "same-origin"
    assert not any(name.lower().startswith("access-control-") for name in headers)


@pytest.mark.parametrize("path", ["/", "/assets/index-abc123.js"])
def test_ui_files_still_need_the_right_host(harness: Harness, path: str) -> None:
    """SYS-03: DNS rebinding can't read the page either."""
    assert harness.client().get(path, headers={"Host": f"evil.example:{PORT}"}).status_code == 403


@pytest.mark.parametrize("path", ["/review", "/settings/stores", "/nope.js", "/assets/missing.js"])
def test_there_is_no_catch_all_a_path_that_is_not_a_file_is_404(harness: Harness, path: str) -> None:
    """UI-SHELL: the UI routes with the URL hash (#/review), so the server never needs a fallback page."""
    response = harness.client().get(path)
    assert response.status_code == 404
    assert INDEX not in response.text


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"])
def test_files_outside_the_ui_folder_are_never_served(harness: Harness, path: str) -> None:
    """SYS-03: no path traversal out of frontend/dist."""
    response = harness.client().get(path)
    assert "outside the UI folder" not in response.text


def test_unknown_api_paths_never_get_the_page_signed_in_or_not(harness: Harness) -> None:
    """SYS-03: the mount is at "/", but nothing under /api is ever answered with index.html."""
    assert harness.client().get("/api/nope").status_code == 401
    signed_in = harness.signed_in_client()
    for path in ["/api/nope", "/api/", "/api/index.html"]:
        response = signed_in.get(path)
        assert response.status_code == 404, path
        assert INDEX not in response.text, path


@pytest.mark.parametrize("path", ["/api/session/ticket", "/api/session", "/api/session/reset-token"])
def test_a_wrong_method_on_an_api_route_is_still_the_routes_405(harness: Harness, path: str) -> None:
    """SYS-03: the mount at "/" declines /api paths, so the router's 405 isn't turned into the files' 404 (a plain
    mount at "/" would take any /api request whose route exists with another method)."""
    response = harness.signed_in_client().get(path)
    assert response.status_code == 405
    assert INDEX not in response.text


def test_writes_to_ui_paths_are_refused_without_the_csrf_checks(harness: Harness) -> None:
    """SYS-03: the CSRF rule is by method, so a POST to "/" from another page is 403 before the mount."""
    assert harness.client().post("/").status_code == 403
    assert harness.client().post("/", headers={"Origin": "http://evil.example", "X-ShelfSync": "1"}).status_code == 403


def test_a_write_with_the_csrf_checks_reaches_the_mount_which_only_reads(harness: Harness) -> None:
    """SYS-03: StaticFiles answers only GET and HEAD."""
    response = harness.client().post("/", headers={"Origin": ORIGIN, "X-ShelfSync": "1"})
    assert response.status_code == 405


def test_without_the_build_the_app_starts_and_logs_one_line(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """UI-SHELL: backend-only CI and tests have no frontend/dist; the API still works, "/" is 404, one log line."""
    caplog.set_level(logging.INFO, logger="shelfsync.api")
    missing = tmp_path / "not-built"
    harness = make_harness(ui_dir=missing)
    records = [record for record in caplog.records if record.name == "shelfsync.api"]
    assert len(records) == 1
    assert records[0].getMessage().startswith("UI files not found, so only the API is served")
    assert harness.client().get("/").status_code == 404
    assert harness.client().get("/api/health").status_code == 200
    assert not any(getattr(route, "name", None) == "ui" for route in harness.app.routes)


def test_a_folder_without_index_html_counts_as_not_built(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """UI-SHELL: a half-written build (no index.html) isn't mounted."""
    caplog.set_level(logging.INFO, logger="shelfsync.api")
    (tmp_path / "assets").mkdir()
    harness = make_harness(ui_dir=tmp_path)
    assert harness.client().get("/").status_code == 404
    assert [record.name for record in caplog.records].count("shelfsync.api") == 1


def test_api_only_mode_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    """UI-SHELL: ui_dir=None (most tests) is a deliberate API-only app, not a missing build."""
    caplog.set_level(logging.INFO, logger="shelfsync.api")
    make_harness(ui_dir=None)
    assert not [record for record in caplog.records if record.name == "shelfsync.api"]


def test_the_default_folder_is_frontend_dist_in_the_source_layout() -> None:
    """UI-SHELL: `npm run build` in frontend/ writes the folder the server reads."""
    repo = Path(__file__).resolve().parents[1]
    assert repo / "frontend" / "dist" == app_module.UI_DIR
