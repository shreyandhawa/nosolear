import pytest
from provider_fakes import raw_result

from nosolear.domain.errors import MalformedProviderResponse
from nosolear.domain.results import parse_transcript
from nosolear.domain.results.whisper import parse_local_transcript
from nosolear.domain.speech import LOCAL, RawResult


def local(words, fillers_kept=False, adapter="faster_whisper"):
    return RawResult(
        LOCAL,
        "faster-whisper x",
        adapter,
        1,
        {
            "engine": "x",
            "model": {"repo_id": "a/b", "revision": "0" * 40},
            "fillers_kept": fillers_kept,
            "text": " ".join(w[0] for w in words),
            "words": [dict(word=w, start=s, end=e, probability=None) for w, s, e in words],
        },
    )


def test_seconds_become_ms_and_spaces_are_stripped():
    t = parse_local_transcript(local([(" Hello,", 0.0, 0.42), (" world", 0.42, 0.9)]))
    assert [(w.text, w.start_ms, w.end_ms) for w in t.words] == [
        ("Hello,", 0, 420),
        ("world", 420, 900),
    ]


def test_empty_recording_gives_empty_transcript():
    t = parse_local_transcript(local([]))
    assert t.words == () and t.text == ""


def test_probability_becomes_confidence():
    raw = local([("vest", 0.0, 0.2)])
    payload = dict(raw.payload)
    payload["words"] = [dict(word="vest", start=0.0, end=0.2, probability=0.75)]
    t = parse_local_transcript(
        RawResult(raw.provider, raw.provider_version, raw.adapter, 1, payload)
    )
    assert t.words[0].confidence == 0.75


def test_dispatch_by_adapter():
    assert parse_transcript(local([("um", 0, 0.2)], True, "crisper_whisper")).fillers_kept is True
    assert parse_transcript(local([("vest", 0, 0.2)], False, "mlx_whisper")).fillers_kept is False
    with pytest.raises(ValueError):
        parse_transcript(raw_result(adapter="nope"))


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "x", "fillers_kept": False, "words": "not a list"},
        {"text": "x", "fillers_kept": False, "words": ["not a mapping"]},
        {"text": 3, "fillers_kept": False, "words": []},
        {"text": "x", "fillers_kept": "no", "words": []},
    ],
)
def test_malformed_payload_is_malformed_provider_response(payload):
    raw = RawResult(LOCAL, "x", "faster_whisper", 1, payload)
    with pytest.raises(MalformedProviderResponse):
        parse_local_transcript(raw)
