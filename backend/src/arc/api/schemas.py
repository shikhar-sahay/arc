"""Health response schema for the ARC API."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Typed response for GET /api/health."""

    app: str
    status: str
    platform: str
