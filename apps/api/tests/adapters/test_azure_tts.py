"""`AzureTts` through the fake backend: voice fallback, word timings, billing and audio checks."""

import pytest
from provider_fakes import FakeSpeechBackend
from pydantic import SecretStr
from security.planted import PLANTED_AZURE_KEY
from wavs import make_wav

from nosolear.adapters.azure_speech import (
    AzureSpeech,
    Cancellation,
    SynthesisOutcome,
    WordBoundary,
)
from nosolear.adapters.azure_tts import AzureTts
from nosolear.domain.errors import (
    MalformedProviderResponse,
    ProviderUnavailable,
    RetryableProviderError,
)
from nosolear.domain.ssml import FALLBACK_VOICE, build_ssml

JENNY = "en-US-JennyNeural"
LOCALE = "en-US"


def ok(boundaries: tuple[WordBoundary, ...] = ()) -> SynthesisOutcome:
    return SynthesisOutcome(
        audio=make_wav(0.5, freq=None), word_boundaries=boundaries, cancellation=None
    )


def rejected(code: str) -> SynthesisOutcome:
    return SynthesisOutcome(audio=b"", word_boundaries=(), cancellation=Cancellation(code, ""))


def tts_over(backend: FakeSpeechBackend) -> AzureTts:
    speech = AzureSpeech(key=SecretStr(PLANTED_AZURE_KEY), region="eastus", backend=backend)
    return AzureTts(speech, voice=JENNY, locale=LOCALE)


def test_sends_configured_voice_and_returns_word_timings():
    backend = FakeSpeechBackend(
        synthesis=[
            ok(
                (
                    WordBoundary("hello", 0, 4_000_000),
                    WordBoundary("world", 5_000_000, 4_000_000),
                )
            )
        ]
    )
    audio = tts_over(backend).synthesize("hello world", rate_percent=0)
    assert f"<voice name='{JENNY}'>" in backend.calls[0]
    assert [(w.text, w.start_ms, w.end_ms) for w in audio.word_timings] == [
        ("hello", 0, 400),
        ("world", 500, 900),
    ]
    assert audio.voice == JENNY


def test_falls_back_to_ava_once_on_bad_request_then_remembers():
    backend = FakeSpeechBackend(synthesis=[rejected("BadRequest"), ok()])
    tts = tts_over(backend)
    tts.synthesize("hello", rate_percent=0)
    second = tts.synthesize("hello again", rate_percent=0)
    assert f"name='{FALLBACK_VOICE}'" in backend.calls[1]
    assert f"name='{FALLBACK_VOICE}'" in backend.calls[2]
    assert len(backend.calls) == 3
    assert second.voice == FALLBACK_VOICE


def test_no_fallback_on_429():
    backend = FakeSpeechBackend(synthesis=[rejected("TooManyRequests")])
    with pytest.raises(RetryableProviderError):
        tts_over(backend).synthesize("hello", rate_percent=0)
    assert len(backend.calls) == 1


def test_both_voices_rejected_is_provider_unavailable():
    backend = FakeSpeechBackend(synthesis=[rejected("BadRequest"), rejected("BadRequest")])
    with pytest.raises(ProviderUnavailable) as info:
        tts_over(backend).synthesize("hello", rate_percent=0)
    assert str(info.value) == "Azure Speech rejected the request"
    assert len(backend.calls) == 2


def test_billed_chars_is_sum_of_ssml_sent():
    backend = FakeSpeechBackend(synthesis=[rejected("BadRequest"), ok()])
    audio = tts_over(backend).synthesize("hello", rate_percent=-25)
    sent = sum(len(ssml) for ssml in backend.calls)
    assert audio.billed_chars == sent
    assert sent == len(build_ssml("hello", voice=JENNY, locale=LOCALE, rate_percent=-25)) + len(
        build_ssml("hello", voice=FALLBACK_VOICE, locale=LOCALE, rate_percent=-25)
    )


def test_non_16k_audio_is_malformed():
    backend = FakeSpeechBackend(
        synthesis=[
            SynthesisOutcome(
                audio=make_wav(0.5, rate=24000, freq=None), word_boundaries=(), cancellation=None
            )
        ]
    )
    with pytest.raises(MalformedProviderResponse):
        tts_over(backend).synthesize("hello", rate_percent=0)
