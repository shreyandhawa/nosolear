from datetime import UTC, datetime

from sqlalchemy import Engine, text

from nosolear.domain.speech import ProviderCapabilities
from nosolear.persistence.capabilities import CapabilityRepository

T0 = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


def caps(probed_at: datetime, *, value: float = 0.2, adapter: str = "faster_whisper"):
    return ProviderCapabilities(
        provider="local",
        adapter=adapter,
        adapter_version=1,
        provider_version="1.2.1",
        region=None,
        locale=None,
        capabilities={"real_time_factor": value, "clip_seconds": 60.0},
        probed_at=probed_at,
    )


def test_latest_returns_the_newest_record_by_probed_at(db_engine: Engine):
    repo = CapabilityRepository(db_engine)
    repo.add(caps(T0, value=0.9))
    repo.add(caps(datetime(2026, 11, 13, 9, 0, tzinfo=UTC), value=0.3))
    repo.add(caps(datetime(2026, 11, 11, 9, 0, tzinfo=UTC), value=0.5))
    latest = repo.latest("local", "faster_whisper")
    assert latest is not None
    assert latest.capabilities["real_time_factor"] == 0.3
    assert latest.probed_at == datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


def test_latest_is_none_for_an_adapter_never_probed(db_engine: Engine):
    assert CapabilityRepository(db_engine).latest("azure", "azure_pa") is None


def test_latest_all_keeps_one_newest_record_per_provider_and_adapter(db_engine: Engine):
    repo = CapabilityRepository(db_engine)
    repo.add(caps(T0, value=0.9))
    repo.add(caps(datetime(2026, 11, 13, tzinfo=UTC), value=0.3))
    repo.add(caps(T0, value=0.12, adapter="mlx_whisper"))
    found = {(r.provider, r.adapter): r for r in repo.latest_all()}
    assert set(found) == {("local", "faster_whisper"), ("local", "mlx_whisper")}
    assert found["local", "faster_whisper"].capabilities["real_time_factor"] == 0.3


def test_a_record_round_trips_its_region_and_locale(db_engine: Engine):
    repo = CapabilityRepository(db_engine)
    azure = ProviderCapabilities(
        provider="azure",
        adapter="azure_pa",
        adapter_version=1,
        provider_version="1.53.0",
        region="eastus",
        locale="en-US",
        capabilities={"nbest_phonemes": True, "prosody": False},
        probed_at=T0,
    )
    repo.add(azure)
    assert repo.latest("azure", "azure_pa") == azure


def test_the_table_holds_no_key_column(db_engine: Engine):
    with db_engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(provider_capabilities)"))}
    assert columns == {
        "id",
        "provider",
        "adapter",
        "adapter_version",
        "provider_version",
        "region",
        "locale",
        "capabilities_json",
        "probed_at",
    }
