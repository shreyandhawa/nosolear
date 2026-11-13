import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import settings
from sqlalchemy import Engine

from nosolear.logging_setup import uninstall_secret_scrubbing
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.settings import Settings

pytest_plugins = ("harness",)

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
def _isolated_settings(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[None]:
    """No test sees the developer's environment or real `.env` (which holds real keys).

    Tests marked `live` are exempt from the env and `.env` isolation (they need the real keys);
    the scrubbing, umask and HF restore below still apply to them.
    """
    if request.node.get_closest_marker("live") is None:
        for name in [n for n in os.environ if n.startswith("NOSOLEAR_")]:
            monkeypatch.delenv(name)
        monkeypatch.setitem(Settings.model_config, "env_file", None)
    # prepare_process sets HF_HUB_DISABLE_TELEMETRY, the umask and the log record factory;
    # none of them may leak between tests
    telemetry = os.environ.pop("HF_HUB_DISABLE_TELEMETRY", None)
    umask = os.umask(0)
    os.umask(umask)
    yield
    uninstall_secret_scrubbing()
    os.umask(umask)
    os.environ.pop("HF_HUB_DISABLE_TELEMETRY", None)
    if telemetry is not None:
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = telemetry
