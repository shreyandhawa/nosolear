"""The onboarding state a learner sees: readiness, calibration and baseline, read without writing.
The use case takes its ports as arguments and calls no provider."""

from dataclasses import dataclass
from typing import Literal

from nosolear.domain.onboarding import (
    OnboardingFacts,
    OnboardingStep,
    next_step,
    readiness_blockers,
)
from nosolear.domain.readiness import ReadinessReport, ReadinessRow
from nosolear.ports.baseline_store import BaselineStore
from nosolear.ports.calibration_store import CalibrationRunRecord, CalibrationStore

CalibrationStatus = Literal["not_run", "running", "done", "skipped"]
BaselineStatus = Literal["not_started", "open", "completed"]


@dataclass(frozen=True, slots=True)
class OnboardingState:
    step: OnboardingStep
    blockers: tuple[ReadinessRow, ...]
    calibration: CalibrationStatus
    baseline: BaselineStatus
    baseline_session_id: str | None


def _calibration_status(run: CalibrationRunRecord | None) -> CalibrationStatus:
    if run is None:
        return "not_run"
    if run.status == "running":
        return "running"
    if run.status == "skipped":
        return "skipped"
    return "done"


def _baseline_status(baselines: BaselineStore) -> tuple[BaselineStatus, str | None]:
    open_session = baselines.open_session()
    if open_session is not None:
        return "open", open_session.id
    completed = baselines.latest_completed()
    if completed is not None:
        return "completed", completed.id
    return "not_started", None


def onboarding_state(
    *,
    readiness: ReadinessReport,
    calibration: CalibrationStore,
    baselines: BaselineStore,
    daily_sessions: int,
) -> OnboardingState:
    names = readiness_blockers(readiness)
    blockers = tuple(row for row in readiness.rows if row.component.value in names)
    cal = _calibration_status(calibration.latest())
    base, base_id = _baseline_status(baselines)
    step = next_step(
        OnboardingFacts(
            blockers=names,
            calibration=cal,
            baseline=base,
            daily_sessions=daily_sessions,
        )
    )
    return OnboardingState(
        step=step,
        blockers=blockers,
        calibration=cal,
        baseline=base,
        baseline_session_id=base_id,
    )
