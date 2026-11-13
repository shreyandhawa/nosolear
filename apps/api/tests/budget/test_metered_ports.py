from datetime import UTC, datetime

import pytest
from factories import FixedClock
from fakes import FakeUsageLedger
from provider_fakes import (
    FakeCoach,
    FakeScorer,
    FakeSpeechSynthesizer,
    FakeTranscriber,
    assessment,
    raw_result,
    transcript,
)
from wavs import write_wav

from nosolear.budget.estimators import claude_tokens
from nosolear.budget.meter import Meter
from nosolear.budget.metered_ports import (
    MeteredCoach,
    MeteredPronunciationScorer,
    MeteredSpeechSynthesizer,
    MeteredTranscriber,
)
from nosolear.domain.budget import Caps, Provider, Unit
from nosolear.domain.coach import (
    ANALYZE_MAX_TOKENS,
    CoachAnalysis,
    CoachTask,
    analysis_request,
    coach_keys,
)
from nosolear.domain.errors import CapExceeded, RequestNotSent
from nosolear.domain.speech import SynthesizedAudio
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX

T0 = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
CAPS = Caps(azure_audio_seconds=100, azure_tts_chars=100, claude_tokens=100)
CAPS_TTS = Caps(azure_audio_seconds=100, azure_tts_chars=100_000, claude_tokens=100)
JENNY = "en-US-JennyNeural"


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


def test_tts_reserves_both_voices_and_records_billed(tmp_path):
    ledger = FakeUsageLedger(
        Caps(azure_audio_seconds=100, azure_tts_chars=100_000, claude_tokens=100), FixedClock(T0)
    )
    fake = FakeSpeechSynthesizer(
        results=[SynthesizedAudio(wav=b"", word_timings=(), voice=JENNY, billed_chars=123)]
    )
    port = MeteredSpeechSynthesizer(fake, Meter(ledger), voice=JENNY, locale="en-US")
    port.synthesize("hello", rate_percent=0)
    usage = ledger.usage(Provider.AZURE, Unit.TTS_CHARS)
    assert (usage.recorded, usage.reserved) == (123, 0)
    assert len(fake.calls) == 1


def test_a_tts_estimate_over_the_cap_makes_no_call():
    ledger = FakeUsageLedger(
        Caps(azure_audio_seconds=100, azure_tts_chars=100, claude_tokens=100), FixedClock(T0)
    )
    fake = FakeSpeechSynthesizer(results=[SynthesizedAudio(b"", (), JENNY, 1)])
    port = MeteredSpeechSynthesizer(fake, Meter(ledger), voice=JENNY, locale="en-US")
    with pytest.raises(CapExceeded):
        port.synthesize("hello", rate_percent=0)
    assert fake.calls == []


def test_tts_request_not_sent_releases_the_reservation():
    ledger = FakeUsageLedger(CAPS_TTS, FixedClock(T0))
    fake = FakeSpeechSynthesizer(errors=[RequestNotSent()])
    port = MeteredSpeechSynthesizer(fake, Meter(ledger), voice=JENNY, locale="en-US")
    with pytest.raises(RequestNotSent):
        port.synthesize("hello", rate_percent=0)
    usage = ledger.usage(Provider.AZURE, Unit.TTS_CHARS)
    assert (usage.recorded, usage.reserved) == (0, 0)


COACH_KEYS = coach_keys(TAX, CoachTask.QUICK_ANSWERS)
COACH_CAPS = Caps(azure_audio_seconds=100, azure_tts_chars=100, claude_tokens=100_000)


def _coach_analysis(tokens: int) -> CoachAnalysis:
    return CoachAnalysis(
        findings=(),
        rubric=None,
        rewrite=None,
        dropped=0,
        tokens_used=tokens,
        raw=raw_result(adapter="claude_coach", provider="anthropic"),
    )


def test_coach_reserves_upper_bound():
    ledger = FakeUsageLedger(COACH_CAPS, FixedClock(T0))
    fake = FakeCoach(results=[_coach_analysis(500)])
    MeteredCoach(fake, Meter(ledger), taxonomy=TAX).analyze(
        task=CoachTask.QUICK_ANSWERS,
        prompt_text="Why?",
        transcript="I go yesterday",
        allowed_keys=COACH_KEYS,
    )
    request = analysis_request(
        task=CoachTask.QUICK_ANSWERS,
        prompt_text="Why?",
        transcript="I go yesterday",
        allowed_keys=COACH_KEYS,
        taxonomy=TAX,
    )
    assert claude_tokens(request) >= len(request.system.encode()) + ANALYZE_MAX_TOKENS
    assert claude_tokens(request) >= ANALYZE_MAX_TOKENS + 1000
    usage = ledger.usage(Provider.ANTHROPIC, Unit.TOKENS)
    assert usage.reserved == 0 and usage.recorded == 500
    assert len(fake.calls) == 1


def test_coach_records_tokens_used():
    ledger = FakeUsageLedger(COACH_CAPS, FixedClock(T0))
    fake = FakeCoach(results=[_coach_analysis(1234)])
    MeteredCoach(fake, Meter(ledger), taxonomy=TAX).analyze(
        task=CoachTask.QUICK_ANSWERS,
        prompt_text="Why?",
        transcript="I go",
        allowed_keys=COACH_KEYS,
    )
    assert ledger.usage(Provider.ANTHROPIC, Unit.TOKENS).recorded == 1234


def test_a_coach_estimate_over_the_cap_makes_no_call():
    ledger = FakeUsageLedger(
        Caps(azure_audio_seconds=1, azure_tts_chars=1, claude_tokens=10), FixedClock(T0)
    )
    fake = FakeCoach(results=[_coach_analysis(1)])
    with pytest.raises(CapExceeded):
        MeteredCoach(fake, Meter(ledger), taxonomy=TAX).analyze(
            task=CoachTask.QUICK_ANSWERS,
            prompt_text="Why?",
            transcript="I go",
            allowed_keys=COACH_KEYS,
        )
    assert fake.calls == []
