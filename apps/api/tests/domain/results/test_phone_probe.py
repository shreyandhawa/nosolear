import json

from nosolear.domain.results.phone_probe import parse_phone_probe
from nosolear.domain.speech import LOCAL, RawResult

PAYLOAD = {
    "espeak_ipa": "s_k_ˈuː_l ð_ə",
    "espeak_version": "eSpeak NG text-to-speech: 1.52.0",
    "heard_tokens": ["ɪ", "s", "k", "uː", "l"],
    "model": {"repo_id": "facebook/wav2vec2-lv-60-espeak-cv-ft", "revision": "a" * 40},
}


def raw(payload=PAYLOAD):
    return RawResult(LOCAL, "espeak-ng 1.52.0", "wav2vec2_espeak", 1, payload)


def test_expected_words_and_heard_are_normalized():
    r = parse_phone_probe(raw())
    assert r.expected_words == (("s", "k", "u", "l"), ("ð", "ə"))
    assert r.heard == ("ɪ", "s", "k", "u", "l")
    assert r.raw.adapter == "wav2vec2_espeak"


def test_re_parsing_a_stored_payload_gives_the_same_result():
    stored = json.loads(json.dumps(PAYLOAD))
    assert parse_phone_probe(raw(stored)) == parse_phone_probe(raw(PAYLOAD))


def test_an_unmapped_heard_symbol_propagates():
    from nosolear.domain.phones import UnmappedSymbol

    bad = dict(PAYLOAD, heard_tokens=["q"])
    try:
        parse_phone_probe(raw(bad))
    except UnmappedSymbol as exc:
        assert exc.symbol == "q"
    else:
        raise AssertionError("expected UnmappedSymbol")
