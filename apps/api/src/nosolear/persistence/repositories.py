"""SQLAlchemy adapters for the storage ports."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, delete, insert, select

from nosolear.domain.estimates import BetaState, KeyEstimate
from nosolear.domain.observations import Context, Observation, Outcome
from nosolear.domain.profile import Profile, ProfileEntry
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import Detector, Taxonomy
from nosolear.persistence.models import (
    format_utc,
    observations,
    profile_entries,
    profile_snapshots,
)


def _now() -> datetime:
    return datetime.now(UTC)


class ObservationRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add_many(self, items: Sequence[Observation]) -> None:
        if not items:
            return
        created_at = _now()
        rows = [
            {
                "attempt_id": o.attempt_id,
                "error_key": o.error_key,
                "outcome": o.outcome.value,
                "weight": o.weight,
                "detector": o.detector.value,
                "context": o.context.value,
                "observed_at": o.observed_at,
                "evidence_json": json.dumps(dict(o.evidence)),
                "taxonomy_version": o.taxonomy_version,
                "created_at": created_at,
            }
            for o in items
        ]
        with self._engine.begin() as conn:
            conn.execute(insert(observations), rows)

    def all(self) -> list[Observation]:
        stmt = select(observations).order_by(observations.c.observed_at, observations.c.id)
        with self._engine.connect() as conn:
            return [
                Observation(
                    error_key=r.error_key,
                    outcome=Outcome(r.outcome),
                    weight=r.weight,
                    detector=Detector(r.detector),
                    context=Context(r.context),
                    observed_at=r.observed_at,
                    taxonomy_version=r.taxonomy_version,
                    attempt_id=r.attempt_id,
                    evidence=json.loads(r.evidence_json),
                )
                for r in conn.execute(stmt)
            ]


def _entry_row(profile: Profile, e: ProfileEntry) -> dict[str, Any]:
    return {
        "error_key": e.definition.key,
        "a": e.state.a,
        "b": e.state.b,
        "updated_at": e.state.updated_at,
        "p_hat": e.estimate.p_hat,
        "ci_low": e.estimate.ci_low,
        "ci_high": e.estimate.ci_high,
        "n_eff": e.estimate.n_eff,
        "status": e.status.value,
        "last_seen_at": e.last_seen_at,
        "priority": e.priority,
        "as_of": profile.as_of,
        "algo_version": profile.algo_version,
        "taxonomy_version": profile.taxonomy_version,
    }


def _snapshot_entry(row: dict[str, Any]) -> dict[str, Any]:
    stored = ("error_key", "a", "b", "p_hat", "ci_low", "ci_high", "n_eff", "status", "priority")
    return {
        **{k: row[k] for k in stored},
        "updated_at": format_utc(row["updated_at"]),
        "last_seen_at": format_utc(row["last_seen_at"]),
    }


class ProfileRepository:
    def __init__(self, engine: Engine, taxonomy: Taxonomy) -> None:
        self._engine = engine
        self._taxonomy = taxonomy

    def save(self, profile: Profile, *, session_id: str | None, reason: str) -> str:
        """Replace every current entry and append a snapshot, atomically."""
        rows = [_entry_row(profile, e) for e in profile.entries]
        snapshot_id = uuid4().hex
        with self._engine.begin() as conn:
            conn.execute(delete(profile_entries))
            if rows:
                conn.execute(insert(profile_entries), rows)
            conn.execute(
                insert(profile_snapshots).values(
                    id=snapshot_id,
                    session_id=session_id,
                    reason=reason,
                    taken_at=_now(),
                    as_of=profile.as_of,
                    algo_version=profile.algo_version,
                    taxonomy_version=profile.taxonomy_version,
                    entries_json=json.dumps([_snapshot_entry(r) for r in rows]),
                )
            )
        return snapshot_id

    def latest(self) -> Profile | None:
        stmt = select(profile_entries).order_by(
            profile_entries.c.priority.desc(), profile_entries.c.error_key
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        if not rows:
            return None
        entries = tuple(
            ProfileEntry(
                definition=self._taxonomy.get(r.error_key),
                state=BetaState(a=r.a, b=r.b, updated_at=r.updated_at),
                estimate=KeyEstimate(
                    p_hat=r.p_hat, ci_low=r.ci_low, ci_high=r.ci_high, n_eff=r.n_eff
                ),
                status=Status(r.status),
                last_seen_at=r.last_seen_at,
                priority=r.priority,
            )
            for r in rows
        )
        first = rows[0]
        return Profile(
            as_of=first.as_of,
            taxonomy_version=first.taxonomy_version,
            algo_version=first.algo_version,
            entries=entries,
        )
