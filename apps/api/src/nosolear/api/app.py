import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Engine

from nosolear.adapters.system_clock import SystemClock
from nosolear.api.deps import RawPorts, Services, build_services, load_active_pack
from nosolear.api.errors import install_error_handlers
from nosolear.api.guards import RequestGuardMiddleware
from nosolear.api.job_routes import router as job_router
from nosolear.api.profile_routes import router as profile_router
from nosolear.api.readiness_routes import router as readiness_router
from nosolear.api.recording_routes import router as recording_router
from nosolear.api.rescore_routes import router as rescore_router
from nosolear.app.ensure_profile_pack import ensure_profile_pack
from nosolear.app.steps import StepRegistry
from nosolear.domain.packs import PackError
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.ports.clock import Clock
from nosolear.ports.ledger import UsageLedger
from nosolear.settings import Settings
from nosolear.startup import prepare_process

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"]


def _prepare(app: FastAPI, settings: Settings, engine: Engine) -> Services:
    """Everything that must hold before the first request: schema, pack, reservations, jobs."""
    upgrade_to_head(engine)
    services = build_services(
        settings,
        engine,
        registry=cast(StepRegistry | None, app.state.step_registry),
        clock=cast(Clock, app.state.clock),
        ledger=cast(UsageLedger | None, app.state.ledger),
        raw_ports=cast(RawPorts | None, app.state.raw_ports),
    )
    try:
        pack = load_active_pack(settings)
        previous_pack = services.profiles.latest_pack_id()
        if ensure_profile_pack(
            observations=services.observations,
            profiles=services.profiles,
            taxonomy=DEFAULT_TAXONOMY,
            pack=pack,
            clock=services.clock,
        ):
            logger.info("profile rebuilt for pack %s (was %s)", pack.id, previous_pack)
    except PackError as exc:
        logger.warning("language pack not applied: %s", exc)
    services.ledger.settle_open_reservations()
    services.jobs.requeue_running()
    return services


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = app.state.settings
    prepare_process(settings, create_data_dir=True)
    engine = create_engine_for(settings.database_url)
    try:
        services = _prepare(app, settings, engine)
    except BaseException:
        engine.dispose()
        raise
    app.state.engine = engine
    app.state.services = services
    try:
        if app.state.start_runner:
            services.runner.start()
            services.runner.wake()
        yield
    finally:
        services.runner.stop()
        engine.dispose()


def create_app(
    settings: Settings | None = None,
    *,
    step_registry: StepRegistry | None = None,
    start_runner: bool = True,
    ledger: UsageLedger | None = None,
    clock: Clock | None = None,
    raw_ports: RawPorts | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Nosolear",
        lifespan=_lifespan,
        # Swagger UI and ReDoc load JavaScript from a CDN into the API's origin (spec §16).
        docs_url=None,
        redoc_url=None,
    )
    settings = settings or Settings()
    app.state.settings = settings
    app.state.step_registry = step_registry
    app.state.start_runner = start_runner
    app.state.ledger = ledger
    app.state.clock = clock or SystemClock()
    app.state.raw_ports = raw_ports
    app.include_router(profile_router)
    app.include_router(readiness_router)
    app.include_router(job_router)
    app.include_router(recording_router)
    app.include_router(rescore_router)
    install_error_handlers(app)

    @app.get("/api/health")
    def health() -> HealthResponse:  # pyright: ignore[reportUnusedFunction]
        return HealthResponse(status="ok")

    # CORS first, guard last: the guard is outermost and refuses before CORS answers anything.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.app_origins),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["content-type"],
        allow_credentials=False,
    )
    app.add_middleware(RequestGuardMiddleware, port=settings.port, app_origins=settings.app_origins)
    return app
