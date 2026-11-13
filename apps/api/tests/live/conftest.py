from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from live_support import require_keys

from nosolear.adapters.azure_speech import AzureSpeech
from nosolear.adapters.azure_tts import AzureTts
from nosolear.adapters.system_clock import SystemClock
from nosolear.adapters.tts_cache import CachedSynthesizer
from nosolear.api.deps import build_ledger, paid_speech_synthesizer
from nosolear.budget.meter import Meter
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.tts_cache import TtsCacheRepository
from nosolear.ports.ledger import UsageLedger
from nosolear.settings import Settings

__all__ = ["live_settings", "require_keys"]


@pytest.fixture
def live_settings(tmp_path: Path) -> Settings:
    """The real environment and `.env`, but never the real data directory."""
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
def require_azure(live_settings: Settings) -> None:
    require_keys(live_settings, "azure")


@pytest.fixture
def require_anthropic(live_settings: Settings) -> None:
    require_keys(live_settings, "anthropic")


@pytest.fixture
def real_ledger() -> Iterator[UsageLedger]:
    """The user's real database, so live calls count against the real caps (ARCHITECTURE.md 12)."""
    settings = Settings()
    engine = create_engine_for(settings.database_url)
    upgrade_to_head(engine)
    yield build_ledger(settings, engine)
    engine.dispose()


@pytest.fixture
def live_meter(real_ledger: UsageLedger) -> Meter:
    return Meter(real_ledger)


@pytest.fixture
def live_azure(live_settings: Settings, require_azure: None) -> AzureSpeech:
    return AzureSpeech(key=live_settings.azure_speech_key, region=live_settings.azure_speech_region)


@pytest.fixture
def tts_clip(
    live_settings: Settings, live_azure: AzureSpeech, live_meter: Meter, tmp_path: Path
) -> Iterator[Callable[..., Path]]:
    """A factory: synthesizes through the cache and metered stack; returns the WAV in `tmp_path`."""
    engine = create_engine_for(f"sqlite:///{tmp_path / 'cache.sqlite'}")
    upgrade_to_head(engine)
    voice, locale = live_settings.tts_voice, live_settings.azure_locale
    raw = AzureTts(live_azure, voice=voice, locale=locale)
    port = paid_speech_synthesizer(raw, live_meter, voice=voice, locale=locale)
    cached = CachedSynthesizer(
        port,
        store=TtsCacheRepository(engine),
        data_dir=tmp_path,
        voice=voice,
        clock=SystemClock(),
    )

    def make(text: str, rate_percent: int = 0) -> Path:
        return tmp_path / cached.synthesize(text, rate_percent=rate_percent).path

    yield make
    engine.dispose()
