"""The feedback routes through the real app: POST makes the cards, GET only reads them."""

import json
from collections.abc import Callable
from typing import cast

import pytest
from factories import NOW, count, mk
from fastapi import FastAPI
from harness import Harness
from provider_fakes import FakeCoach
from security.planted import PLANTED_ANTHROPIC_KEY
from sqlalchemy import Engine, text

from nosolear.domain.coach import CoachExplanation
from nosolear.domain.errors import CapExceeded, ProviderUnavailable
from nosolear.domain.observations import Outcome
from nosolear.domain.speech import RawResult
from nosolear.domain.taxonomy import Detector
from nosolear.persistence.repositories import ObservationRepository

SOUND = "sound.sub.v.w"
FILLER = "fluency.filler"
CLARITY = "clarity.vague"


def _raw() -> RawResult:
    return RawResult(
        provider="anthropic",
        provider_version="oracle",
        adapter="claude_coach",
        adapter_version=1,
        payload={},
    )


def expl(message: str, model_text: str = "rewrite") -> CoachExplanation:
    return CoachExplanation(message=message, model_text=model_text, tokens_used=1, raw=_raw())


class CappedCoach(FakeCoach):
    def explain(self, *, error_key: str, quote: str, context: str) -> CoachExplanation:
        self.explain_calls.append((error_key, quote, context))
        raise CapExceeded()


class LeakingCoach(FakeCoach):
    def explain(self, *, error_key: str, quote: str, context: str) -> CoachExplanation:
        self.explain_calls.append((error_key, quote, context))
        raise ProviderUnavailable(f"the provider rejected {PLANTED_ANTHROPIC_KEY}")


def seed(
    harness: Harness,
    *,
    kind: str = "daily",
    job_status: str | None = None,
) -> str:
    """A session of `kind` with one attempt, three misses (one per skill) and an optional job."""
    attempt_id = harness.attempt(
        step="speak", scripted=False, reference_text=None, session_kind=kind
    )
    with harness.engine.connect() as conn:
        session_id = conn.execute(
            text("SELECT session_id FROM attempts WHERE id = :id"), {"id": attempt_id}
        ).scalar_one()
    ObservationRepository(harness.engine).add_many(
        [
            mk(
                SOUND,
                Outcome.MISS,
                NOW,
                detector=Detector.AZURE_PA,
                attempt_id=attempt_id,
                evidence={"word": "very", "start_ms": 100, "end_ms": 300},
            ),
            mk(
                FILLER,
                Outcome.MISS,
                NOW,
                detector=Detector.ASR_METRICS,
                attempt_id=attempt_id,
                evidence={"text": "um I think", "start_ms": 400, "end_ms": 900},
            ),
            mk(
                CLARITY,
                Outcome.MISS,
                NOW,
                detector=Detector.COACH,
                attempt_id=attempt_id,
                evidence={"quote": "a lot of things"},
            ),
        ]
    )
    if job_status is not None:
        _job(harness.engine, attempt_id, job_status)
    return str(session_id)


def _job(engine: Engine, attempt_id: str, status: str) -> None:
    stamp = "2026-11-13T09:00:00.000000+00:00"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO jobs (id, kind, attempt_id, status, progress, steps_json, tries, "
                "created_at, updated_at) VALUES (:id, 'analyze', :attempt, :status, 0.0, '[]', 0, "
                ":stamp, :stamp)"
            ),
            {"id": f"job-{attempt_id}", "attempt": attempt_id, "status": status, "stamp": stamp},
        )


def _coach_three() -> FakeCoach:
    return FakeCoach(
        explain_results=[
            expl("Put your teeth on your lip."),
            expl("Pause, breathe, then go on."),
            expl("Say the point in fewer words."),
        ]
    )


