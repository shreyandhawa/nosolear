import os
from pathlib import Path

import pytest
from live_support import require_keys
from pydantic import SecretStr

from nosolear.settings import REPO_ROOT, Settings

KEY = "k" * 32


def test_require_keys_skips_naming_only_the_missing_variables(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, anthropic_api_key=SecretStr(KEY))
    with pytest.raises(pytest.skip.Exception) as info:
        require_keys(settings, "azure", "anthropic")
    message = str(info.value)
    assert "NOSOLEAR_AZURE_SPEECH_KEY" in message
    assert "NOSOLEAR_ANTHROPIC_API_KEY" not in message
    assert KEY not in message


def test_require_keys_returns_when_every_key_is_set(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        azure_speech_key=SecretStr(KEY),
        azure_speech_region="westeurope",
        anthropic_api_key=SecretStr(KEY),
    )
    require_keys(settings, "azure", "anthropic")


def test_live_settings_use_tmp_path_not_the_real_data_dir(
    live_settings: Settings, tmp_path: Path
) -> None:
    assert live_settings.data_dir.is_relative_to(tmp_path)
    assert live_settings.data_dir != REPO_ROOT / "data"


def test_non_live_tests_stay_isolated() -> None:
    assert not [n for n in os.environ if n.startswith("NOSOLEAR_")]
    assert Settings.model_config.get("env_file") is None
