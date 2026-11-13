"""POST /api/sessions/{id}/complete: 200 once, the same answer on a repeat, 409 during analysis."""

from collections.abc import Callable

from factories import count
from harness import Harness
from sqlalchemy import text

from nosolear.persistence.models import format_utc


def _daily(h: Harness, *, kind: str = "daily", job_status: str | None = None) -> str:
    attempt_id = h.attempt(step="speak", scripted=False, reference_text=None, session_kind=kind)
    with h.engine.begin() as conn:
        session_id = conn.execute(
            text("SELECT session_id FROM attempts WHERE id = :id"), {"id": attempt_id}
        ).scalar_one()
        if job_status is not None:
            conn.execute(
                text(
                    "INSERT INTO jobs (id, kind, attempt_id, status, progress, steps_json, tries, "
                    "created_at, updated_at) VALUES (:id, 'analyze', :attempt, :status, 0.0, "
                    "'[]', 0, :stamp, :stamp)"
                ),
                {
                    "id": f"job-{attempt_id}",
                    "attempt": attempt_id,
                    "status": job_status,
                    "stamp": format_utc(h.clock.now()),
                },
            )
    return str(session_id)


def test_complete_is_200_and_a_repeat_returns_the_same_answer(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness()
    session_id = _daily(h)

    first = h.client.post(f"/api/sessions/{session_id}/complete")
    assert first.status_code == 200, first.text
    assert first.json()["already_completed"] is False

    snapshots = count(h.engine, "profile_snapshots")
    second = h.client.post(f"/api/sessions/{session_id}/complete")
    assert second.status_code == 200
    assert second.json()["already_completed"] is True
    assert second.json()["completed_at"] == first.json()["completed_at"]
    assert count(h.engine, "profile_snapshots") == snapshots


def test_complete_while_a_job_is_queued_is_409(make_harness: Callable[..., Harness]) -> None:
    h = make_harness()
    session_id = _daily(h, job_status="queued")
    response = h.client.post(f"/api/sessions/{session_id}/complete")
    assert response.status_code == 409
    assert response.json()["code"] == "session_not_analyzed"


def test_complete_unknown_and_baseline_sessions_are_refused(
    make_harness: Callable[..., Harness],
) -> None:
    h = make_harness()
    assert h.client.post("/api/sessions/nobody/complete").status_code == 404
    baseline = _daily(h, kind="baseline")
    response = h.client.post(f"/api/sessions/{baseline}/complete")
    assert response.status_code == 409
    assert response.json()["code"] == "session_not_daily"
