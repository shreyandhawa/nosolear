"""SQLAlchemy adapter for the baseline session: its session row, one attempt per protocol item,
the per-skill scores, and completion."""

import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Final, cast
from uuid import uuid4

from sqlalchemy import Engine, Row, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nosolear.domain.content import BaselineProtocol
from nosolear.domain.jobs import JobKind
from nosolear.domain.skill_scores import SkillScore
from nosolear.domain.taxonomy import Skill
from nosolear.persistence.models import attempts, jobs, recordings, sessions, skill_scores
from nosolear.persistence.transactions import immediate
from nosolear.ports.baseline_store import BaselineItemRecord, BaselineSessionRecord

SCRIPTED_SECTIONS: Final = frozenset({"read_aloud", "word_list"})
ONE_MICROSECOND: Final = timedelta(microseconds=1)
_SKILL_ORDER: Final = {skill: index for index, skill in enumerate(Skill)}
_OPEN_SESSION: Final = (
    select(sessions)
    .where(sessions.c.kind == "baseline", sessions.c.completed_at.is_(None))
    .order_by(sessions.c.started_at.desc())
    .limit(1)
)


def _session(row: Row[Any]) -> BaselineSessionRecord:
    return BaselineSessionRecord(
        id=row.id,
        protocol_version=row.protocol_version,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _floats(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    items = cast(dict[str, object], raw)
    return {key: float(value) for key, value in items.items() if isinstance(value, int | float)}


class BaselineRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(
        self, *, session_id: str, protocol: BaselineProtocol, now: datetime
    ) -> BaselineSessionRecord:
        """Opens a session with its protocol attempts, or returns the one already open. The check
        and the insert share one `BEGIN IMMEDIATE`, so two concurrent starts cannot both create."""
        with immediate(self._engine) as conn:
            open_row = conn.execute(_OPEN_SESSION).first()
            if open_row is not None:
                return _session(open_row)
            conn.execute(
                insert(sessions).values(
                    id=session_id,
                    kind="baseline",
                    protocol_version=protocol.version,
                    started_at=now,
                    completed_at=None,
                )
            )
            order = 0
            for section in protocol.sections:
                scripted = section.name in SCRIPTED_SECTIONS
                for entry in section.items:
                    conn.execute(
                        insert(attempts).values(
                            id=uuid4().hex,
                            session_id=session_id,
                            step=section.step.value,
                            reference_text=entry.item.text if scripted else None,
                            scripted=scripted,
                            created_at=now + order * ONE_MICROSECOND,
                            content_item_id=entry.item.id,
                        )
                    )
                    order += 1
        return BaselineSessionRecord(
            id=session_id,
            protocol_version=protocol.version,
            started_at=now,
            completed_at=None,
        )

    def open_session(self) -> BaselineSessionRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(_OPEN_SESSION).first()
        return None if row is None else _session(row)

    def latest_completed(self) -> BaselineSessionRecord | None:
        stmt = (
            select(sessions)
            .where(sessions.c.kind == "baseline", sessions.c.completed_at.is_not(None))
            .order_by(sessions.c.completed_at.desc())
            .limit(1)
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        return None if row is None else _session(row)

    def completed_sessions(self) -> list[BaselineSessionRecord]:
        stmt = (
            select(sessions)
            .where(sessions.c.kind == "baseline", sessions.c.completed_at.is_not(None))
            .order_by(sessions.c.completed_at, sessions.c.id)
        )
        with self._engine.connect() as conn:
            return [_session(row) for row in conn.execute(stmt)]

    def items(self, session_id: str) -> list[BaselineItemRecord]:
        with self._engine.connect() as conn:
            started_at = conn.execute(
                select(sessions.c.started_at).where(sessions.c.id == session_id)
            ).scalar_one()
            rows = conn.execute(
                select(attempts)
                .where(attempts.c.session_id == session_id)
                .order_by(attempts.c.created_at, attempts.c.id)
            ).all()
            out: list[BaselineItemRecord] = []
            for row in rows:
                recorded = conn.execute(
                    select(recordings.c.id).where(recordings.c.attempt_id == row.id)
                ).first()
                job_status = conn.execute(
                    select(jobs.c.status)
                    .where(jobs.c.attempt_id == row.id, jobs.c.kind == JobKind.ANALYZE.value)
                    .order_by(jobs.c.created_at.desc())
                    .limit(1)
                ).scalar()
                out.append(
                    BaselineItemRecord(
                        attempt_id=row.id,
                        order=int((row.created_at - started_at) / ONE_MICROSECOND),
                        item_id=row.content_item_id,
                        step=row.step,
                        scripted=bool(row.scripted),
                        recorded=recorded is not None,
                        job_status=None if job_status is None else str(job_status),
                    )
                )
        return out

    def complete(self, session_id: str, *, completed_at: datetime) -> bool:
        """Closes the session only while it is open. Returns False when it was already closed, so
        exactly one of two concurrent completes claims it."""
        with self._engine.begin() as conn:
            result = conn.execute(
                update(sessions)
                .where(sessions.c.id == session_id, sessions.c.completed_at.is_(None))
                .values(completed_at=completed_at)
            )
        return result.rowcount == 1

    def reopen(self, session_id: str) -> bool:
        """Undoes a `complete` whose report could not be built. It reopens the session only when
        no other baseline is open, so the store never holds two open sessions. Returns whether it
        reopened."""
        with immediate(self._engine) as conn:
            if conn.execute(_OPEN_SESSION).first() is not None:
                return False
            result = conn.execute(
                update(sessions)
                .where(sessions.c.id == session_id, sessions.c.completed_at.is_not(None))
                .values(completed_at=None)
            )
        return result.rowcount == 1

    def save_scores(self, session_id: str, scores: Sequence[SkillScore]) -> None:
        with self._engine.begin() as conn:
            for score in scores:
                components = json.dumps(
                    {"values": dict(score.values), "scores": dict(score.scores)},
                    sort_keys=True,
                )
                stmt = (
                    sqlite_insert(skill_scores)
                    .values(
                        session_id=session_id,
                        skill=score.skill.value,
                        score=score.score,
                        components_json=components,
                    )
                    .on_conflict_do_update(
                        index_elements=[skill_scores.c.session_id, skill_scores.c.skill],
                        set_={
                            "score": score.score,
                            "components_json": components,
                        },
                    )
                )
                conn.execute(stmt)

    def scores(self, session_id: str) -> tuple[SkillScore, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(skill_scores).where(skill_scores.c.session_id == session_id)
            ).all()
        out: list[SkillScore] = []
        for row in rows:
            components: dict[str, object] = json.loads(row.components_json)
            out.append(
                SkillScore(
                    skill=Skill(row.skill),
                    score=float(row.score),
                    values=_floats(components.get("values")),
                    scores=_floats(components.get("scores")),
                )
            )
        out.sort(key=lambda s: _SKILL_ORDER[s.skill])
        return tuple(out)
