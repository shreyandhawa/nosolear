"""Which live probes `doctor --probe` builds: Azure always, and a speed check only for each local
transcriber that is installed on its platform (crisper_whisper only when it is the choice)."""

from datetime import UTC, datetime

import pytest
from factories import FixedClock, make_settings
from provider_fakes import FakeCoach, FakeScorer, FakeSynthesizer, FakeTranscriber
from sqlalchemy import Engine

import nosolear.api.deps as deps
from nosolear.adapters.azure_pa_probe import AzureCapabilityProbe
from nosolear.adapters.transcriber_speed_check import TranscriberSpeedCheck
from nosolear.api.deps import Providers, build_capability_probes
from nosolear.domain.transcriber_choice import Platform, TranscriberChoice, TranscriberName

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


def _providers(tmp_path) -> Providers:
    return Providers(
        scorer=FakeScorer(),
        transcriber=FakeTranscriber(),
        transcriber_choice=TranscriberChoice(
            TranscriberName.AZURE_STT, auto=True, skipped=(), warning=None
        ),
        phone_probe=None,
        synthesizer=FakeSynthesizer(tmp_path),
        coach=FakeCoach(),
    )


@pytest.mark.parametrize(
    ("installed", "platform", "setting", "expected"),
    [
        (set(), Platform.LINUX, "auto", ["azure_pa"]),
        ({"mlx_whisper"}, Platform.MACOS_ARM64, "auto", ["azure_pa", "mlx_whisper"]),
        ({"mlx_whisper"}, Platform.LINUX, "auto", ["azure_pa"]),
        ({"faster_whisper"}, Platform.LINUX, "auto", ["azure_pa", "faster_whisper"]),
        ({"crisper_whisper"}, Platform.LINUX, "auto", ["azure_pa"]),
        ({"crisper_whisper"}, Platform.LINUX, "crisper_whisper", ["azure_pa", "crisper_whisper"]),
    ],
)
def test_speed_checks_only_for_installed_transcribers_on_their_platform(
    tmp_path, db_engine: Engine, monkeypatch, installed, platform, setting, expected
):
    names = {TranscriberName(name) for name in installed}
    monkeypatch.setattr(deps, "installed_transcribers", lambda: frozenset(names))
    monkeypatch.setattr(deps, "current_platform", lambda: platform)
    settings = make_settings(data_dir=tmp_path, transcriber=setting)
    probes = build_capability_probes(
        settings, _providers(tmp_path), engine=db_engine, clock=FixedClock(NOW)
    )
    assert [probe.adapter for probe in probes] == expected
    assert isinstance(probes[0], AzureCapabilityProbe)
    assert all(isinstance(probe, TranscriberSpeedCheck) for probe in probes[1:])


def test_read_capabilities_creates_nothing_when_the_database_is_missing(tmp_path):
    settings = make_settings(data_dir=tmp_path / "absent")
    assert deps.read_capabilities(settings) == ()
    assert not (tmp_path / "absent").exists()
