import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import settings
from sqlalchemy import Engine

from nosolear.logging_setup import uninstall_secret_scrubbing
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.settings import Settings

settings.register_profile("default", max_examples=100, deadline=None)
settings.register_profile("heavy", max_examples=1000, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


@pytest.fixture
def db_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_engine_for(f"sqlite:///{tmp_path / 'db' / 't.sqlite'}")
    upgrade_to_head(engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test sees the developer's environment or real `.env` (which holds real keys).

    Live tests (added in Task 9) will be exempted from this fixture.
    """
    for name in [n for n in os.environ if n.startswith("NOSOLEAR_")]:
        monkeypatch.delenv(name)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    # prepare_process sets this and installs the log record factory; neither may leak between tests
    monkeypatch.delenv("HF_HUB_DISABLE_TELEMETRY", raising=False)
    yield
    uninstall_secret_scrubbing()
