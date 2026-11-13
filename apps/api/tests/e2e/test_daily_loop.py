"""The daily loop through the API: plan, session, recording, feedback, completion, and tomorrow's
plan, which must reflect today's misses. Every provider is an oracle or a fake, so no test makes a
paid call. The live coach is in tests/live and is never run here."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from adapters.anthropic_payloads import analysis_text, message_json
from factories import T0
from harness import Harness
from provider_fakes import FakeCoach
from sqlalchemy import text

from nosolear.domain.coach import (
    CoachAnalysis,
    CoachExplanation,
    CoachTask,
    coach_keys,
    parse_coach_analysis,
)
from nosolear.domain.errors import CapabilityMissing, CapExceeded
from nosolear.domain.speech import RawResult
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY

# The oracle replaces v with w, so "very" and "vests" are sound misses; "Um" is a filler.
SPOKEN = (
    "Um I went to the market and bought very nice vests and very cheap vests "
    "and very warm vests a lot of things"
)
SOUND = "sound.sub.v.w"
FILLER = "fluency.filler"
ARTICLE = "grammar.article"
CLARITY = "clarity.vague"
MISSED = {SOUND, FILLER, ARTICLE, CLARITY}
SKILLS = ["sounds", "on_the_spot", "articulate"]


class MovableClock:
    """A clock the test can move forward, to cross a local midnight."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now = self._now + delta


def _explain(message: str) -> CoachExplanation:
    raw = RawResult(
        provider="anthropic",
        provider_version="oracle",
        adapter="claude_coach",
        adapter_version=1,
        payload={},
    )
    return CoachExplanation(message=message, model_text="rewrite", tokens_used=1, raw=raw)


def _analysis() -> CoachAnalysis:
    """The coach's reading of one speak, as its real reply would parse: a grammar finding and a
    clarity finding, both quoted from the speech."""
    text = analysis_text(
        [
            {
                "error_key": ARTICLE,
                "quote": "to the market",
                "correction": "to the market",
                "explanation": "Use the article the before the noun.",
            },
            {
                "error_key": CLARITY,
                "quote": "a lot of things",
                "correction": "many things",
                "explanation": "Say the point more exactly.",
            },
        ]
    )
    raw = RawResult(
        provider="anthropic",
        provider_version="oracle",
        adapter="claude_coach",
        adapter_version=1,
        payload=message_json(text),
    )
    return parse_coach_analysis(
        raw, transcript=SPOKEN, allowed_keys=coach_keys(DEFAULT_TAXONOMY, CoachTask.FREE_TALK)
    )


def _coach() -> FakeCoach:
    return FakeCoach(
        results=[_analysis()],
        explain_results=[
            _explain("Use an article."),
            _explain("Say it shorter."),
            _explain("Pause."),
        ],
    )


class CappedExplainCoach(FakeCoach):
    """Analyses normally, but every explanation hits the usage cap."""

    def explain(self, *, error_key: str, quote: str, context: str) -> CoachExplanation:
        self.explain_calls.append((error_key, quote, context))
        raise CapExceeded()


def _speaker(h: Harness) -> None:
    """The speaker says v as w, so every "very" and "vests" is a sound miss."""
    h.voice.user_errors["v"] = "w"


def _start_session(h: Harness) -> tuple[str, str]:
    body: dict[str, Any] = h.client.post("/api/plan/today/session").json()
    return str(body["session_id"]), str(body["attempts"][0]["id"])


def _focus_keys(plan: dict[str, Any]) -> dict[str, str]:
    return {focus["skill"]: focus["error_key"] for focus in plan["foci"]}


def _missed_keys(h: Harness) -> set[str]:
    return {o.error_key for o in h.observations() if o.outcome.value == "miss"}


def _snapshot_reasons(h: Harness, session_id: str) -> list[str]:
    with h.engine.connect() as conn:
        rows = conn.execute(
            text("SELECT reason FROM profile_snapshots WHERE session_id = :id"), {"id": session_id}
        ).all()
    return [str(row.reason) for row in rows]


def _sources(plan: dict[str, Any]) -> dict[str, str]:
    return {focus["skill"]: focus["source"] for focus in plan["foci"]}


