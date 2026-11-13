"""`AzurePronunciationScorer` through the fake backend: the request it sends and what it returns."""

import json

import pytest
from provider_fakes import FakeSpeechBackend
from pydantic import SecretStr
from security.planted import PLANTED_AZURE_KEY
from wavs import write_wav

from adapters.azure_payloads import pa_phrase, pa_word
from nosolear.adapters.azure_pa import (
    AzurePronunciationScorer,
    pronunciation_config_json,
    scoring_mode,
)
from nosolear.adapters.azure_speech import AzureSpeech, Cancellation, RecognitionOutcome
from nosolear.domain.errors import RetryableProviderError
from nosolear.domain.speech import ScoringMode


def scorer_over(*, results=(), cancel: Cancellation | None = None):
    backend = FakeSpeechBackend(
        recognition=[RecognitionOutcome(results=tuple(results), cancellation=None)],
        cancel=cancel,
    )
    speech = AzureSpeech(key=SecretStr(PLANTED_AZURE_KEY), region="eastus", backend=backend)
    return backend, AzurePronunciationScorer(speech, locale="en-US")


def one_word_phrase() -> dict[str, object]:
    return pa_phrase([pa_word("vest", 90, offset_ms=0, duration_ms=300)])


def test_short_scripted_clip_uses_once_with_miscue(tmp_path):
    backend, scorer = scorer_over(results=[one_word_phrase()])
    scorer.score(write_wav(tmp_path / "a.wav", 3.0), reference_text='He said "vest"\nthen left')
    request = backend.calls[0]
    config = json.loads(request.pronunciation_json)
    assert not request.continuous
    assert config["EnableMiscue"] is True and config["NBestPhonemeCount"] == 5
    assert config["ReferenceText"] == 'He said "vest"\nthen left'
    assert config["PhonemeAlphabet"] == "IPA"


def test_scripted_over_30s_uses_continuous_mode(tmp_path):
    backend, scorer = scorer_over(results=[one_word_phrase()])
    a = scorer.score(write_wav(tmp_path / "a.wav", 31.0), reference_text="a long sentence")
    request = backend.calls[0]
    assert request.continuous
    assert json.loads(request.pronunciation_json)["EnableMiscue"] is False
    assert a.mode is ScoringMode.CONTINUOUS


def test_no_reference_is_unscripted(tmp_path):
    backend, scorer = scorer_over(results=[one_word_phrase()])
    a = scorer.score(write_wav(tmp_path / "a.wav", 3.0), reference_text=None)
    request = backend.calls[0]
    assert request.continuous
    assert json.loads(request.pronunciation_json)["ReferenceText"] == ""
    assert a.mode is ScoringMode.UNSCRIPTED


def test_timeout_is_twice_the_audio_plus_thirty_seconds(tmp_path):
    backend, scorer = scorer_over(results=[one_word_phrase()])
    scorer.score(write_wav(tmp_path / "a.wav", 3.0), reference_text="vest")
    assert backend.calls[0].timeout_s == pytest.approx(2 * 3.0 + 30)


def test_raw_carries_versions(tmp_path):
    backend, scorer = scorer_over(results=[one_word_phrase()])
    raw = scorer.score(write_wav(tmp_path / "a.wav", 3.0), reference_text="vest").raw
    assert (raw.provider, raw.adapter, raw.adapter_version) == ("azure", "azure_pa", 1)
    assert raw.provider_version == backend.version


def test_429_is_retryable(tmp_path):
    _, scorer = scorer_over(cancel=Cancellation("TooManyRequests", ""))
    with pytest.raises(RetryableProviderError):
        scorer.score(write_wav(tmp_path / "a.wav", 3.0), reference_text="vest")


@pytest.mark.parametrize(
    ("reference", "duration", "expected"),
    [
        ("vest", 3.0, ScoringMode.SCRIPTED),
        ("vest", 30.0, ScoringMode.SCRIPTED),
        ("vest", 30.5, ScoringMode.CONTINUOUS),
        (None, 3.0, ScoringMode.UNSCRIPTED),
        ("", 3.0, ScoringMode.UNSCRIPTED),
    ],
)
def test_scoring_mode(reference, duration, expected):
    assert scoring_mode(reference, duration) is expected


def test_pronunciation_config_json_matches_the_spec():
    config = json.loads(pronunciation_config_json("vest", ScoringMode.SCRIPTED))
    assert config == {
        "ReferenceText": "vest",
        "GradingSystem": "HundredMark",
        "Granularity": "Phoneme",
        "EnableMiscue": True,
        "PhonemeAlphabet": "IPA",
        "NBestPhonemeCount": 5,
        "EnableProsodyAssessment": True,
    }
    assert (
        json.loads(pronunciation_config_json(None, ScoringMode.UNSCRIPTED))["EnableMiscue"] is False
    )
