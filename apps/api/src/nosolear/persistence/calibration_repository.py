"""SQLAlchemy adapter for the calibration run, its session, attempts and trials."""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, Row, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nosolear.domain.analyses import AnalysisKind
from nosolear.domain.calibration import CalibrationPlan, Trial, TrialKind
from nosolear.domain.jobs import JobKind
from nosolear.domain.scoring import ScoringConfig, canonical_json, rules_to_json
from nosolear.domain.speech import RawResult
from nosolear.domain.taxonomy import Detector
from nosolear.persistence.models import (
    analyses,
    attempts,
    calibration_runs,
    calibration_trials,
    jobs,
    recordings,
    scoring_configs,
    sessions,
    tts_cache,
)
from nosolear.persistence.transactions import immediate
from nosolear.ports.calibration_store import (
    CalibrationItemRecord,
    CalibrationRunRecord,
    RunAlreadyOpen,
    TrialRecord,
)
from nosolear.ports.clock import Clock

CALIBRATION_STEP = "calibration"
ONE_MICROSECOND = timedelta(microseconds=1)


def _run(row: Row[Any]) -> CalibrationRunRecord:
    return CalibrationRunRecord(
        id=row.id,
        session_id=row.session_id,
        status=row.status,
        scoring_config_id=row.scoring_config_id,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _evidence(take: int, deliberate: bool, word: str) -> str:
    return json.dumps({"take": take, "deliberate": deliberate, "word": word}, sort_keys=True)


class CalibrationRepository:
    def __init__(self, engine: Engine, clock: Clock) -> None:
        self._engine = engine
        self._clock = clock

    def running(self) -> CalibrationRunRecord | None:
        stmt = select(calibration_runs).where(calibration_runs.c.status == "running")
        with self._engine.connect() as conn:
            row = conn.execute(stmt.limit(1)).first()
        return None if row is None else _run(row)

    def latest(self) -> CalibrationRunRecord | None:
        stmt = select(calibration_runs).order_by(
            calibration_runs.c.started_at.desc(), calibration_runs.c.id.desc()
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt.limit(1)).first()
        return None if row is None else _run(row)

    def start(
        self, *, run_id: str, session_id: str, plan: CalibrationPlan, now: datetime
    ) -> CalibrationRunRecord:
        with immediate(self._engine) as conn:
            open_run = conn.execute(
                select(calibration_runs.c.id).where(calibration_runs.c.status == "running")
            ).first()
            if open_run is not None:
                raise RunAlreadyOpen("A calibration run is already in progress.")
            conn.execute(
                insert(sessions).values(
                    id=session_id,
                    kind="calibration",
                    protocol_version=1,
                    started_at=now,
                    completed_at=None,
                )
            )
            conn.execute(
                insert(calibration_runs).values(
                    id=run_id,
                    session_id=session_id,
                    status="running",
                    scoring_config_id=None,
                    started_at=now,
                    completed_at=None,
                )
            )
            for token in plan.tokens:
                attempt_id = uuid4().hex
                conn.execute(
                    insert(attempts).values(
                        id=attempt_id,
                        session_id=session_id,
                        step=CALIBRATION_STEP,
                        reference_text=token.word,
                        scripted=True,
                        created_at=now + token.order * ONE_MICROSECOND,
                        content_item_id=token.item_id,
                    )
                )
                for detector in plan.detectors[token.error_key]:
                    conn.execute(
                        insert(calibration_trials).values(
                            run_id=run_id,
                            error_key=token.error_key,
                            detector=detector.value,
                            kind=TrialKind.ERROR.value
                            if token.deliberate
                            else TrialKind.CONTROL.value,
                            attempt_id=attempt_id,
                            tts_hash=None,
                            flagged=None,
                            evidence_json=_evidence(token.take, token.deliberate, token.word),
                        )
                    )
        return CalibrationRunRecord(
            id=run_id,
            session_id=session_id,
            status="running",
            scoring_config_id=None,
            started_at=now,
            completed_at=None,
        )

    def skip(self, *, run_id: str, now: datetime) -> CalibrationRunRecord:
        with self._engine.begin() as conn:
            open_run = conn.execute(
                select(calibration_runs.c.id).where(calibration_runs.c.status == "running")
            ).first()
            if open_run is not None:
                conn.execute(
                    update(calibration_runs)
                    .where(calibration_runs.c.id == open_run.id)
                    .values(status="skipped", completed_at=now)
                )
                run_id = str(open_run.id)
            else:
                conn.execute(
                    insert(calibration_runs).values(
                        id=run_id,
                        session_id=None,
                        status="skipped",
                        scoring_config_id=None,
                        started_at=now,
                        completed_at=now,
                    )
                )
        found = self._run_row(run_id)
        assert found is not None
        return found

    def _run_row(self, run_id: str) -> CalibrationRunRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(calibration_runs).where(calibration_runs.c.id == run_id)
            ).first()
        return None if row is None else _run(row)

    def items(self, run_id: str) -> list[CalibrationItemRecord]:
        run = self._run_row(run_id)
        if run is None or run.session_id is None:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(attempts)
                .where(attempts.c.session_id == run.session_id)
                .order_by(attempts.c.created_at, attempts.c.id)
            ).all()
            out: list[CalibrationItemRecord] = []
            for row in rows:
                trial = conn.execute(
                    select(calibration_trials.c.error_key, calibration_trials.c.evidence_json)
                    .where(calibration_trials.c.attempt_id == row.id)
                    .limit(1)
                ).one()
                evidence = json.loads(trial.evidence_json)
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
                    CalibrationItemRecord(
                        attempt_id=row.id,
                        order=_order(row.created_at, run.started_at),
                        item_id=row.content_item_id,
                        error_key=trial.error_key,
                        word=row.reference_text,
                        deliberate=bool(evidence["deliberate"]),
                        take=int(evidence["take"]),
                        recorded=recorded is not None,
                        job_status=None if job_status is None else str(job_status),
                    )
                )
        return out

    def trials(self, run_id: str) -> list[TrialRecord]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(calibration_trials)
                .where(calibration_trials.c.run_id == run_id)
                .order_by(calibration_trials.c.id)
            ).all()
        return [
            TrialRecord(
                id=row.id,
                trial=Trial(
                    error_key=row.error_key,
                    detector=Detector(row.detector),
                    kind=TrialKind(row.kind),
                    attempt_id=row.attempt_id,
                    tts_hash=row.tts_hash,
                    flagged=row.flagged,
                ),
            )
            for row in rows
        ]

    def control_words(self, run_id: str) -> dict[str, str]:
        stmt = (
            select(tts_cache.c.hash, tts_cache.c.text)
            .join(calibration_trials, calibration_trials.c.tts_hash == tts_cache.c.hash)
            .where(calibration_trials.c.run_id == run_id)
            .distinct()
        )
        with self._engine.connect() as conn:
            return {str(row.hash): str(row.text) for row in conn.execute(stmt)}

    def control_analysis(self, tts_hash: str, run_id: str, kind: AnalysisKind) -> RawResult | None:
        stmt = select(analyses).where(
            analyses.c.tts_hash == tts_hash,
            analyses.c.calibration_run_id == run_id,
            analyses.c.kind == kind.value,
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        if row is None:
            return None
        return RawResult(
            provider=row.provider,
            provider_version=row.provider_version,
            adapter=row.adapter,
            adapter_version=row.adapter_version,
            payload=json.loads(row.raw_json),
        )

    def add_control_analysis(
        self, tts_hash: str, run_id: str, kind: AnalysisKind, raw: RawResult
    ) -> None:
        stmt = (
            sqlite_insert(analyses)
            .values(
                attempt_id=None,
                tts_hash=tts_hash,
                calibration_run_id=run_id,
                kind=kind.value,
                provider=raw.provider,
                provider_version=raw.provider_version,
                adapter=raw.adapter,
                adapter_version=raw.adapter_version,
                raw_json=json.dumps(dict(raw.payload), sort_keys=True),
                created_at=self._clock.now(),
            )
            .on_conflict_do_nothing()
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def add_control_trials(
        self, run_id: str, tts_hash: str, pairs: Sequence[tuple[str, Detector]]
    ) -> None:
        if not pairs:
            return
        rows = [
            {
                "run_id": run_id,
                "error_key": key,
                "detector": detector.value,
                "kind": TrialKind.CONTROL.value,
                "attempt_id": None,
                "tts_hash": tts_hash,
                "flagged": None,
                "evidence_json": "{}",
            }
            for key, detector in pairs
        ]
        with self._engine.begin() as conn:
            conn.execute(sqlite_insert(calibration_trials).values(rows).on_conflict_do_nothing())

    def set_flags(self, flags: Mapping[int, bool | None]) -> None:
        with self._engine.begin() as conn:
            for trial_id, flag in flags.items():
                conn.execute(
                    update(calibration_trials)
                    .where(calibration_trials.c.id == trial_id)
                    .values(flagged=flag)
                )

    def complete(
        self,
        *,
        run_id: str,
        config: ScoringConfig,
        capabilities: Mapping[str, object],
        now: datetime,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(scoring_configs).values(
                    id=config.id,
                    kind=config.kind.value,
                    calibration_run_id=config.calibration_run_id,
                    rules_json=canonical_json(rules_to_json(config)),
                    capabilities_json=canonical_json(dict(capabilities)),
                    created_at=now,
                )
            )
            result = conn.execute(
                update(calibration_runs)
                .where(
                    calibration_runs.c.id == run_id,
                    calibration_runs.c.status == "running",
                )
                .values(status="done", scoring_config_id=config.id, completed_at=now)
            )
            if result.rowcount != 1:
                raise RuntimeError("the calibration run is not running")

    def open_calibrate_job(self) -> str | None:
        stmt = (
            select(jobs.c.id)
            .where(
                jobs.c.kind == JobKind.CALIBRATE.value,
                jobs.c.status.in_(("queued", "running")),
            )
            .order_by(jobs.c.created_at, jobs.c.id)
            .limit(1)
        )
        with self._engine.connect() as conn:
            found = conn.execute(stmt).scalar()
        return None if found is None else str(found)


def _order(created_at: datetime, started_at: datetime) -> int:
    return int((created_at - started_at) / ONE_MICROSECOND)
