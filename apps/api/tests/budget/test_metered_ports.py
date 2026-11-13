from datetime import UTC, datetime

import pytest
from factories import FixedClock
from fakes import FakeUsageLedger
from provider_fakes import FakeScorer, FakeTranscriber, assessment, transcript
from wavs import write_wav

from nosolear.budget.meter import Meter
from nosolear.budget.metered_ports import MeteredPronunciationScorer, MeteredTranscriber
from nosolear.domain.budget import Caps, Provider, Unit
from nosolear.domain.errors import CapExceeded, RequestNotSent

T0 = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
CAPS = Caps(azure_audio_seconds=100, azure_tts_chars=100, claude_tokens=100)


def _usage(ledger: FakeUsageLedger):
    usage = ledger.usage(Provider.AZURE, Unit.AUDIO_SECONDS)
    return usage.recorded, usage.reserved


def test_a_2_4_second_clip_reserves_and_records_3_audio_seconds(tmp_path):
    ledger = FakeUsageLedger(CAPS, FixedClock(T0))
    fake = FakeScorer(results=[assessment()])
    wav = write_wav(tmp_path / "a.wav", 2.4)
    MeteredPronunciationScorer(fake, Meter(ledger)).score(wav, reference_text="vest")
    assert _usage(ledger) == (3, 0)
    assert len(fake.calls) == 1


def test_an_estimate_over_the_cap_makes_no_call(tmp_path):
    ledger = FakeUsageLedger(
        Caps(azure_audio_seconds=2, azure_tts_chars=2, claude_tokens=2), FixedClock(T0)
    )
    fake = FakeScorer(results=[assessment()])
    wav = write_wav(tmp_path / "a.wav", 2.4)
    with pytest.raises(CapExceeded):
        MeteredPronunciationScorer(fake, Meter(ledger)).score(wav, reference_text="vest")
    assert fake.calls == []


def test_request_not_sent_leaves_no_recorded_usage(tmp_path):
    ledger = FakeUsageLedger(CAPS, FixedClock(T0))
    fake = FakeScorer(errors=[RequestNotSent()])
    wav = write_wav(tmp_path / "a.wav", 2.4)
    with pytest.raises(RequestNotSent):
        MeteredPronunciationScorer(fake, Meter(ledger)).score(wav, reference_text="vest")
    assert _usage(ledger) == (0, 0)


def test_a_non_wav_input_reserves_nothing(tmp_path):
    ledger = FakeUsageLedger(CAPS, FixedClock(T0))
    fake = FakeScorer(results=[assessment()])
    wav = tmp_path / "bad.wav"
    wav.write_bytes(b"not a wav")
    with pytest.raises(RequestNotSent):
        MeteredPronunciationScorer(fake, Meter(ledger)).score(wav, reference_text="vest")
    assert _usage(ledger) == (0, 0)
    assert fake.calls == []


def test_metered_transcriber_records_the_audio_seconds(tmp_path):
    ledger = FakeUsageLedger(CAPS, FixedClock(T0))
    fake = FakeTranscriber(results=[transcript("hello")])
    wav = write_wav(tmp_path / "a.wav", 2.4)
    assert MeteredTranscriber(fake, Meter(ledger)).transcribe(wav).text == "hello"
    assert _usage(ledger) == (3, 0)


def test_metered_transcriber_releases_on_request_not_sent(tmp_path):
    ledger = FakeUsageLedger(CAPS, FixedClock(T0))
    fake = FakeTranscriber(errors=[RequestNotSent()])
    wav = write_wav(tmp_path / "a.wav", 2.4)
    with pytest.raises(RequestNotSent):
        MeteredTranscriber(fake, Meter(ledger)).transcribe(wav)
    assert _usage(ledger) == (0, 0)
