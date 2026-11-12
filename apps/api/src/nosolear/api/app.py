import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from nosolear.adapters.system_clock import SystemClock
from nosolear.api.deps import load_active_pack
from nosolear.api.profile_routes import router as profile_router
from nosolear.app.ensure_profile_pack import ensure_profile_pack
from nosolear.domain.packs import PackError
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository
from nosolear.settings import Settings
from nosolear.startup import prepare_process

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = app.state.settings
    prepare_process(settings, create_data_dir=True)
    engine = create_engine_for(settings.database_url)
    upgrade_to_head(engine)
    try:
        ensure_profile_pack(
            observations=ObservationRepository(engine),
            profiles=ProfileRepository(engine, DEFAULT_TAXONOMY),
            taxonomy=DEFAULT_TAXONOMY,
            pack=load_active_pack(settings),
            clock=SystemClock(),
        )
    except PackError as exc:
        logger.warning("language pack not applied: %s", exc)
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
