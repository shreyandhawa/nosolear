from pathlib import Path

import pytest

from nosolear.settings import REPO_ROOT, Settings


@pytest.mark.live
def test_live_settings_never_use_the_real_data_dir(live_settings: Settings, tmp_path: Path) -> None:
    # live tests are exempt from the env isolation, so `.env` loading must be enabled
    assert Settings.model_config.get("env_file") is not None
    assert live_settings.data_dir.is_relative_to(tmp_path)
    assert live_settings.data_dir != REPO_ROOT / "data"
