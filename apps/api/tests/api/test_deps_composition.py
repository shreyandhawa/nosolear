"""Every paid port the composition root builds is ordered retry -> metered -> raw, and the
synthesizer adds the clip cache outside that. Local transcribers and the phone probe are
unwrapped."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from factories import FixedClock, insert_job, make_settings
from provider_fakes import FakeScorer, FakeTranscriber, assessment, wrapper_chain
from sqlalchemy import Engine, text
from wavs import write_wav

import nosolear.api.deps as deps
from nosolear.adapters.azure_pa import AzurePronunciationScorer
from nosolear.adapters.azure_speech import AzureSpeech
from nosolear.adapters.azure_stt import AzureTranscriber
from nosolear.adapters.azure_tts import AzureTts
from nosolear.adapters.claude_coach import ClaudeCoach
from nosolear.adapters.faster_whisper import FasterWhisperTranscriber
from nosolear.adapters.retry import (
    RetryingCoach,
    RetryingPronunciationScorer,
    RetryingSpeechSynthesizer,
    RetryingTranscriber,
)
from nosolear.adapters.tts_cache import CachedSynthesizer
from nosolear.api.app import create_app
from nosolear.api.deps import (
    Providers,
    RawPorts,
    build_ledger,
    build_providers,
    build_services,
)
from nosolear.app.steps import StepRegistry, running_job
from nosolear.budget.compose import layers_of
from nosolear.budget.metered_ports import (
    MeteredCoach,
    MeteredPronunciationScorer,
    MeteredSpeechSynthesizer,
    MeteredTranscriber,
)
from nosolear.domain.errors import RequestNotSent
from nosolear.domain.jobs import JobKind
from nosolear.domain.speech import LOCAL, ProviderCapabilities
from nosolear.domain.transcriber_choice import Platform, TranscriberName
from nosolear.persistence.capabilities import CapabilityRepository
from nosolear.persistence.db import create_engine_for, upgrade_to_head

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
TAIL = ["retry", "metered", "raw"]


def assert_port_order(name: str, port: object) -> None:
    """Fails unless `port` is exactly the stack the composition rules allow for `name`."""
    expected = ["cache", *TAIL] if name == "synthesizer" else TAIL
    assert layers_of(port) == expected, f"{name} is wrapped as {layers_of(port)}"


def _engine(tmp_path: Path) -> Engine:
    engine = create_engine_for(make_settings(data_dir=tmp_path).database_url)
    upgrade_to_head(engine)
    return engine


def providers(
    tmp_path: Path, *, transcriber: str = "azure_stt", raw: RawPorts | None = None, **env: object
) -> Providers:
    settings = make_settings(data_dir=tmp_path, transcriber=transcriber, **env)
    engine = _engine(tmp_path)
    return build_providers(
        settings,
        engine=engine,
        ledger=_ledger(settings, engine),
        clock=FixedClock(NOW),
        raw=raw,
    )


def _ledger(settings, engine):
    return build_ledger(settings, engine, clock=FixedClock(NOW))


def test_every_paid_port_is_retry_then_metered_then_raw(tmp_path):
    p = providers(tmp_path)
    assert wrapper_chain(p.scorer) == [
        RetryingPronunciationScorer,
        MeteredPronunciationScorer,
        AzurePronunciationScorer,
    ]
    assert wrapper_chain(p.synthesizer) == [
        CachedSynthesizer,
        RetryingSpeechSynthesizer,
        MeteredSpeechSynthesizer,
        AzureTts,
    ]
    assert wrapper_chain(p.coach) == [RetryingCoach, MeteredCoach, ClaudeCoach]
    assert wrapper_chain(p.transcriber) == [
        RetryingTranscriber,
        MeteredTranscriber,
        AzureTranscriber,
    ]
    for name, port in p.paid_ports().items():
        assert_port_order(name, port)
    assert set(p.paid_ports()) == {
        "pronunciation_scorer",
        "synthesizer",
        "coach",
        "transcriber_azure",
    }


def _speech_of(port: object, *, depth: int) -> object:
    """The `AzureSpeech` under `depth` wrapper layers (the raw adapter holds it as `_speech`)."""
    current: Any = port
    for _ in range(depth):
        current = current.inner
    speech: object = current._speech
    return speech


def test_the_speech_adapters_share_one_client(tmp_path):
    p = providers(tmp_path)
    scorer_speech = _speech_of(p.scorer, depth=2)
    transcriber_speech = _speech_of(p.transcriber, depth=2)
    synth_speech = _speech_of(p.synthesizer, depth=3)
    assert isinstance(scorer_speech, AzureSpeech)
    assert scorer_speech is transcriber_speech is synth_speech


def test_local_transcriber_is_unmetered_and_not_in_the_azure_ports(tmp_path):
    p = providers(tmp_path, transcriber="faster_whisper")
    assert wrapper_chain(p.transcriber) == [FasterWhisperTranscriber]
    assert "transcriber_azure" not in p.paid_ports()


def test_injected_raw_ports_are_wrapped_like_real_ones(tmp_path):
    p = providers(
        tmp_path,
        raw=RawPorts(scorer=FakeScorer(), transcriber=FakeTranscriber()),
    )
    assert wrapper_chain(p.scorer) == [
        RetryingPronunciationScorer,
        MeteredPronunciationScorer,
        FakeScorer,
    ]
    assert wrapper_chain(p.transcriber) == [
        RetryingTranscriber,
        MeteredTranscriber,
        FakeTranscriber,
    ]
    assert "transcriber_azure" in p.paid_ports()


def test_build_needs_no_keys(tmp_path):
    coach = providers(tmp_path).coach
    with pytest.raises(RequestNotSent) as info:
        coach.explain(error_key="grammar.article", quote="a apple", context="I ate a apple")
    assert "NOSOLEAR_ANTHROPIC_API_KEY" in str(info.value)


def test_the_meter_records_the_job_id_of_the_running_step(tmp_path):
    settings = make_settings(data_dir=tmp_path)
    engine = _engine(tmp_path)
    ledger = _ledger(settings, engine)
    scorer = FakeScorer(results=[assessment()])
    p = build_providers(
        settings,
        engine=engine,
        ledger=ledger,
        clock=FixedClock(NOW),
        raw=RawPorts(scorer=scorer),
    )
    wav = write_wav(tmp_path / "a.wav", 1.2)
    insert_job(engine, "job-7")
    with running_job("job-7"):
        p.scorer.score(wav, reference_text=None)
    with engine.connect() as conn:
        job_ids = conn.execute(text("SELECT job_id FROM usage_ledger")).scalars().all()
    assert job_ids == ["job-7"]


def test_build_services_registers_the_provider_steps_and_keeps_given_ones(tmp_path):
    settings = make_settings(data_dir=tmp_path)
    engine = _engine(tmp_path)
    registry = StepRegistry()
    services = build_services(
        settings,
        engine,
        registry=registry,
        clock=FixedClock(NOW),
        raw_ports=RawPorts(coach=None),
    )
    try:
        for name in ("score", "transcribe", "probe", "coach"):
            assert registry.get(JobKind.ANALYZE, name) is not None
        assert services.providers.coach is not None
    finally:
        services.runner.stop(timeout=10.0)
        engine.dispose()


def test_create_app_hands_its_raw_ports_to_the_lifespan(tmp_path):
    ports = RawPorts(scorer=FakeScorer(results=[assessment()]))
    app = create_app(
        make_settings(data_dir=tmp_path), start_runner=False, raw_ports=ports, clock=FixedClock(NOW)
    )
    assert app.state.raw_ports is ports


@pytest.mark.parametrize(
    ("factor", "expected"),
    [(0.9, TranscriberName.AZURE_STT), (0.2, TranscriberName.FASTER_WHISPER)],
)
def test_the_server_auto_choice_uses_the_stored_speed(
    tmp_path, monkeypatch, factor: float, expected: TranscriberName
):
    # `doctor` and the running server must agree: both read the stored speed figures.
    settings = make_settings(data_dir=tmp_path, transcriber="auto")
    engine = _engine(tmp_path)
    CapabilityRepository(engine).add(
        ProviderCapabilities(
            provider=LOCAL,
            adapter=TranscriberName.FASTER_WHISPER.value,
            adapter_version=1,
            provider_version="small.en",
            region=None,
            locale=None,
            capabilities={"real_time_factor": factor},
            probed_at=NOW,
        )
    )
    monkeypatch.setattr(deps, "current_platform", lambda: Platform.OTHER)
    monkeypatch.setattr(
        deps, "installed_transcribers", lambda: frozenset({TranscriberName.FASTER_WHISPER})
    )
    services = build_services(settings, engine, clock=FixedClock(NOW))
    try:
        assert services.providers.transcriber_choice.name is expected
    finally:
        services.runner.stop(timeout=10.0)
        engine.dispose()
