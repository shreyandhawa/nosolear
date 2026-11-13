import pytest
from provider_fakes import (
    FakeCapabilityProbe,
    FakeCoach,
    FakePhoneProbe,
    FakeScorer,
    FakeSpeechSynthesizer,
    FakeSynthesizer,
    FakeTranscriber,
    assessment,
    transcript,
)

from nosolear.domain.errors import RetryableProviderError
from nosolear.ports.providers import (
    CapabilityProbe,
    Coach,
    PhoneProbe,
    PronunciationScorer,
    SpeechSynthesizer,
    Synthesizer,
    Transcriber,
)


def test_each_fake_is_typed_as_its_port(tmp_path):
    scorer: PronunciationScorer = FakeScorer(results=[assessment()])
    transcriber: Transcriber = FakeTranscriber(results=[transcript("hi")])
    probe: PhoneProbe = FakePhoneProbe()
    raw_tts: SpeechSynthesizer = FakeSpeechSynthesizer()
    cached: Synthesizer = FakeSynthesizer(tmp_path)
    coach: Coach = FakeCoach()
    capabilities: CapabilityProbe = FakeCapabilityProbe()
    for port in (scorer, transcriber, probe, raw_tts, cached, coach, capabilities):
        assert port.layer == "raw"


def test_queued_error_raises_first_then_the_result_returns(tmp_path):
    wav = tmp_path / "a.wav"
    fake = FakeScorer(errors=[RetryableProviderError("busy")], results=[assessment()])
    with pytest.raises(RetryableProviderError):
        fake.score(wav, reference_text="vest")
    assert fake.score(wav, reference_text="vest") == assessment()
    assert fake.calls == [(wav, "vest"), (wav, "vest")]


def test_the_last_result_repeats(tmp_path):
    fake = FakeTranscriber(results=[transcript("one")])
    wav = tmp_path / "a.wav"
    assert fake.transcribe(wav).text == "one"
    assert fake.transcribe(wav).text == "one"
