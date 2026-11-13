import pytest
from factories import T0, mk, pa_result, pa_word, transcript

from nosolear.domain.coach import Rubric
from nosolear.domain.observations import Context, Observation, Outcome
from nosolear.domain.skill_scores import SessionEvidence, linear_score, skill_scores
from nosolear.domain.speech import PronunciationAssessment, Transcript, WordAssessment
from nosolear.domain.taxonomy import Skill

MISS, OK = Outcome.MISS, Outcome.OK


def _pa(*accuracies: float | None) -> PronunciationAssessment:
    words = []
    for accuracy in accuracies:
        base = pa_word("cat", [])
        words.append(
            WordAssessment(
                word=base.word,
                accuracy=accuracy,
                error_type=base.error_type,
                start_ms=base.start_ms,
                end_ms=base.end_ms,
                phonemes=base.phonemes,
                prosody=None,
            )
        )
    return pa_result(words)


def _evidence(
    *,
    scripted_pronunciation: tuple[PronunciationAssessment, ...] = (),
    sound_observations: tuple[Observation, ...] = (),
    quick_answers: tuple[Transcript, ...] = (),
    unscripted: tuple[Transcript, ...] = (),
    grammar_misses: int = 0,
    articulate_rubric: Rubric | None = None,
) -> SessionEvidence:
    return SessionEvidence(
        scripted_pronunciation=scripted_pronunciation,
        sound_observations=sound_observations,
        quick_answers=quick_answers,
        unscripted=unscripted,
        grammar_misses=grammar_misses,
        articulate_rubric=articulate_rubric,
    )


def _score(evidence: SessionEvidence, skill: Skill):
    found = [s for s in skill_scores(evidence) if s.skill is skill]
    assert len(found) == 1
    return found[0]


def test_linear_score_clamps():
    assert [linear_score(v, zero_at=5000, full_at=1000) for v in (500, 3000, 6000)] == [
        100,
        50,
        0,
    ]


def test_linear_score_runs_downward_when_full_is_below_zero():
    assert linear_score(6, zero_at=12, full_at=0) == pytest.approx(50)


def test_sounds_score_averages_accuracy_and_hit_share():
    evidence = _evidence(
        scripted_pronunciation=(_pa(80),),
        sound_observations=(
            mk("sound.sub.v.w", MISS, T0),
            mk("sound.sub.v.w", OK, T0),
            mk("sound.sub.v.w", OK, T0),
            mk("sound.sub.v.w", OK, T0),
        ),
    )
    s = _score(evidence, Skill.SOUNDS)
    assert s.values == {"accuracy": 80, "tracked_hit_share": 0.75}
    assert s.scores == {"accuracy": 80, "tracked_hit_share": 75}
    assert s.score == pytest.approx((80 + 75) / 2)


def test_hit_share_weights_misses_by_context():
    # A scripted miss weighs 1.0 and an unscripted hit weighs 0.5, so the hit share is 1 - 1/1.5.
    evidence = _evidence(
        sound_observations=(
            mk("sound.sub.v.w", MISS, T0, context=Context.SCRIPTED),
            mk("sound.sub.v.w", OK, T0, context=Context.UNSCRIPTED),
        ),
    )
    assert _score(evidence, Skill.SOUNDS).values["tracked_hit_share"] == pytest.approx(
        1 - 1.0 / 1.5
    )


def test_accuracy_ignores_unscored_words():
    evidence = _evidence(scripted_pronunciation=(_pa(60, None, 100),))
    assert _score(evidence, Skill.SOUNDS).values == {"accuracy": 80}


def test_on_the_spot_components():
    # Free talk: 1000..2700 ms with one filler, then a short answer 500..1400 ms. Speech time is
    # 2600 ms in all, with 8 non-filler words and 1 filler.
    free = transcript(
        ("so", 1000, 1300),
        ("um", 1400, 1700),
        ("i", 1800, 1900),
        ("like", 1950, 2200),
        ("tea", 2200, 2400),
        ("daily", 2400, 2700),
    )
    short = transcript(("yes", 500, 800), ("sure", 900, 1200), ("ok", 1200, 1400))
    quick = transcript(("one", 2000, 2300))
    s = _score(
        _evidence(quick_answers=(quick,), unscripted=(free, short), grammar_misses=2),
        Skill.ON_THE_SPOT,
    )
    minutes = 2.6 / 60
    assert s.values["median_first_word_ms"] == 2000
    assert s.values["fillers_per_min"] == pytest.approx(1 / minutes)
    assert s.values["words_per_min"] == pytest.approx(8 / minutes)
    # Runs: "so" | "i like tea daily" | "yes sure ok", so 1, 4 and 3 words.
    assert s.values["mean_length_of_run"] == pytest.approx(8 / 3)
    # Grammar: 2 misses over the 9 words of the unscripted transcripts.
    assert s.values["grammar_errors_per_100_words"] == pytest.approx(2 / 9 * 100)
    assert s.scores["median_first_word_ms"] == pytest.approx(75)
    assert s.scores["fillers_per_min"] == pytest.approx(
        linear_score(1 / minutes, zero_at=12, full_at=0)
    )
    assert s.score == pytest.approx(sum(s.scores.values()) / len(s.scores))


def test_fillers_lower_the_fillers_score():
    clean = transcript(("a", 0, 500), ("b", 600, 900))
    filled = transcript(("um", 0, 500), ("uh", 600, 900))
    clean_s = _score(_evidence(unscripted=(clean,)), Skill.ON_THE_SPOT)
    filled_s = _score(_evidence(unscripted=(filled,)), Skill.ON_THE_SPOT)
    assert clean_s.values["fillers_per_min"] == 0
    assert filled_s.scores["fillers_per_min"] < clean_s.scores["fillers_per_min"]


def test_run_splits_at_a_gap_of_250_ms():
    gap = transcript(("a", 0, 100), ("b", 400, 500))
    s = _score(_evidence(unscripted=(gap,)), Skill.ON_THE_SPOT)
    assert s.values["mean_length_of_run"] == pytest.approx(1.0)


def test_articulate_from_rubric():
    s = _score(
        _evidence(articulate_rubric=Rubric(structure=3, clarity=2, concision=4)),
        Skill.ARTICULATE,
    )
    assert s.values == {"rubric": 3}
    assert s.score == pytest.approx(75.0)


def test_skill_without_evidence_is_omitted():
    evidence = _evidence(articulate_rubric=Rubric(structure=4, clarity=4, concision=4))
    assert [s.skill for s in skill_scores(evidence)] == [Skill.ARTICULATE]


def test_scores_come_in_skill_order():
    evidence = _evidence(
        scripted_pronunciation=(_pa(90),),
        unscripted=(transcript(("a", 0, 500)),),
        articulate_rubric=Rubric(structure=1, clarity=1, concision=1),
    )
    assert [s.skill for s in skill_scores(evidence)] == [
        Skill.SOUNDS,
        Skill.ON_THE_SPOT,
        Skill.ARTICULATE,
    ]
