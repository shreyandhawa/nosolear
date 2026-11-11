"""Composition root: wires adapters to the routes."""

from typing import cast

from fastapi import Request
from sqlalchemy import Engine

from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.repositories import ProfileRepository


def get_profile_repository(request: Request) -> ProfileRepository:
    engine = cast(Engine, request.app.state.engine)
    return ProfileRepository(engine, DEFAULT_TAXONOMY)
