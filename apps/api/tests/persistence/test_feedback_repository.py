"""The feedback store and the session readers that generate_feedback relies on."""

from typing import Any

from factories import T0, mk
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from nosolear.domain.observations import Outcome
from nosolear.domain.taxonomy import Skill
from nosolear.persistence.feedback_repositories import (
    FeedbackRepository,
    SessionJobRepository,
    SessionRepository,
)
from nosolear.persistence.models import format_utc
from nosolear.persistence.repositories import ObservationRepository
from nosolear.ports.feedback import FallbackReason, FeedbackItem, FeedbackSource

STAMP = format_utc(T0)
SOUND = "sound.sub.v.w"


def _session(engine: Engine, session_id: str, kind: str = "daily") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sessions (id, kind, protocol_version, started_at) "
                "VALUES (:id, :kind, 1, :stamp)"
            ),
            {"id": session_id, "kind": kind, "stamp": STAMP},
        )


def _attempt(engine: Engine, attempt_id: str, session_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO attempts (id, session_id, step, scripted, created_at) "
                "VALUES (:id, :session, 'speak', 1, :stamp)"
            ),
            {"id": attempt_id, "session": session_id, "stamp": STAMP},
        )


def _job(engine: Engine, job_id: str, attempt_id: str, status: str, kind: str = "analyze") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO jobs (id, kind, attempt_id, status, progress, steps_json, tries, "
                "created_at, updated_at) VALUES (:id, :kind, :attempt, :status, 0.0, "
                "'[]', 0, :stamp, :stamp)"
            ),
            {
                "id": job_id,
                "kind": kind,
                "attempt": attempt_id,
                "status": status,
                "stamp": STAMP,
            },
        )


def _observation_id(engine: Engine, attempt_id: str, key: str = SOUND) -> int:
    ObservationRepository(engine).add_many(
        [
            mk(
                key,
                Outcome.MISS,
                T0,
                attempt_id=attempt_id,
                evidence={"word": "vest", "start_ms": 120, "end_ms": 300},
            )
        ]
    )
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT max(id) FROM observations")).scalar_one())


def _item(
    *,
    session_id: str,
    observation_id: int,
    message: str = "say the v",
    source: FeedbackSource = "coach",
    fallback_reason: FallbackReason | None = None,
    item_id: str = "item-1",
) -> FeedbackItem:
    return FeedbackItem(
        id=item_id,
        session_id=session_id,
        skill=Skill.SOUNDS,
        error_key=SOUND,
        observation_id=observation_id,
        attempt_id="a1",
        start_ms=120,
        end_ms=300,
        word="vest",
        message=message,
        model_text="vest",
        source=source,
        fallback_reason=fallback_reason,
    )


def test_feedback_roundtrip_keeps_source_and_reason(db_engine: Engine) -> None:
    _session(db_engine, "s1")
    _attempt(db_engine, "a1", "s1")
    obs = _observation_id(db_engine, "a1")
    store = FeedbackRepository(db_engine)
    stored = _item(
        session_id="s1", observation_id=obs, source="template", fallback_reason="cap_exceeded"
    )
    store.upsert("s1", [stored])
    assert store.for_session("s1") == [stored]


def test_feedback_upsert_replaces_by_session_and_skill(db_engine: Engine) -> None:
    _session(db_engine, "s1")
    _attempt(db_engine, "a1", "s1")
    obs = _observation_id(db_engine, "a1")
    store = FeedbackRepository(db_engine)
    store.upsert("s1", [_item(session_id="s1", observation_id=obs, message="first")])
    store.upsert(
        "s1",
        [_item(session_id="s1", observation_id=obs, message="second", item_id="item-2")],
    )
    found = store.for_session("s1")
    assert [item.message for item in found] == ["second"]


def test_check_constraints_reject_bad_source_and_reason(db_engine: Engine) -> None:
    _session(db_engine, "s1")
    _attempt(db_engine, "a1", "s1")
    obs = _observation_id(db_engine, "a1")
    store = FeedbackRepository(db_engine)
    bad_rows: list[dict[str, Any]] = [
        {"source": "guess"},
        {"source": "template", "fallback_reason": "bogus"},
    ]
    for bad in bad_rows:
        item = _item(session_id="s1", observation_id=obs, **bad)
        try:
            store.upsert("s1", [item])
        except IntegrityError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_kind_is_none_for_an_unknown_session(db_engine: Engine) -> None:
    _session(db_engine, "s1", kind="baseline")
    sessions = SessionRepository(db_engine)
    assert sessions.kind("s1") == "baseline"
    assert sessions.kind("missing") is None


def test_analyzed_needs_a_finished_analyze_job_and_nothing_running(db_engine: Engine) -> None:
    """A session is analysed only when its recording's analyze job has ended (done or failed).
    No attempt, no upload, a queued job, or only a rescore is not an analysis."""
    cases = {
        "no-upload": ([], []),
        "queued": (["a-q"], [("j-q", "a-q", "queued", "analyze")]),
        "rescore-only": (["a-r"], [("j-r", "a-r", "done", "rescore")]),
        "done": (["a-d"], [("j-d", "a-d", "done", "analyze")]),
        "failed": (["a-f"], [("j-f", "a-f", "failed", "analyze")]),
        "one-still-queued": (
            ["a-x1", "a-x2"],
            [("j-x1", "a-x1", "done", "analyze"), ("j-x2", "a-x2", "queued", "analyze")],
        ),
    }
    for session_id, (attempt_ids, jobs_rows) in cases.items():
        _session(db_engine, session_id)
        for attempt_id in attempt_ids:
            _attempt(db_engine, attempt_id, session_id)
        for job_id, attempt_id, status, kind in jobs_rows:
            _job(db_engine, job_id, attempt_id, status, kind=kind)
    jobs = SessionJobRepository(db_engine)
    got = {session_id: jobs.analyzed(session_id) for session_id in cases}
    assert got == {
        "no-upload": False,
        "queued": False,
        "rescore-only": False,
        "done": True,
        "failed": True,
        "one-still-queued": False,
    }