def test_post_returns_three_skill_cards_with_fixes(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness(coach=_coach_three())
    session_id = seed(harness)
    response = harness.client.post(f"/api/sessions/{session_id}/feedback")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded"] is False
    assert [s["skill"] for s in body["skills"]] == ["sounds", "on_the_spot", "articulate"]
    assert [s["state"] for s in body["skills"]] == ["fix", "fix", "fix"]
    sounds = body["skills"][0]["item"]
    assert sounds["source"] == "coach"
    assert sounds["error_key"] == SOUND
    assert sounds["word"] == "very"
    assert sounds["start_ms"] == 100
    assert sounds["message"] == "Put your teeth on your lip."
    assert sounds["fallback_reason"] is None


def test_post_before_job_finished_is_409_session_not_analyzed_and_coach_untouched(
    make_harness: Callable[..., Harness],
) -> None:
    coach = _coach_three()
    harness = make_harness(coach=coach)
    session_id = seed(harness, job_status="queued")
    response = harness.client.post(f"/api/sessions/{session_id}/feedback")
    assert response.status_code == 409
    assert response.json()["code"] == "session_not_analyzed"
    assert coach.explain_calls == []


def test_get_before_generate_is_404_and_has_no_side_effects(
    make_harness: Callable[..., Harness],
) -> None:
    coach = _coach_three()
    harness = make_harness(coach=coach)
    session_id = seed(harness)
    response = harness.client.get(f"/api/sessions/{session_id}/feedback")
    assert response.status_code == 404
    assert response.json()["code"] == "feedback_not_generated"

    assert harness.client.post(f"/api/sessions/{session_id}/feedback").status_code == 200
    calls, rows = len(coach.explain_calls), count(harness.engine, "feedback_items")
    for _ in range(2):
        assert harness.client.get(f"/api/sessions/{session_id}/feedback").status_code == 200
    assert len(coach.explain_calls) == calls
    assert count(harness.engine, "feedback_items") == rows


def test_unknown_session_is_404(make_harness: Callable[..., Harness]) -> None:
    harness = make_harness(coach=_coach_three())
    response = harness.client.post("/api/sessions/no-such-session/feedback")
    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_baseline_session_is_409_not_daily(make_harness: Callable[..., Harness]) -> None:
    coach = _coach_three()
    harness = make_harness(coach=coach)
    session_id = seed(harness, kind="baseline")
    response = harness.client.post(f"/api/sessions/{session_id}/feedback")
    assert response.status_code == 409
    assert response.json()["code"] == "session_not_daily"
    assert coach.explain_calls == []


def test_capped_coach_returns_200_degraded_with_reason(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness(coach=CappedCoach())
    session_id = seed(harness)
    response = harness.client.post(f"/api/sessions/{session_id}/feedback")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["degraded"] is True
    for skill in body["skills"]:
        assert skill["item"]["source"] == "template"
        assert skill["item"]["fallback_reason"] == "cap_exceeded"


def test_post_twice_is_idempotent(make_harness: Callable[..., Harness]) -> None:
    coach = _coach_three()
    harness = make_harness(coach=coach)
    session_id = seed(harness)
    first = harness.client.post(f"/api/sessions/{session_id}/feedback").json()
    second = harness.client.post(f"/api/sessions/{session_id}/feedback")
    assert second.status_code == 200
    assert second.json() == first
    assert len(coach.explain_calls) == 3


def test_response_and_openapi_contain_no_planted_key(
    make_harness: Callable[..., Harness], caplog: pytest.LogCaptureFixture
) -> None:
    harness = make_harness(coach=LeakingCoach())
    session_id = seed(harness)
    response = harness.client.post(f"/api/sessions/{session_id}/feedback")
    get_response = harness.client.get(f"/api/sessions/{session_id}/feedback")
    app = cast(FastAPI, harness.client.app)
    openapi = json.dumps(app.openapi())
    for text_seen in (response.text, get_response.text, caplog.text, openapi):
        assert PLANTED_ANTHROPIC_KEY not in text_seen


def test_hostile_coach_text_is_returned_as_plain_text_without_control_chars(
    make_harness: Callable[..., Harness],
) -> None:
    coach = FakeCoach(
        explain_results=[
            expl("fix‮ it\x00 now"),
            expl("Pause."),
            expl("Shorter."),
        ]
    )
    harness = make_harness(coach=coach)
    session_id = seed(harness)
    body = harness.client.post(f"/api/sessions/{session_id}/feedback").json()
    message = body["skills"][0]["item"]["message"]
    assert message == "fix it now"
    assert "\x00" not in message
    assert "‮" not in message
