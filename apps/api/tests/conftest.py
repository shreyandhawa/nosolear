import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import settings
from sqlalchemy import Engine

from nosolear.persistence.db import create_engine_for, upgrade_to_head

settings.register_profile("default", max_examples=100, deadline=None)
settings.register_profile("heavy", max_examples=1000, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


@pytest.fixture
def db_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_engine_for(f"sqlite:///{tmp_path / 'db' / 't.sqlite'}")
    upgrade_to_head(engine)
    yield engine
    engine.dispose()
