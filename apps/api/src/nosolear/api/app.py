from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from nosolear.api.profile_routes import router as profile_router
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.settings import Settings
from nosolear.startup import prepare_process


class HealthResponse(BaseModel):
    status: Literal["ok"]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = app.state.settings
    prepare_process(settings, create_data_dir=True)
    engine = create_engine_for(settings.database_url)
    upgrade_to_head(engine)
    app.state.engine = engine
    try:
        yield
    finally:
        engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Nosolear", lifespan=_lifespan)
    app.state.settings = settings or Settings()
    app.include_router(profile_router)

    @app.get("/api/health")
    def health() -> HealthResponse:  # pyright: ignore[reportUnusedFunction]
        return HealthResponse(status="ok")

    return app
