import io
import logging
import stat
from pathlib import Path

from factories import make_settings
from fastapi.testclient import TestClient

from nosolear.api.app import create_app

KEY = "sk-test-0123456789abcdef"


def test_lifespan_prepares_data_dir_and_scrubbing(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    data.chmod(0o755)
    (data / "old.txt").write_text("x")
    (data / "old.txt").chmod(0o644)
    with TestClient(create_app(make_settings(data_dir=data, anthropic_api_key=KEY))):
        stream = io.StringIO()
        log = logging.getLogger("t.lifespan")
        log.handlers = [logging.StreamHandler(stream)]
        log.propagate = False
        log.warning("k=%s", KEY)
        assert KEY not in stream.getvalue()
        assert "[redacted]" in stream.getvalue()
    assert stat.S_IMODE(data.stat().st_mode) == 0o700
    assert stat.S_IMODE((data / "old.txt").stat().st_mode) == 0o600
