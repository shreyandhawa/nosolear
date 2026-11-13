"""Composition root: wires adapters to the routes."""

from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy import Engine

from nosolear.adapters.content_files import load_pack
from nosolear.adapters.environment import SystemEnvironment
from nosolear.app.check_readiness import check_readiness
from nosolear.domain.packs import LanguagePack
from nosolear.domain.readiness import ReadinessReport
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.repositories import ProfileRepository
from nosolear.ports.clock import Clock
from nosolear.ports.environment import EnvironmentProbe
from nosolear.ports.ledger import UsageLedger
from nosolear.settings import Settings


def get_profile_repository(request: Request) -> ProfileRepository:
    engine = cast(Engine, request.app.state.engine)
    return ProfileRepository(engine, DEFAULT_TAXONOMY)


def load_active_pack(settings: Settings) -> LanguagePack:
    """The configured pack; `PackError` propagates so each caller can report it its own way."""
    return load_pack(settings.packs_dir, settings.pack)


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_environment() -> EnvironmentProbe:
    return SystemEnvironment()


def get_readiness_report(
    settings: Annotated[Settings, Depends(get_settings)],
    env: Annotated[EnvironmentProbe, Depends(get_environment)],
) -> ReadinessReport:
    """The route's only dependency; tests override it."""
    return check_readiness(settings, env)


def build_paid_ports(settings: Settings, *, ledger: UsageLedger, clock: Clock) -> dict[str, object]:
    """Every paid port, each built through `compose_paid_port`. Empty until Phase 0d adds them."""
    return {}
