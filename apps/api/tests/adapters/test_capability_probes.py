from datetime import UTC, datetime
from pathlib import Path

from factories import FixedClock
from provider_fakes import (
    FakeScorer,
    FakeSynthesizer,
    FakeTranscriber,
    assessment,
    raw_result,
    transcript,
)

from nosolear.adapters.azure_pa_probe import AzureCapabilityProbe
from nosolear.adapters.transcriber_speed_check import TranscriberSpeedCheck
from nosolear.domain.capabilities import (
    NBEST_PHONEMES,
    PROBE_SENTENCE,
    PROSODY,
    SPEED_CHECK_PASSAGE,
)
from nosolear.domain.transcriber_choice import TranscriberName

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


def test_azure_probe_reports_what_the_tier_returned(tmp_path: Path):
    synth = FakeSynthesizer(tmp_path)
    scorer = FakeScorer(
        results=[
            assessment(
                has_nbest=True,
                has_prosody=False,
                raw=raw_result(adapter="azure_pa", provider="azure", provider_version="1.53.0"),
            )
        ]
    )
    caps = AzureCapabilityProbe(
        synthesizer=synth,
        scorer=scorer,
        data_dir=tmp_path,
        region="eastus",
        locale="en-US",
        clock=FixedClock(NOW),
    ).probe()
    assert caps.capabilities == {NBEST_PHONEMES: True, PROSODY: False}
    assert caps.provider == "azure" and caps.adapter == "azure_pa"
    assert caps.provider_version == "1.53.0" and caps.region == "eastus"
    assert scorer.calls[0][1] == PROBE_SENTENCE
    assert [text for text, _ in synth.calls] == [PROBE_SENTENCE]


def test_speed_check_excludes_warm_up(tmp_path: Path):
    ticks = iter([10.0, 22.0])  # only the passage run is timed
    transcriber = FakeTranscriber(results=[transcript("warm up")])
    check = TranscriberSpeedCheck(
        name=TranscriberName.FASTER_WHISPER,
        synthesizer=FakeSynthesizer(tmp_path, duration_ms=60_000),
        transcriber=transcriber,
        data_dir=tmp_path,
        clock=FixedClock(NOW),
        timer=lambda: next(ticks),
    )
    caps = check.probe()
    assert caps.capabilities == {"real_time_factor": 0.2, "clip_seconds": 60.0}
    assert caps.provider == "local" and caps.adapter == "faster_whisper"
    assert len(transcriber.calls) == 2


def test_the_speed_check_times_the_passage_not_the_probe_sentence(tmp_path: Path):
    synth = FakeSynthesizer(tmp_path, duration_ms=60_000)
    check = TranscriberSpeedCheck(
        name=TranscriberName.MLX_WHISPER,
        synthesizer=synth,
        transcriber=FakeTranscriber(results=[transcript("x")]),
        data_dir=tmp_path,
        clock=FixedClock(NOW),
        timer=lambda: 0.0,
    )
    check.probe()
    assert [text for text, _ in synth.calls] == [PROBE_SENTENCE, SPEED_CHECK_PASSAGE]
