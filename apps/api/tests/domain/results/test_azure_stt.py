import pytest
from adapters.azure_payloads import no_match, stt_phrase
from provider_fakes import raw_result

from nosolear.domain.errors import MalformedProviderResponse
from nosolear.domain.results import parse_azure_stt


def stt(results):
    return raw_result(adapter="azure_stt", provider_version="1.53.0", payload={"results": results})


def test_words_are_in_ms_from_ticks_with_confidence():
    raw = stt([stt_phrase("Hello there.", [("Hello", 0, 400, 0.9), ("there", 500, 300, 0.8)])])
    t = parse_azure_stt(raw)
    assert [(w.text, w.start_ms, w.end_ms, w.confidence) for w in t.words] == [
        ("Hello", 0, 400, 0.9),
        ("there", 500, 800, 0.8),
    ]
    assert t.text == "Hello there."


def test_phrases_join_their_display_text_with_a_space():
    t = parse_azure_stt(
        stt(
            [
                stt_phrase("Hello there.", [("Hello", 0, 400, 0.9)]),
                stt_phrase("How are you?", [("How", 1000, 200, 0.9)]),
            ]
        )
    )
    assert t.text == "Hello there. How are you?"
    assert [w.start_ms for w in t.words] == [0, 1000]


def test_no_match_is_an_empty_transcript_not_an_error():
    t = parse_azure_stt(stt([no_match()]))
    assert (t.text, t.words) == ("", ())


def test_fillers_are_never_kept():
    assert parse_azure_stt(stt([])).fillers_kept is False


def test_malformed_is_typed():
    with pytest.raises(MalformedProviderResponse):
        parse_azure_stt(stt(["not a phrase"]))