def test_full_daily_loop_through_api(make_harness: Callable[..., Harness]) -> None:
    # Control: the same calendar day with no session at all. Its foci are the prior's fallback,
    # so any difference from the real loop's plan is caused by today's misses.
    control = make_harness(clock=MovableClock(T0 + timedelta(days=1)))
    control_plan = control.client.post("/api/plan/today").json()

    clock = MovableClock(T0)
    h = make_harness(clock=clock, coach=_coach())
    _speaker(h)

    plan = h.client.post("/api/plan/today")
    assert plan.status_code == 201, plan.text
    assert set(_focus_keys(plan.json())) == set(SKILLS)

    session_id, attempt_id = _start_session(h)
    h.upload(attempt_id, SPOKEN)
    assert h.drain() >= 1
    assert _missed_keys(h) == MISSED

    feedback = h.client.post(f"/api/sessions/{session_id}/feedback")
    assert feedback.status_code == 200, feedback.text
    body = feedback.json()
    assert body["degraded"] is False
    assert [s["state"] for s in body["skills"]] == ["fix", "fix", "fix"]
    assert {s["item"]["error_key"] for s in body["skills"]} <= MISSED

    assert h.client.post(f"/api/sessions/{session_id}/complete").status_code == 200
    assert "daily" in _snapshot_reasons(h, session_id)

    clock.advance(timedelta(days=1))
    tomorrow = h.client.post("/api/plan/today")
    assert tomorrow.status_code == 201, tomorrow.text
    foci = _focus_keys(tomorrow.json())
    # Every skill's focus now comes from the profile the session built; the control's all come
    # from the prior. Only sounds is a different key from the control, so it is the one that
    # shows the misses changing the choice: the control's prior picks another sound.
    assert _sources(control_plan) == {skill: "fallback" for skill in SKILLS}
    assert _sources(tomorrow.json()) == {skill: "profile" for skill in SKILLS}
    assert _focus_keys(control_plan)["sounds"] != SOUND
    assert foci["sounds"] == SOUND


def test_loop_with_capped_coach_still_gives_template_feedback_and_a_plan(
    make_harness: Callable[..., Harness],
) -> None:
    clock = MovableClock(T0)
    h = make_harness(clock=clock, coach=CappedExplainCoach(results=[_analysis()]))
    _speaker(h)
    h.client.post("/api/plan/today")
    session_id, attempt_id = _start_session(h)
    h.upload(attempt_id, SPOKEN)
    h.drain()

    feedback = h.client.post(f"/api/sessions/{session_id}/feedback").json()
    assert feedback["degraded"] is True
    assert all(s["item"]["fallback_reason"] == "cap_exceeded" for s in feedback["skills"])
    assert h.client.post(f"/api/sessions/{session_id}/complete").status_code == 200

    clock.advance(timedelta(days=1))
    assert h.client.post("/api/plan/today").status_code == 201


class NoScorer:
    """The pronunciation capability is missing, so the score step fails with its typed error."""

    layer = "raw"

    def score(self, wav: Any, *, reference_text: str | None) -> Any:
        raise CapabilityMissing()


def test_loop_without_pronunciation_scorer_marks_sounds_not_scored(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness(coach=_coach(), scorer=NoScorer())  # pyright: ignore[reportArgumentType]
    _speaker(h)
    h.client.post("/api/plan/today")
    session_id, attempt_id = _start_session(h)
    h.upload(attempt_id, SPOKEN)
    h.drain()

    feedback = h.client.post(f"/api/sessions/{session_id}/feedback")
    assert feedback.status_code == 200, feedback.text
    states = {s["skill"]: s["state"] for s in feedback.json()["skills"]}
    assert states == {"sounds": "not_scored", "on_the_spot": "fix", "articulate": "fix"}


def test_feedback_before_job_run_is_409(make_harness: Callable[..., Harness]) -> None:
    coach = _coach()
    h = make_harness(coach=coach)
    _speaker(h)
    h.client.post("/api/plan/today")
    session_id, attempt_id = _start_session(h)
    h.upload(attempt_id, SPOKEN)

    response = h.client.post(f"/api/sessions/{session_id}/feedback")
    assert response.status_code == 409
    assert response.json()["code"] == "session_not_analyzed"
    assert coach.explain_calls == []
