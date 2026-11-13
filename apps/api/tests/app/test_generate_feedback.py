"""generate_feedback: one card per skill, the coach asked once per fix, templates on failure."""

from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from factories import NOW, mk
from fakes import (
    FakeFeedbackStore,
    FakeProfileReader,
    FakeSessionJobStatus,
    FakeSessionObservations,
    FakeSessionReader,
)
from provider_fakes import FakeCoach

from nosolear.app.generate_feedback import generate_feedback
from nosolear.domain.coach import CoachExplanation
from nosolear.domain.errors import (
    CapabilityMissing,
    CapExceeded,
    MalformedProviderResponse,
    ProviderUnavailable,
)
from nosolear.domain.feedback import (
    SessionNotAnalyzed,
    SessionNotDaily,
    SessionNotFound,
    SkillState,
)
from nosolear.domain.observations import Outcome
from nosolear.domain.speech import RawResult
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY, Detector, Skill
from nosolear.ports.feedback import FeedbackReport, StoredObservation

SESSION = "s1"
SOUND = "sound.sub.v.w"
FILLER = "fluency.filler"
CLARITY = "clarity.vague"
PLANTED = "sk-ant-api03-PLANTEDKEYVALUE"


def _raw() -> RawResult:
    return RawResult(
        provider="anthropic",
        provider_version="1",
        adapter="claude",
        adapter_version=1,
        payload={},
    )


def reply(message: str, model_text: str = "rewritten") -> CoachExplanation:
    return CoachExplanation(message=message, model_text=model_text, tokens_used=1, raw=_raw())


class ScriptedCoach(FakeCoach):
    """`explain` answers each call from one queue: a reply is returned, an exception is raised.
    A call with nothing queued fails the test, so an unexpected paid call cannot pass silently."""

    def __init__(self, outcomes: Sequence[CoachExplanation | Exception]) -> None:
        super().__init__()
        self.outcomes: list[CoachExplanation | Exception] = list(outcomes)

    def explain(self, *, error_key: str, quote: str, context: str) -> CoachExplanation:
        self.explain_calls.append((error_key, quote, context))
        if not self.outcomes:
            raise RuntimeError("the coach was called with nothing scripted")
        result = self.outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _stored(
    id_: int,
    key: str,
    evidence: dict[str, object],
    *,
    outcome: Outcome = Outcome.MISS,
    detector: Detector | None = None,
) -> StoredObservation:
    chosen = detector or sorted(DEFAULT_TAXONOMY.get(key).detectors)[0]
    return StoredObservation(
        id=id_,
        observation=mk(
            key,
            outcome,
            NOW,
            detector=chosen,
            evidence=evidence,
            attempt_id="a1",
        ),
    )


def session_observations() -> list[StoredObservation]:
    return [
        _stored(
            1, SOUND, {"word": "very", "start_ms": 100, "end_ms": 300}, detector=Detector.AZURE_PA
        ),
        _stored(
            2,
            FILLER,
            {"text": "um so I think", "start_ms": 400, "end_ms": 900},
            detector=Detector.ASR_METRICS,
        ),
        _stored(3, CLARITY, {"quote": "a lot of things"}, detector=Detector.COACH),
    ]


@dataclass
class World:
    sessions: FakeSessionReader
    jobs: FakeSessionJobStatus
    observations: FakeSessionObservations
    feedback: FakeFeedbackStore
    coach: ScriptedCoach


def world(
    outcomes: Sequence[CoachExplanation | Exception],
    *,
    observations: Sequence[StoredObservation] | None = None,
    unfinished: int = 0,
    kind: str = "daily",
) -> World:
    return World(
        sessions=FakeSessionReader({SESSION: kind, "base": "baseline"}),
        jobs=FakeSessionJobStatus({SESSION: unfinished}),
        observations=FakeSessionObservations(
            {SESSION: list(session_observations() if observations is None else observations)}
        ),
        feedback=FakeFeedbackStore(),
        coach=ScriptedCoach(outcomes),
    )


def call(w: World, session_id: str = SESSION) -> FeedbackReport:
    return generate_feedback(
        session_id=session_id,
        sessions=w.sessions,
        jobs=w.jobs,
        observations=w.observations,
        profiles=FakeProfileReader(None),
        feedback=w.feedback,
        coach=w.coach,
        taxonomy=DEFAULT_TAXONOMY,
    )


def test_one_item_per_skill_with_misses_and_coach_text() -> None:
    w = world(
        [
            reply("Put your teeth on your lip."),
            reply("Pause, breathe, go on."),
            reply("Say it shorter."),
        ]
    )
    report = call(w)
    assert report.degraded is False
    assert [s.skill for s in report.skills] == [Skill.SOUNDS, Skill.ON_THE_SPOT, Skill.ARTICULATE]
    assert [s.state for s in report.skills] == [SkillState.FIX] * 3
    messages = [s.item.message for s in report.skills if s.item is not None]
    assert messages == ["Put your teeth on your lip.", "Pause, breathe, go on.", "Say it shorter."]
    assert all(s.item is not None and s.item.source == "coach" for s in report.skills)
    assert report.skills[0].item is not None
    assert report.skills[0].item.word == "very"
    assert report.skills[0].item.start_ms == 100


