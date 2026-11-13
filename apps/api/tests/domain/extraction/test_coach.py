"""Coach opportunities. The coach output is untrusted and is re-checked here."""

import pytest
from factories import TAX, coach_analysis, finding, transcript_from

from nosolear.domain.coach import CoachFinding
from nosolear.domain.extraction.coach import coach_opportunities, valid_findings
from nosolear.domain.taxonomy import Family

TEXT = transcript_from("I go to the market yesterday. It was fun.")
GRAMMAR = frozenset(d.key for d in TAX.defined() if d.family is Family.GRAMMAR)
ALL_COACH = frozenset(d.key for d in TAX.defined() if d.family is not Family.SUB)


@pytest.mark.parametrize(
    "bad",
    [
        finding("grammar.artcle", "the market"),  # unknown key
        finding("sound.sub.v.w", "market"),  # coach may not report sound keys
        finding("grammar.verb_tense", "I went"),  # quote not in transcript
        finding("grammar.verb_tense", None),  # grammar needs a quote
        finding("structure.missing_point", None),  # structure not judged on quick answers
        finding("grammar.article'); DROP TABLE observations;--", "x"),
    ],
)
def test_coach_output_is_untrusted(bad: CoachFinding) -> None:
    kept = valid_findings(coach_analysis([bad]), TEXT, step="quick_answer", taxonomy=TAX)
    assert kept == []


def test_unknown_step_keeps_no_findings() -> None:
    good = finding("grammar.verb_tense", "I go to")
    assert valid_findings(coach_analysis([good]), TEXT, step="read_aloud", taxonomy=TAX) == []


def test_grammar_miss_lands_in_the_quoted_sentence() -> None:
    c = coach_analysis([finding("grammar.verb_tense", "I go to")])
    got = coach_opportunities(c, TEXT, step="quick_answer", keys=GRAMMAR, taxonomy=TAX)
    verb = [o.missed for o in got if o.error_key == "grammar.verb_tense"]
    assert verb == [True, False]


def test_structure_is_one_opportunity_per_answer() -> None:
    key = "structure.missing_reason"
    c = coach_analysis([finding(key, None)])
    got = coach_opportunities(c, TEXT, step="articulate", keys=frozenset({key}), taxonomy=TAX)
    assert [o.missed for o in got] == [True]


def test_grammar_keys_are_not_judged_on_steps_without_grammar() -> None:
    c = coach_analysis([finding("grammar.verb_tense", "I go to")])
    assert coach_opportunities(c, TEXT, step="retell", keys=GRAMMAR, taxonomy=TAX) == []


def test_clarity_is_one_opportunity_per_answer_with_its_span() -> None:
    clarity = next(d.key for d in TAX.defined() if d.family is Family.CLARITY)
    c = coach_analysis([finding(clarity, None)])
    got = coach_opportunities(c, TEXT, step="speak", keys=ALL_COACH, taxonomy=TAX)
    mine = [o for o in got if o.error_key == clarity]
    assert [o.missed for o in mine] == [True]
    assert mine[0].evidence["start_ms"] == 0
