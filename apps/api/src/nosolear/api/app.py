from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from nosolear.settings import Settings


class HealthResponse(BaseModel):
    status: Literal["ok"]


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Nosolear")
    app.state.settings = settings or Settings()

    @app.get("/api/health")
    def health() -> HealthResponse:  # pyright: ignore[reportUnusedFunction]
        return HealthResponse(status="ok")

    return app
