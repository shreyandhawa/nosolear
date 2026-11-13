"""SQLAlchemy adapters for scoring configs, extraction markers and their observations."""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, Row, insert, select
from sqlalchemy.exc import IntegrityError

from nosolear.domain.observations import Context, Observation, Outcome
from nosolear.domain.scoring import (
    ConfigKind,
    ScoringConfig,
    canonical_json,
    rules_from_json,
    rules_to_json,
)
from nosolear.domain.taxonomy import Detector, Taxonomy
from nosolear.persistence.models import extractions, scoring_configs
from nosolear.persistence.models import observations as observations_table


def observation_rows(items: Sequence[Observation], created_at: datetime) -> list[dict[str, Any]]:
    return [
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
            "scoring_config_id": o.scoring_config_id,
            "provisional": o.provisional,
        }
        for o in items
    ]


def observation_from_row(row: Row[Any]) -> Observation:
    return Observation(
        error_key=row.error_key,
        outcome=Outcome(row.outcome),
        weight=row.weight,
        detector=Detector(row.detector),
        context=Context(row.context),
        observed_at=row.observed_at,
        taxonomy_version=row.taxonomy_version,
        attempt_id=row.attempt_id,
        evidence=json.loads(row.evidence_json),
        scoring_config_id=row.scoring_config_id,
        provisional=row.provisional,
    )


def scoring_config_order(engine: Engine) -> list[str]:
    """`v0` first, then the calibrated configs by (created_at, id); the last entry is the newest."""
    with engine.connect() as conn:
        rows = list(
            conn.execute(
                select(scoring_configs.c.id, scoring_configs.c.kind, scoring_configs.c.created_at)
            ).all()
        )
    ordered = sorted(rows, key=lambda r: (r.kind != ConfigKind.V0.value, r.created_at, r.id))
    return [str(r.id) for r in ordered]


class ScoringConfigRepository:
    def __init__(self, engine: Engine, taxonomy: Taxonomy) -> None:
        self._engine = engine
        self._taxonomy = taxonomy

    def add(
        self, config: ScoringConfig, *, capabilities: Mapping[str, object], created_at: datetime
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(scoring_configs).values(
                    id=config.id,
                    kind=config.kind.value,
                    calibration_run_id=config.calibration_run_id,
                    rules_json=canonical_json(rules_to_json(config)),
                    capabilities_json=canonical_json(dict(capabilities)),
                    created_at=created_at,
                )
            )

    def get(self, config_id: str) -> ScoringConfig:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(scoring_configs).where(scoring_configs.c.id == config_id)
            ).first()
        if row is None:
            raise KeyError(config_id)
        return rules_from_json(
            config_id=row.id,
            kind=ConfigKind(row.kind),
            calibration_run_id=row.calibration_run_id,
            rules=json.loads(row.rules_json),
            taxonomy=self._taxonomy,
        )

    def order(self) -> list[str]:
        return scoring_config_order(self._engine)

    def newest(self) -> ScoringConfig:
        return self.get(self.order()[-1])


class ExtractionRepository:
    """One marker per (attempt, config, detector), written with that detector's observations."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(
        self,
        *,
        attempt_id: str,
        scoring_config_id: str,
        detector: Detector,
        observations: Sequence[Observation],
        created_at: datetime,
    ) -> bool:
        for o in observations:
            if (
                o.attempt_id != attempt_id
                or o.scoring_config_id != scoring_config_id
                or o.detector != detector
            ):
                raise ValueError("an observation must match the attempt, config and detector")
        if self._marked(attempt_id, scoring_config_id, detector):
            return False
        try:
            with self._engine.begin() as conn:
                # The marker goes first, so a duplicate from a concurrent writer fails before any
                # observation is written.
                conn.execute(
                    insert(extractions).values(
                        attempt_id=attempt_id,
                        scoring_config_id=scoring_config_id,
                        detector=detector.value,
                        observation_count=len(observations),
                        created_at=created_at,
                    )
                )
                if observations:
                    conn.execute(
                        insert(observations_table), observation_rows(observations, created_at)
                    )
        except IntegrityError:
            if self._marked(attempt_id, scoring_config_id, detector):
                return False
            raise
        return True

    def scored(self) -> list[tuple[str, str]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(extractions.c.attempt_id, extractions.c.scoring_config_id).order_by(
                    extractions.c.attempt_id, extractions.c.scoring_config_id
                )
            ).all()
        return [(r.attempt_id, r.scoring_config_id) for r in rows]

    def _marked(self, attempt_id: str, scoring_config_id: str, detector: Detector) -> bool:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(extractions.c.attempt_id).where(
                    extractions.c.attempt_id == attempt_id,
                    extractions.c.scoring_config_id == scoring_config_id,
                    extractions.c.detector == detector.value,
                )
            ).first()
        return row is not None
