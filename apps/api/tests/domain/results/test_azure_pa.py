import pytest
from adapters.azure_payloads import no_match, pa_phoneme, pa_phrase, pa_word
from provider_fakes import raw_result

from nosolear.domain.errors import MalformedProviderResponse
from nosolear.domain.results import parse_azure_pa
from nosolear.domain.speech import NBestPhoneme, ScoringMode


def pa(mode="scripted", results=None):
    return raw_result(
        adapter="azure_pa",
        provider_version="1.53.0",
        payload={"mode": mode, "reference_text": "vest", "results": results},
    )


def test_nbest_shows_w_for_v():
    word = pa_word(
        "vest",
        40,
        offset_ms=100,
        duration_ms=400,
        phonemes=[pa_phoneme("v", 22, nbest=[("w", 88), ("v", 22)], offset_ms=100, duration_ms=90)],
    )
    a = parse_azure_pa(pa(results=[pa_phrase([word])]))
    ph = a.words[0].phonemes[0]
    assert (ph.phoneme, ph.nbest[0], ph.start_ms, ph.end_ms) == (
        "v",
        NBestPhoneme("w", 88),
        100,
        190,
    )
    assert a.has_nbest


def test_tier_without_nbest_or_prosody_is_reported_not_failed():
    a = parse_azure_pa(
        pa(
            results=[
                pa_phrase(
                    [
                        pa_word(
                            "vest",
                            90,
                            offset_ms=0,
                            duration_ms=300,
                            phonemes=[pa_phoneme("v", 90, offset_ms=0, duration_ms=50)],
                        )
                    ]
                )
            ]
        )
    )
    assert (a.has_nbest, a.has_prosody, a.prosody) == (False, False, None)


def test_continuous_phrases_concatenate_in_order():
    a = parse_azure_pa(
        pa(
            "continuous",
            [
                pa_phrase([pa_word("one", 90, offset_ms=0, duration_ms=200)]),
                pa_phrase([pa_word("two", 80, offset_ms=5000, duration_ms=200)]),
            ],
        )
    )
    assert [w.word for w in a.words] == ["one", "two"]
    assert a.words[1].start_ms == 5000


def test_omitted_word_has_no_times():
    a = parse_azure_pa(
        pa(
            results=[
                pa_phrase(
                    [
                        pa_word(
                            "van",
                            None,
                            error_type="Omission",
                            offset_ms=None,
                            duration_ms=None,
                        )
                    ]
                )
            ]
        )
    )
    assert a.words[0].error_type == "Omission"
    assert a.words[0].start_ms is None


def test_silence_is_empty_not_error():
    assert parse_azure_pa(pa(results=[no_match()])).words == ()


def test_malformed_is_typed():
    with pytest.raises(MalformedProviderResponse):
        parse_azure_pa(pa(results=[{"RecognitionStatus": "Success"}]))


def test_non_numeric_score_is_malformed():
    bad = pa_phrase([pa_word("vest", 90, offset_ms=0, duration_ms=300)], accuracy="high")
    with pytest.raises(MalformedProviderResponse):
        parse_azure_pa(pa(results=[bad]))


def test_prosody_feedback_parsed():
    prosody = {
        "Break": {
            "ErrorTypes": ["UnexpectedBreak"],
            "UnexpectedBreak": {"Confidence": 0.7},
            "MissingBreak": {"Confidence": 0.1},
        },
        "Intonation": {
            "ErrorTypes": ["Monotone"],
            "Monotone": {"SyllablePitchDeltaConfidence": 0.6},
        },
    }
    word = pa_word("vest", 90, offset_ms=0, duration_ms=300, prosody=prosody)
    a = parse_azure_pa(pa(results=[pa_phrase([word], prosody=75.0)]))
    feedback = a.words[0].prosody
    assert feedback is not None
    assert feedback.error_types == ("UnexpectedBreak", "Monotone")
    assert (feedback.unexpected_break, feedback.missing_break, feedback.monotone) == (0.7, 0.1, 0.6)
    assert (a.has_prosody, a.prosody) == (True, 75.0)


def test_phrase_scores_are_weighted_by_word_count():
    short = pa_phrase([pa_word("hi", 50, offset_ms=0, duration_ms=100)], accuracy=50.0)
    long = pa_phrase(
        [pa_word(f"w{i}", 90, offset_ms=i * 100, duration_ms=100) for i in range(3)],
        accuracy=90.0,
    )
    a = parse_azure_pa(pa("continuous", [short, long]))
    assert a.accuracy == pytest.approx((50 * 1 + 90 * 3) / 4)


def test_scores_are_none_when_no_phrase_has_them():
    a = parse_azure_pa(
        pa(results=[pa_phrase([pa_word("vest", 90, offset_ms=0, duration_ms=300)], fluency=None)])
    )
    assert a.fluency is None
    assert a.mode is ScoringMode.SCRIPTED
