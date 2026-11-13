"""Sound and prosody opportunities from Azure pronunciation and the phone probe."""

from dataclasses import replace

from factories import PACK, TAX, pa_phone, pa_result, pa_word, probe_result

from nosolear.domain.estimates import Prior
from nosolear.domain.extraction.opportunities import tracked_keys
from nosolear.domain.extraction.phones import probe_words
from nosolear.domain.extraction.sounds import (
    azure_opportunities,
    clear_substitute,
    probe_opportunities,
)
from nosolear.domain.packs import PackHypothesis
from nosolear.domain.scoring import V0_THRESHOLDS, Thresholds

ALL = tracked_keys(TAX, PACK)


def v0(_: str) -> Thresholds:
    return V0_THRESHOLDS


def _missed(opps: list, key: str) -> list[bool]:
    return [o.missed for o in opps if o.error_key == key]


def test_substitution_needs_a_clear_margin() -> None:
    r = pa_result(
        [
            pa_word(
                "vest",
                [pa_phone("v", 30, [("w", 80), ("v", 40)]), pa_phone("ɛ", 95), pa_phone("s", 95)],
            )
        ]
    )
    assert _missed(azure_opportunities(r, keys=ALL, thresholds_for=v0), "sound.sub.v.w") == [True]

    def strict(_: str) -> Thresholds:
        return replace(V0_THRESHOLDS, nbest_margin=50.0)

    assert _missed(azure_opportunities(r, keys=ALL, thresholds_for=strict), "sound.sub.v.w") == [
        False
    ]


def test_every_expected_phone_is_one_opportunity_per_sub_key() -> None:
    r = pa_result(
        [
            pa_word(
                "vivid",
                [
                    pa_phone("v", 95, [("v", 95)]),
                    pa_phone("ɪ", 95),
                    pa_phone("v", 95, [("v", 95)]),
                ],
            )
        ]
    )
    opps = azure_opportunities(r, keys=ALL, thresholds_for=v0)
    assert sum(o.error_key == "sound.sub.v.w" for o in opps) == 2


def test_no_nbest_means_no_substitution_opportunities() -> None:
    r = pa_result([pa_word("think", [pa_phone("θ", 20)])], has_nbest=False)
    opps = azure_opportunities(r, keys=ALL, thresholds_for=v0)
    assert not [o for o in opps if o.error_key.startswith("sound.sub.")]
    assert [(o.error_key, o.missed) for o in opps if o.error_key == "sound.low.θ"] == [
        ("sound.low.θ", True)
    ]


def test_weak_sound_only_without_a_clear_substitute() -> None:
    r = pa_result([pa_word("think", [pa_phone("θ", 30, [("t", 90), ("θ", 30)])])])
    got = {o.error_key: o.missed for o in azure_opportunities(r, keys=ALL, thresholds_for=v0)}
    assert got["sound.sub.θ.t"] is True and got["sound.low.θ"] is False


def test_clear_substitute_ignores_the_expected_phone_and_ties_by_name() -> None:
    assert clear_substitute(pa_phone("θ", 30, [("θ", 99)]), 10.0) is None
    tie = pa_phone("θ", 30, [("t", 90), ("s", 90)])
    assert clear_substitute(tie, 10.0) == "s"


def test_omitted_and_inserted_words_are_skipped() -> None:
    r = pa_result(
        [
            pa_word("the", [pa_phone("θ", 10)], error_type="Omission"),
            pa_word("vest", [pa_phone("v", 10)], error_type="Insertion"),
        ]
    )
    assert azure_opportunities(r, keys=ALL, thresholds_for=v0) == []


def test_prosody_only_when_returned() -> None:
    words = [
        pa_word("one", [pa_phone("w", 90)]),
        pa_word("two", [pa_phone("u", 90)], prosody=["UnexpectedBreak"]),
    ]
    opps = azure_opportunities(pa_result(words, has_prosody=False), keys=ALL, thresholds_for=v0)
    assert not [o for o in opps if o.error_key.startswith("prosody.")]
    opps = azure_opportunities(pa_result(words, has_prosody=True), keys=ALL, thresholds_for=v0)
    assert _missed(opps, "prosody.unexpected_break") == [True]


