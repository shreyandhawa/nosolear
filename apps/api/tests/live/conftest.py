from pathlib import Path

import pytest
from live_support import require_keys

from nosolear.settings import Settings

__all__ = ["live_settings", "require_keys"]


@pytest.fixture
def live_settings(tmp_path: Path) -> Settings:
    """The real environment and `.env`, but never the real data directory."""
    return Settings(data_dir=tmp_path / "data")
