from typing import Literal

import pytest

from nosolear.settings import Settings

Provider = Literal["azure", "anthropic"]


def _missing(settings: Settings, provider: Provider) -> list[str]:
    if provider == "azure":
        pairs = {
            "NOSOLEAR_AZURE_SPEECH_KEY": settings.azure_speech_key,
            "NOSOLEAR_AZURE_SPEECH_REGION": settings.azure_speech_region,
        }
    else:
        pairs = {"NOSOLEAR_ANTHROPIC_API_KEY": settings.anthropic_api_key}
    return [name for name, value in pairs.items() if value is None]


def require_keys(settings: Settings, *providers: Provider) -> None:
    """Skip the test when a provider's settings are unset. Names variables, never values."""
    missing = [name for provider in providers for name in _missing(settings, provider)]
    if missing:
        pytest.skip("live test needs " + ", ".join(missing) + " (set in env or .env)")