def test_break_flags_skip_the_first_scored_word() -> None:
    words = [
        pa_word("one", [pa_phone("w", 90)], prosody=["MissingBreak"]),
        pa_word("two", [pa_phone("u", 90)], prosody=["MissingBreak"]),
        pa_word("three", [pa_phone("n", 90)]),
    ]
    opps = azure_opportunities(pa_result(words), keys=ALL, thresholds_for=v0)
    assert _missed(opps, "prosody.missing_break") == [True, False]


def test_monotone_is_one_opportunity_per_clip() -> None:
    words = [
        pa_word("one", [pa_phone("w", 90)], prosody=["Monotone"]),
        pa_word("two", [pa_phone("u", 90)], prosody=["Monotone"]),
    ]
    opps = azure_opportunities(pa_result(words), keys=ALL, thresholds_for=v0)
    assert _missed(opps, "prosody.monotone") == [True]
    silent = azure_opportunities(
        pa_result([pa_word("x", [], error_type="Omission")]), keys=ALL, thresholds_for=v0
    )
    assert _missed(silent, "prosody.monotone") == []


def test_dynamic_pack_key_is_tracked() -> None:
    pack = replace(
        PACK,
        hypotheses=(PackHypothesis("sound.sub.p.b", "reason", Prior(1.0, 1.0)),),
    )
    keys = tracked_keys(TAX, pack)
    assert "sound.sub.p.b" in keys
    r = pa_result([pa_word("pen", [pa_phone("p", 90, [("b", 95), ("p", 40)])])])
    got = _missed(azure_opportunities(r, keys=keys, thresholds_for=v0), "sound.sub.p.b")
    assert got == [True]


def test_probe_epenthesis_and_final_cluster() -> None:
    r = probe_result(
        "school", expected_words=[["s", "k", "u", "l"]], heard=["ɪ", "s", "k", "u", "l"]
    )
    got = {o.error_key: o.missed for o in probe_opportunities(r, reference_text="school", keys=ALL)}
    assert got["sound.ins.epenthesis_sC"] is True and "sound.del.final_cluster" not in got


def test_probe_substitution_counts_deleted_phones_as_ok() -> None:
    r = probe_result("vest", expected_words=[["v", "ɛ", "s", "t"]], heard=["w", "ɛ", "t"])
    keys = frozenset({"sound.sub.v.w", "sound.sub.s.t"})
    opps = probe_opportunities(r, reference_text="vest", keys=keys)
    # the /s/ is deleted, an edit that is not a substitution of /t/
    assert [(o.error_key, o.missed) for o in opps] == [
        ("sound.sub.v.w", True),
        ("sound.sub.s.t", False),
    ]


def test_probe_words_split_edits_by_word() -> None:
    r = probe_result(
        "the school",
        expected_words=[["ð", "ə"], ["s", "k", "u", "l"]],
        heard=["ð", "ə", "ɪ", "s", "k", "u", "l"],
    )
    words = probe_words(r, reference_text="the school")
    assert [w.text for w in words] == ["the", "school"]
    assert [(e.op, e.expected_index) for e in words[1].edits] == [
        ("ins", 0),
        ("match", 0),
        ("match", 1),
        ("match", 2),
        ("match", 3),
    ]
    assert all(e.op == "match" for e in words[0].edits)


def test_probe_words_has_no_text_when_token_count_differs() -> None:
    r = probe_result(
        "the school", expected_words=[["s", "k", "u", "l"]], heard=["s", "k", "u", "l"]
    )
    assert [w.text for w in probe_words(r, reference_text="the school")] == [None]


def test_evidence_carries_word_span_and_phones() -> None:
    r = pa_result([pa_word("vest", [pa_phone("v", 30, [("w", 80)])], start_ms=100, end_ms=520)])
    opp = [
        o
        for o in azure_opportunities(r, keys=ALL, thresholds_for=v0)
        if o.error_key == "sound.sub.v.w"
    ]
    assert opp[0].evidence == {
        "word": "vest",
        "start_ms": 100,
        "end_ms": 520,
        "expected": "v",
        "produced": "w",
        "score": 30,
    }
