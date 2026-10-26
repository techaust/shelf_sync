"""The FastAPI app factory (04 section 5)."""

import time
from collections.abc import Callable

from fastapi import FastAPI
from pydantic import BaseModel

from shelfsync import __version__
from shelfsync.api.errors import register_error_handlers
from shelfsync.api.session import make_session_router
from shelfsync.platform.secrets import SecretStore
from shelfsync.secure.headers import SecurityHeadersMiddleware
from shelfsync.secure.middleware import HEALTH_PATH, GuardMiddleware
from shelfsync.secure.sessions import SessionStore
from shelfsync.secure.token import InstallToken


class HealthResponse(BaseModel):
    app: str
    version: str


def create_app(port: int, secrets: SecretStore, clock: Callable[[], float] = time.monotonic) -> FastAPI:
    """The app for the port the server actually bound (the Host check needs it).

    `secrets` holds the install token, `clock` times the 60-second tickets (tests pass their own).
    """
    # No interactive docs and no public schema route (docs_url, redoc_url, openapi_url all None). The schema is
    # still available in code through app.openapi(), for openapi-typescript in M1a.3. debug stays off, so an
    # unhandled error never shows a traceback.
    app = FastAPI(title="ShelfSync", version=__version__, debug=False, docs_url=None, redoc_url=None, openapi_url=None)
    sessions = SessionStore(clock)
    install_token = InstallToken(secrets)
    register_error_handlers(app)

    @app.get(HEALTH_PATH, response_model=HealthResponse)
    def health() -> HealthResponse:
        # No session needed; returns only these two fields (04 section 5).
        return HealthResponse(app="shelfsync", version=__version__)

    app.include_router(make_session_router(sessions, install_token))

    # The last middleware added is the outermost: the headers wrap the guard, so a refusal carries them too.
    app.add_middleware(GuardMiddleware, port=port, sessions=sessions)
    app.add_middleware(SecurityHeadersMiddleware)
    return app
