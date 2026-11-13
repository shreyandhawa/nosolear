import io
import logging
import stat
from pathlib import Path

import pytest
from factories import NOW, SAMPLE_OBS, FixedClock, loopback_client, make_settings

from nosolear.api.app import create_app
from nosolear.api.deps import load_active_pack
from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository

KEY = "sk-test-0123456789abcdef"


def test_lifespan_prepares_data_dir_and_scrubbing(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    data.chmod(0o755)
    (data / "old.txt").write_text("x")
    (data / "old.txt").chmod(0o644)
    with loopback_client(create_app(make_settings(data_dir=data, anthropic_api_key=KEY))):
        stream = io.StringIO()
        log = logging.getLogger("t.lifespan")
        log.handlers = [logging.StreamHandler(stream)]
        log.propagate = False
        log.warning("k=%s", KEY)
        assert KEY not in stream.getvalue()
        assert "[redacted]" in stream.getvalue()
    assert stat.S_IMODE(data.stat().st_mode) == 0o700
    assert stat.S_IMODE((data / "old.txt").stat().st_mode) == 0o600


def test_lifespan_logs_a_pack_change_rebuild(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    data = tmp_path / "data"
    seed = make_settings(data_dir=data, pack="nepali")
    data.mkdir()
    engine = create_engine_for(seed.database_url)
    upgrade_to_head(engine)
    ObservationRepository(engine).add_many(SAMPLE_OBS)
    rebuild_profile(
        observations=ObservationRepository(engine),
        profiles=ProfileRepository(engine, DEFAULT_TAXONOMY),
        taxonomy=DEFAULT_TAXONOMY,
        pack=load_active_pack(seed),
        clock=FixedClock(NOW),
    )
    engine.dispose()
    with caplog.at_level(logging.INFO, logger="nosolear.api.app"):
        with loopback_client(create_app(make_settings(data_dir=data, pack="neutral"))):
            pass
    messages = [r.getMessage() for r in caplog.records if r.name == "nosolear.api.app"]
    assert any("nepali" in m and "neutral" in m and "rebuilt" in m for m in messages), messages
    assert not any(str(tmp_path) in m for m in messages)
