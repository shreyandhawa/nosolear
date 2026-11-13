from datetime import timedelta

import pytest
from factories import NOW, entry, mk, profile_of

from nosolear.domain.coach import (
    MAX_EXPLANATION_CHARS,
    MAX_MODEL_TEXT_CHARS,
    CoachExplanation,
)
from nosolear.domain.feedback import (
    FixChoice,
    SkillState,
    choose_fixes,
    sanitize_explanation,
    template_explanation,
)
from nosolear.domain.observations import Context, Outcome
from nosolear.domain.speech import RawResult
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY, Detector, Skill
from nosolear.ports.feedback import StoredObservation

SUB = "sound.sub.v.w"  # SOUNDS, impact 3
FILLER = "fluency.filler"  # ON_THE_SPOT, impact 2
ARTICLE = "grammar.article"  # ON_THE_SPOT, COACH


def stored(
    id_: int,
    key: str,
    outcome: Outcome = Outcome.MISS,
    *,
    at=NOW,
    weight_context: Context = Context.SCRIPTED,
    evidence=None,
) -> StoredObservation:
    detector = DEFAULT_TAXONOMY.get(key).detectors
    chosen = Detector.AZURE_PA if Detector.AZURE_PA in detector else sorted(detector)[0]
    return StoredObservation(
        id=id_,
        observation=mk(
            key,
            outcome,
            at,
            context=weight_context,
            detector=chosen,
            evidence=evidence,
            attempt_id="a1",
        ),
    )


def raw() -> RawResult:
    return RawResult(
        provider="anthropic",
        provider_version="1",
        adapter="claude",
        adapter_version=1,
        payload={},
    )


def explanation(message: str, model_text: str = "fixed") -> CoachExplanation:
    return CoachExplanation(message=message, model_text=model_text, tokens_used=1, raw=raw())


def fix_for(key: str, *, word: str | None = None, quote: str | None = None) -> FixChoice:
    return FixChoice(
        skill=DEFAULT_TAXONOMY.get(key).skill,
        error_key=key,
        observation_id=1,
        attempt_id="a1",
        word=word,
        quote=quote,
        context=None,
        start_ms=None,
        end_ms=None,
        priority=1.0,
    )


def test_picks_highest_priority_missed_key_per_skill() -> None:
    profile = profile_of(
        [
            entry("sound.sub.v.w", a=2, b=8, status=Status.ACTIVE),  # p=0.2 * 3 = 0.6
            entry("sound.sub.f.p", a=6, b=4, status=Status.ACTIVE),  # p=0.6 * 3 = 1.8
        ]
    )
    observations = [
        stored(1, "sound.sub.v.w"),
        stored(2, "sound.sub.f.p"),
    ]
    outcomes = choose_fixes(
        session_observations=observations, profile=profile, taxonomy=DEFAULT_TAXONOMY
    )
    sounds = outcomes[0]
    assert sounds.state is SkillState.FIX
    assert sounds.fix is not None
    assert sounds.fix.error_key == "sound.sub.f.p"


def test_evidence_is_highest_weight_miss_of_that_key() -> None:
    unscripted = stored(1, SUB, weight_context=Context.UNSCRIPTED)  # weight 0.5
    scripted = stored(2, SUB, weight_context=Context.SCRIPTED)  # weight 1.0
    outcomes = choose_fixes(
        session_observations=[unscripted, scripted],
        profile=profile_of([]),
        taxonomy=DEFAULT_TAXONOMY,
    )
    fix = outcomes[0].fix
    assert fix is not None
    assert fix.observation_id == 2


def test_evidence_ties_break_by_earliest_then_lowest_id() -> None:
    later = stored(1, SUB, at=NOW + timedelta(minutes=5))
    earlier = stored(9, SUB, at=NOW)
    tied_early_low_id = stored(3, SUB, at=NOW)
    outcomes = choose_fixes(
        session_observations=[later, earlier, tied_early_low_id],
        profile=profile_of([]),
        taxonomy=DEFAULT_TAXONOMY,
    )
    fix = outcomes[0].fix
    assert fix is not None
    assert fix.observation_id == 3