def test_unfinished_job_refuses_without_calling_coach() -> None:
    w = world([reply("unused")], unfinished=1)
    with pytest.raises(SessionNotAnalyzed):
        call(w)
    assert w.coach.explain_calls == []
    assert w.feedback.for_session(SESSION) == []


@pytest.mark.parametrize(
    ("session_id", "error"),
    [("missing", SessionNotFound), ("base", SessionNotDaily)],
    ids=["unknown", "baseline"],
)
def test_unknown_and_non_daily_sessions_raise_typed_errors(
    session_id: str, error: type[Exception]
) -> None:
    w = world([reply("unused")])
    with pytest.raises(error):
        call(w, session_id=session_id)
    assert w.coach.explain_calls == []


def test_at_most_one_coach_call_per_fix() -> None:
    w = world([reply("a"), reply("b"), reply("c")])
    call(w)
    assert [key for key, _, _ in w.coach.explain_calls] == [SOUND, FILLER, CLARITY]


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (CapExceeded(), "cap_exceeded"),
        (ProviderUnavailable(), "provider_unavailable"),
        (CapabilityMissing(), "capability_missing"),
    ],
)
def test_capped_coach_stores_template_with_reason(error: Exception, reason: str) -> None:
    w = world([error])
    report = call(w)
    assert report.degraded is True
    assert len(w.coach.explain_calls) == 1
    for skill in report.skills:
        assert skill.item is not None
        assert skill.item.source == "template"
        assert skill.item.fallback_reason == reason


def test_malformed_reply_gives_only_that_fix_invalid_output() -> None:
    w = world([MalformedProviderResponse(), reply("Say it shorter."), reply("Pause.")])
    report = call(w)
    assert report.degraded is True
    assert len(w.coach.explain_calls) == 3
    sounds, on_the_spot, articulate = (s.item for s in report.skills)
    assert sounds is not None and sounds.source == "template"
    assert sounds.fallback_reason == "invalid_output"
    assert on_the_spot is not None and on_the_spot.source == "coach"
    assert articulate is not None and articulate.source == "coach"


def test_hostile_coach_output_falls_back_to_template_invalid_output() -> None:
    w = world([reply("x" * 50_000), reply("Pause."), reply("Shorter.")])
    report = call(w)
    sounds = report.skills[0].item
    assert sounds is not None
    assert sounds.source == "template"
    assert sounds.fallback_reason == "invalid_output"
    assert report.degraded is True


def test_unexpected_exception_propagates() -> None:
    w = world([RuntimeError("boom")])
    with pytest.raises(RuntimeError, match="boom"):
        call(w)


def test_second_request_does_not_call_coach_when_all_items_are_coach() -> None:
    w = world([reply("a"), reply("b"), reply("c")])
    first = call(w)
    second = call(w)
    assert len(w.coach.explain_calls) == 3
    assert second == first


def test_second_request_upgrades_template_items_only() -> None:
    w = world([reply("Put your teeth on your lip."), CapExceeded()])
    first = call(w)
    sounds_before = first.skills[0].item
    assert sounds_before is not None and sounds_before.source == "coach"
    assert first.skills[1].item is not None and first.skills[1].item.source == "template"

    w.coach.outcomes.extend([reply("Pause, breathe, go on."), reply("Say it shorter.")])
    second = call(w)

    assert [key for key, _, _ in w.coach.explain_calls] == [SOUND, FILLER, FILLER, CLARITY]
    assert second.skills[0].item == sounds_before
    assert second.skills[1].item is not None
    assert second.skills[1].item.source == "coach"
    assert second.skills[1].item.message == "Pause, breathe, go on."
    assert second.skills[2].item is not None
    assert second.skills[2].item.source == "coach"
    assert second.degraded is False


def test_clean_skill_has_no_item_and_no_coach_request() -> None:
    observations = [
        _stored(1, SOUND, {"word": "very"}, outcome=Outcome.OK, detector=Detector.AZURE_PA),
        _stored(2, FILLER, {"text": "um"}, detector=Detector.ASR_METRICS),
        _stored(3, CLARITY, {"quote": "a lot"}, detector=Detector.COACH),
    ]
    w = world([reply("Pause."), reply("Shorter.")], observations=observations)
    report = call(w)
    sounds = report.skills[0]
    assert sounds.state is SkillState.CLEAN
    assert sounds.item is None
    assert [key for key, _, _ in w.coach.explain_calls] == [FILLER, CLARITY]


def test_planted_key_never_appears_in_stored_text() -> None:
    leaked = ProviderUnavailable(f"the request failed with {PLANTED}")
    w = world([leaked])
    report = call(w)
    stored = repr(w.feedback.for_session(SESSION)) + repr(report)
    assert PLANTED not in stored
