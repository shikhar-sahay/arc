"""ARC FastAPI application factory.

FastAPI is an interface to the ARC engine, not the engine itself.
Engine logic (monitoring, evaluation, enforcement, restoration)
will live under arc.core and related packages in later passes.
"""

import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from arc.api.schemas import HealthResponse

APP_NAME = "ARC"


def create_app() -> FastAPI:
    """Create and configure the ARC FastAPI application."""
    app = FastAPI(title="ARC", description="Adaptive Resource Contract Engine API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    def get_health() -> HealthResponse:
        """Return service health and runtime platform info."""
        return HealthResponse(app=APP_NAME, status="ok", platform=sys.platform)

    return app


app = create_app()
