"""SQLAlchemy adapters for feedback: the session kind, its unfinished jobs and the stored items."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Engine, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nosolear.domain.taxonomy import Skill
from nosolear.persistence.models import (
    attempts,
    feedback_items,
    jobs,
    observations,
    sessions,
)
from nosolear.ports.feedback import FallbackReason, FeedbackItem, FeedbackSource


class SessionRepository:
    """`SessionReader` and `SessionCompleter`: a session's kind and its completion."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def kind(self, session_id: str) -> str | None:
        stmt = select(sessions.c.kind).where(sessions.c.id == session_id)
        with self._engine.connect() as conn:
            return cast(str | None, conn.execute(stmt).scalar_one_or_none())

    def completed_at(self, session_id: str) -> datetime | None:
        stmt = select(sessions.c.completed_at).where(sessions.c.id == session_id)
        with self._engine.connect() as conn:
            return cast(datetime | None, conn.execute(stmt).scalar_one_or_none())

    def claim(self, session_id: str, at: datetime) -> bool:
        """A guarded UPDATE: only the call that finds the session open gets rowcount 1."""
        with self._engine.begin() as conn:
            result = conn.execute(
                update(sessions)
                .where(sessions.c.id == session_id, sessions.c.completed_at.is_(None))
                .values(completed_at=at)
            )
        return result.rowcount == 1

    def reopen(self, session_id: str, at: datetime) -> bool:
        """Only the claim made at `at` is undone, so a later completion is never reopened."""
        with self._engine.begin() as conn:
            result = conn.execute(
                update(sessions)
                .where(sessions.c.id == session_id, sessions.c.completed_at == at)
                .values(completed_at=None)
            )
        return result.rowcount == 1


class SessionJobRepository:
    """`SessionJobStatus`: jobs still queued or running for the session's attempts."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def unfinished(self, session_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(jobs.join(attempts, jobs.c.attempt_id == attempts.c.id))
            .where(
                attempts.c.session_id == session_id,
                jobs.c.status.in_(("queued", "running")),
            )
        )
        with self._engine.connect() as conn:
            return int(conn.execute(stmt).scalar_one())


def _evidence_of(raw: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(raw))


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


class FeedbackRepository:
    """`FeedbackStore`: one row per (session, skill). The evidence fields are read from the
    observation the item points at, so they are never stored twice."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def for_session(self, session_id: str) -> list[FeedbackItem]:
        stmt = (
            select(
                feedback_items,
                observations.c.attempt_id,
                observations.c.evidence_json,
            )
            .join(observations, feedback_items.c.observation_id == observations.c.id)
            .where(feedback_items.c.session_id == session_id)
            .order_by(feedback_items.c.skill)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        items: list[FeedbackItem] = []
        for row in rows:
            evidence = _evidence_of(row.evidence_json)
            items.append(
                FeedbackItem(
                    id=row.id,
                    session_id=row.session_id,
                    skill=Skill(row.skill),
                    error_key=row.error_key,
                    observation_id=row.observation_id,
                    attempt_id=row.attempt_id,
                    start_ms=_int_or_none(evidence.get("start_ms")),
                    end_ms=_int_or_none(evidence.get("end_ms")),
                    word=_text_or_none(evidence.get("word")),
                    message=row.message,
                    model_text=row.model_text,
                    source=cast(FeedbackSource, row.source),
                    fallback_reason=cast(FallbackReason | None, row.fallback_reason),
                )
            )
        return items

    def upsert(self, session_id: str, items: Sequence[FeedbackItem]) -> None:
        stamp = datetime.now(UTC)
        with self._engine.begin() as conn:
            for item in items:
                if item.session_id != session_id:
                    raise ValueError("a feedback item belongs to another session")
                values = {
                    "id": item.id,
                    "session_id": session_id,
                    "skill": item.skill.value,
                    "error_key": item.error_key,
                    "observation_id": item.observation_id,
                    "message": item.message,
                    "model_text": item.model_text,
                    "source": item.source,
                    "fallback_reason": item.fallback_reason,
                    "created_at": stamp,
                }
                stmt = sqlite_insert(feedback_items).values(**values)
                conn.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["session_id", "skill"],
                        set_={
                            key: values[key]
                            for key in (
                                "error_key",
                                "observation_id",
                                "message",
                                "model_text",
                                "source",
                                "fallback_reason",
                                "created_at",
                            )
                        },
                    )
                )
