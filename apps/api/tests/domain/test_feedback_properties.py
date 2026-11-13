import unicodedata
from datetime import timedelta

from factories import NOW, mk, profile_of
from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.coach import MAX_EXPLANATION_CHARS, MAX_MODEL_TEXT_CHARS, CoachExplanation
from nosolear.domain.feedback import SkillState, choose_fixes, sanitize_explanation
from nosolear.domain.observations import Outcome
from nosolear.domain.speech import RawResult
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY, Detector
from nosolear.ports.feedback import StoredObservation

# Prosody keys have no detector yet, so no observation can carry them; only detected keys are drawn.
KEYS = [d.key for d in DEFAULT_TAXONOMY.defined() if d.detectors] + ["sound.sub.θ.s", "sound.low.ɝ"]
ARTICLE = "grammar.article"


def _detector(key: str) -> Detector:
    detectors = DEFAULT_TAXONOMY.get(key).detectors
    return Detector.AZURE_PA if Detector.AZURE_PA in detectors else sorted(detectors)[0]


@st.composite
def sessions(draw: st.DrawFn) -> list[StoredObservation]:
    rows = draw(
        st.lists(
            st.tuples(
                st.sampled_from(KEYS),
                st.sampled_from([Outcome.MISS, Outcome.OK]),
                st.integers(min_value=0, max_value=600),
            ),
            max_size=30,
        )
    )
    return [
        StoredObservation(
            id=index + 1,
            observation=mk(
                key,
                outcome,
                NOW + timedelta(minutes=minute),
                detector=_detector(key),
                attempt_id="a1",
            ),
        )
        for index, (key, outcome, minute) in enumerate(rows)
    ]


@given(sessions())
def test_at_most_one_fix_per_skill_and_it_is_a_session_miss(
    observations: list[StoredObservation],
) -> None:
    outcomes = choose_fixes(
        session_observations=observations, profile=profile_of([]), taxonomy=DEFAULT_TAXONOMY
    )
    assert len(outcomes) == 3
    for outcome in outcomes:
        if outcome.state is not SkillState.FIX:
            assert outcome.fix is None
            continue
        assert outcome.fix is not None
        misses = {
            s.id
            for s in observations
            if s.observation.error_key == outcome.fix.error_key
            and s.observation.outcome is Outcome.MISS
        }
        assert outcome.fix.observation_id in misses


@given(sessions())
def test_fix_key_belongs_to_its_skill(observations: list[StoredObservation]) -> None:
    for outcome in choose_fixes(
        session_observations=observations, profile=profile_of([]), taxonomy=DEFAULT_TAXONOMY
    ):
        if outcome.fix is not None:
            assert DEFAULT_TAXONOMY.get(outcome.fix.error_key).skill is outcome.skill


@given(sessions(), st.data())
def test_choose_fixes_is_order_independent(
    observations: list[StoredObservation], data: st.DataObject
) -> None:
    shuffled = data.draw(st.permutations(observations))
    assert choose_fixes(
        session_observations=observations, profile=profile_of([]), taxonomy=DEFAULT_TAXONOMY
    ) == choose_fixes(
        session_observations=shuffled, profile=profile_of([]), taxonomy=DEFAULT_TAXONOMY
    )


@given(st.text(max_size=2_000), st.text(max_size=2_000))
def test_sanitized_text_has_no_control_chars_and_respects_caps(message: str, rewrite: str) -> None:
    grammar = StoredObservation(
        id=1,
        observation=mk(ARTICLE, Outcome.MISS, NOW, detector=Detector.COACH, attempt_id="a1"),
    )
    outcomes = choose_fixes(
        session_observations=[grammar], profile=profile_of([]), taxonomy=DEFAULT_TAXONOMY
    )
    fix = next(o.fix for o in outcomes if o.fix is not None)
    raw = CoachExplanation(
        message=message,
        model_text=rewrite,
        tokens_used=0,
        raw=RawResult(
            provider="anthropic",
            provider_version="1",
            adapter="claude",
            adapter_version=1,
            payload={},
        ),
    )
    result = sanitize_explanation(raw, fix=fix, taxonomy=DEFAULT_TAXONOMY)
    if result is None:
        return
    assert 0 < len(result.message) <= MAX_EXPLANATION_CHARS
    texts = [result.message] + ([result.model_text] if result.model_text is not None else [])
    for text in texts:
        assert all(unicodedata.category(ch) not in ("Cc", "Cf") for ch in text)
    if result.model_text is not None:
        assert len(result.model_text) <= MAX_MODEL_TEXT_CHARS