def test_clean_and_not_scored_are_distinct() -> None:
    clean = choose_fixes(
        session_observations=[stored(1, SUB, Outcome.OK)],
        profile=profile_of([]),
        taxonomy=DEFAULT_TAXONOMY,
    )
    not_scored = choose_fixes(
        session_observations=[stored(1, FILLER)],
        profile=profile_of([]),
        taxonomy=DEFAULT_TAXONOMY,
    )
    assert clean[0].state is SkillState.CLEAN
    assert clean[0].fix is None
    assert not_scored[0].state is SkillState.NOT_SCORED
    assert not_scored[0].fix is None
    assert clean[0] != not_scored[0]


def test_outcomes_always_three_in_skill_order() -> None:
    outcomes = choose_fixes(
        session_observations=[], profile=profile_of([]), taxonomy=DEFAULT_TAXONOMY
    )
    assert [o.skill for o in outcomes] == [Skill.SOUNDS, Skill.ON_THE_SPOT, Skill.ARTICULATE]
    assert all(o.state is SkillState.NOT_SCORED for o in outcomes)


def test_ties_break_by_key() -> None:
    observations = [stored(1, "sound.sub.v.w"), stored(2, "sound.sub.f.p")]
    outcomes = choose_fixes(
        session_observations=observations, profile=profile_of([]), taxonomy=DEFAULT_TAXONOMY
    )
    # Both keys have impact 3 and no profile entry, so the priority ties and the smaller key wins.
    fix = outcomes[0].fix
    assert fix is not None
    assert fix.error_key == "sound.sub.f.p"


def test_sanitize_accepts_matching_explanation_and_strips_controls() -> None:
    result = sanitize_explanation(
        explanation("fix‮ it\x00"), fix=fix_for(SUB), taxonomy=DEFAULT_TAXONOMY
    )
    assert result is not None
    assert result.message == "fix it"
    assert result.error_key == SUB


@pytest.mark.parametrize(
    "message",
    ["x" * 50_000, "", "\x00\x01‮​"],
    ids=["too_long", "empty", "only_controls"],
)
def test_hostile_explanations_are_rejected(message: str) -> None:
    assert (
        sanitize_explanation(explanation(message), fix=fix_for(SUB), taxonomy=DEFAULT_TAXONOMY)
        is None
    )


def test_hostile_explanations_reject_none() -> None:
    assert sanitize_explanation(None, fix=fix_for(SUB), taxonomy=DEFAULT_TAXONOMY) is None


def test_sound_model_text_comes_from_domain_not_coach() -> None:
    result = sanitize_explanation(
        explanation("Say it with the v sound.", model_text="rm -rf /"),
        fix=fix_for(SUB, word="very"),
        taxonomy=DEFAULT_TAXONOMY,
    )
    assert result is not None
    assert result.model_text == "very"


def test_coach_rewrite_kept_for_grammar_and_capped() -> None:
    long_rewrite = "word " * 200
    result = sanitize_explanation(
        explanation("Use an article.", model_text=long_rewrite),
        fix=fix_for(ARTICLE),
        taxonomy=DEFAULT_TAXONOMY,
    )
    assert result is not None
    assert result.model_text is not None
    assert len(result.model_text) <= MAX_MODEL_TEXT_CHARS
    assert result.model_text.startswith("word word")


def test_fluency_has_no_model_text() -> None:
    result = sanitize_explanation(
        explanation("Pause once, then finish the thought.", model_text="anything"),
        fix=fix_for(FILLER),
        taxonomy=DEFAULT_TAXONOMY,
    )
    assert result is not None
    assert result.model_text is None


def test_template_exists_for_every_defined_key() -> None:
    keys = [d.key for d in DEFAULT_TAXONOMY.defined()] + ["sound.sub.θ.s", "sound.low.ɝ"]
    for key in keys:
        result = template_explanation(fix_for(key, word="word", quote="a quote"), DEFAULT_TAXONOMY)
        assert result.error_key == key
        assert result.message
        assert len(result.message) <= MAX_EXPLANATION_CHARS
        assert DEFAULT_TAXONOMY.get(key).description in result.message


def test_template_mentions_word_when_present() -> None:
    result = template_explanation(fix_for(SUB, word="very"), DEFAULT_TAXONOMY)
    assert "very" in result.message
    assert result.model_text == "very"
