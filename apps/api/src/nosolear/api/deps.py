"""Composition root: wires adapters to the routes."""

from typing import cast

from fastapi import Request
from sqlalchemy import Engine

from nosolear.adapters.content_files import load_pack
from nosolear.adapters.environment import SystemEnvironment
from nosolear.app.check_readiness import check_readiness
from nosolear.domain.packs import LanguagePack
from nosolear.domain.readiness import ReadinessReport
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.repositories import ProfileRepository
from nosolear.ports.environment import EnvironmentProbe
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


def get_readiness_report(request: Request) -> ReadinessReport:
    """The route's only dependency; tests override it."""
    return check_readiness(get_settings(request), get_environment())
