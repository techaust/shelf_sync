"""The FastAPI app factory (04 section 5)."""

import logging
import time
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel
from starlette.responses import Response
from starlette.routing import Match, Mount
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from shelfsync import __version__
from shelfsync.api.errors import register_error_handlers
from shelfsync.api.session import make_session_router
from shelfsync.secure.headers import SecurityHeadersMiddleware, is_api_path
from shelfsync.secure.middleware import HEALTH_PATH, GuardMiddleware
from shelfsync.secure.sessions import SessionStore
from shelfsync.secure.token import InstallToken

_log = logging.getLogger("shelfsync.api")

# The built UI (`npm run build` in frontend/) in the source layout: <repo>/frontend/dist. Where the installer puts
# it is decided with the packaging (M1b); this default is the development layout.
UI_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"

# The mount's name and path. Starlette stores a mount at "/" with the path "" (it strips the trailing slash), which
# is the path the route-table test sees (tests/test_guard.py ALLOWED_OUTSIDE_API).
UI_MOUNT_PATH = "/"
UI_MOUNT_NAME = "ui"


class HealthResponse(BaseModel):
    app: str
    version: str


# Caching of the UI's files. Vite names every file under assets/ by its content hash, so one name always holds the
# same bytes and the browser may keep it for a year without asking. Everything else (index.html, the favicons) is
# revalidated on every load, so after an update the page never asks for assets an old index.html named.
UI_ASSETS_PREFIX = "assets/"
CACHE_HASHED = "public, max-age=31536000, immutable"
CACHE_REVALIDATE = "no-cache"


class _UiFiles(StaticFiles):
    """StaticFiles with the cache rule above on every file it answers with (200 or 304). A 404 is raised as an
    exception and answered by the app's error handler, with no Cache-Control."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        hashed = path.replace("\\", "/").startswith(UI_ASSETS_PREFIX) and response.status_code in (200, 304)
        response.headers["Cache-Control"] = CACHE_HASHED if hashed else CACHE_REVALIDATE
        return response


class _UiMount(Mount):
    """A mount at "/" that never matches a path under /api.

    A plain mount at "/" matches every path, so Starlette's router would hand it any /api request whose route
    exists with another method (it only remembers that partial match and keeps looking): GET on a POST-only route
    would get the static files' 404 instead of the route's 405, and an unknown /api path would reach the files.
    Declining /api here keeps every /api answer the API's own."""

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] == "http" and is_api_path(scope.get("path", "")):
            return Match.NONE, {}
        return super().matches(scope)


def _mount_ui(app: FastAPI, ui_dir: Path) -> None:
    """Serve the built UI at "/" (html mode: "/" gives index.html). Files only: there is no catch-all fallback, so
    a path that isn't a file is a 404, and nothing under /api ever reaches the files (`_UiMount`). The UI routes
    with the URL hash (#/review), so a refresh always asks for "/". Without the build (backend-only CI, tests) the
    app starts without it and says so in one log line."""
    if not (ui_dir / "index.html").is_file():
        _log.info("UI files not found, so only the API is served (looked in %s)", ui_dir)
        return
    app.router.routes.append(_UiMount(UI_MOUNT_PATH, app=_UiFiles(directory=ui_dir, html=True), name=UI_MOUNT_NAME))


def create_app(
    port: int,
    install_token: InstallToken,
    clock: Callable[[], float] = time.monotonic,
    *,
    ui_dir: Path | None,
) -> FastAPI:
    """The app for the port the server actually bound (the Host check needs it).

    `install_token` is the one token holder: start-up builds it before binding the port (so the secret store is read
    once and a failure holds no port) and the app never touches the store itself. `clock` times the 60-second
    tickets (tests pass their own). `ui_dir` (required, so no caller gets the real frontend/dist by accident) holds the
    built UI; None serves the API only (most tests).
    """
    # No interactive docs and no public schema route (docs_url, redoc_url, openapi_url all None). The schema is
    # still available in code through app.openapi(), for openapi-typescript in M1a.3. debug stays off, so an
    # unhandled error never shows a traceback.
    app = FastAPI(title="ShelfSync", version=__version__, debug=False, docs_url=None, redoc_url=None, openapi_url=None)
    sessions = SessionStore(clock)
    register_error_handlers(app)

    @app.get(HEALTH_PATH, response_model=HealthResponse)
    def health() -> HealthResponse:
        # No session needed; returns only these two fields (04 section 5).
        return HealthResponse(app="shelfsync", version=__version__)

    app.include_router(make_session_router(sessions, install_token))

    # Mounted last, so every /api route is matched first; and like every route it sits inside the middleware below:
    # the Host check and the security headers (the CSP included) apply to the UI's files too. No session is needed
    # to load them (06 section 2); every /api call the page makes still needs one.
    if ui_dir is not None:
        _mount_ui(app, ui_dir)

    # The last middleware added is the outermost: the headers wrap the guard, so a refusal carries them too.
    app.add_middleware(GuardMiddleware, port=port, sessions=sessions)
    app.add_middleware(SecurityHeadersMiddleware)
    return app
