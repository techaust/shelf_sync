"""The FastAPI app factory (04 section 5)."""

from fastapi import FastAPI
from pydantic import BaseModel

from shelfsync import __version__


class HealthResponse(BaseModel):
    app: str
    version: str


def create_app() -> FastAPI:
    # No interactive docs and no public schema route (docs_url, redoc_url, openapi_url all None). The schema is
    # still available in code through app.openapi(), for openapi-typescript in M1a.3.
    app = FastAPI(title="ShelfSync", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        # No session needed; returns only these two fields (04 section 5).
        return HealthResponse(app="shelfsync", version=__version__)

    return app
