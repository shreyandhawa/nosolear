"""Fluency opportunities from the ASR transcript (asr_metrics)."""

from factories import TAX, transcript, transcript_from

from nosolear.domain.extraction.fluency import fluency_opportunities, normalize, sentences
from nosolear.domain.extraction.opportunities import Opportunity
from nosolear.domain.scoring import V0_THRESHOLDS, Thresholds

FLUENCY = frozenset(d.key for d in TAX.defined() if d.key.startswith("fluency."))


def v0(_: str) -> Thresholds:
    return V0_THRESHOLDS


def opps(t, *, step: str, key: str) -> list[bool]:
    found = fluency_opportunities(t, step=step, keys=FLUENCY, thresholds_for=v0)
    return [o.missed for o in found if o.error_key == key]


def run(t, *, step: str) -> list[Opportunity]:
    return fluency_opportunities(t, step=step, keys=FLUENCY, thresholds_for=v0)


def test_slow_start_is_one_opportunity_per_rapid_question() -> None:
    late = transcript(("I", 3400, 3500), ("think", 3500, 3900))
    assert opps(late, step="quick_answer", key="fluency.slow_start") == [True]
    assert opps(late, step="speak", key="fluency.slow_start") == []


def test_no_answer_is_a_slow_start() -> None:
    assert opps(transcript(), step="quick_answer", key="fluency.slow_start") == [True]


def test_quick_answer_within_the_limit_is_not_a_slow_start() -> None:
    on_time = transcript(("Yes", 2900, 3100))
    assert opps(on_time, step="quick_answer", key="fluency.slow_start") == [False]


def test_fillers_long_pauses_and_false_starts_per_sentence() -> None:
    t = transcript(
        ("I", 0, 300),
        ("I", 300, 600),
        ("went", 600, 900),
        ("home.", 900, 1200),
        ("Um", 1300, 1500),
        ("it", 1500, 1600),
        ("was", 1600, 1700),
        ("late.", 1700, 2000),
    )
    assert opps(t, step="speak", key="fluency.false_start") == [True, False]
    assert opps(t, step="speak", key="fluency.filler") == [False, True]


def test_long_pause_counts_the_gap_before_a_sentence_but_not_before_the_first() -> None:
    t = transcript(
        ("Hello.", 0, 500),
        ("Then", 2800, 3000),  # a 2300 ms gap before the second sentence
        ("more.", 3000, 3300),
    )
    assert opps(t, step="speak", key="fluency.long_pause") == [False, True]
    first_gap = transcript(("Hi", 0, 300), ("there.", 2800, 3100))
    assert opps(first_gap, step="speak", key="fluency.long_pause") == [True]


def test_scripted_steps_have_no_fluency_opportunities() -> None:
    t = transcript_from("I I went home.")
    assert run(t, step="read_aloud") == []
    assert run(t, step="word_list") == []


def test_filler_evidence_flags_undercounting() -> None:
    t = transcript(("Um", 0, 300), ("yes.", 300, 600), fillers_kept=False)
    filler = [o for o in run(t, step="speak") if o.error_key == "fluency.filler"]
    assert filler[0].missed is True
    assert filler[0].evidence["undercounted"] is True
    assert filler[0].evidence["text"] == "Um yes."
    assert filler[0].evidence["start_ms"] == 0 and filler[0].evidence["end_ms"] == 600


def test_normalize_lowercases_and_strips_punctuation() -> None:
    assert normalize("Well,") == "well"
    assert normalize("\u201cUm\u201d") == "um"


def test_sentences_end_on_terminal_punctuation_and_keep_leftovers() -> None:
    t = transcript_from("a b. c d? e f! g h")
    assert [[w.text for w in s] for s in sentences(t.words)] == [
        ["a", "b."],
        ["c", "d?"],
        ["e", "f!"],
        ["g", "h"],
    ]
