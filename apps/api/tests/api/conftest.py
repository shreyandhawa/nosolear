from collections.abc import Iterator
from pathlib import Path

import pytest
from factories import NOW, SAMPLE_OBS, TAX
from fastapi.testclient import TestClient

from nosolear.api.app import create_app
from nosolear.domain.profile import Profile, build_profile
from nosolear.persistence.repositories import ProfileRepository
from nosolear.settings import Settings


@pytest.fixture
def client_with_tmp_db(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        yield client


@pytest.fixture
def seeded_profile(client_with_tmp_db: TestClient) -> Profile:
    profile = build_profile(SAMPLE_OBS, as_of=NOW, taxonomy=TAX)
    engine = client_with_tmp_db.app.state.engine  # pyright: ignore[reportAttributeAccessIssue]
    ProfileRepository(engine, TAX).save(profile, session_id=None, reason="rebuild")
    return profile
