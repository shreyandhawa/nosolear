"""Composition root: wires adapters to the routes."""

from typing import cast

from fastapi import Request
from sqlalchemy import Engine

from nosolear.adapters.content_files import load_pack
from nosolear.domain.packs import LanguagePack
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.repositories import ProfileRepository
from nosolear.settings import Settings


def get_profile_repository(request: Request) -> ProfileRepository:
    engine = cast(Engine, request.app.state.engine)
    return ProfileRepository(engine, DEFAULT_TAXONOMY)


def load_active_pack(settings: Settings) -> LanguagePack:
    """The configured pack; `PackError` propagates so each caller can report it its own way."""
    return load_pack(settings.packs_dir, settings.pack)
