"""`GET /api/onboarding`: the first-run step, read without writing anything."""

from typing import Annotated

from fastapi import APIRouter, Depends

from nosolear.api.deps import (
    get_attempt_repository,
    get_baseline_store,
    get_calibration_store,
    get_readiness_report,
)
from nosolear.api.onboarding_schemas import OnboardingBlockerOut, OnboardingOut
from nosolear.app.onboarding import OnboardingState, onboarding_state
from nosolear.domain.onboarding import OnboardingStep
from nosolear.domain.readiness import ReadinessReport
from nosolear.persistence.repositories import AttemptRepository
from nosolear.ports.baseline_store import BaselineStore
from nosolear.ports.calibration_store import CalibrationStore

router = APIRouter()
DAILY_KIND = "daily"


def _out(state: OnboardingState) -> OnboardingOut:
    step: OnboardingStep = state.step
    return OnboardingOut(
        step=step.value,
        blockers=[
            OnboardingBlockerOut(
                component=row.component.value, status=row.status.value, fix=row.fix
            )
            for row in state.blockers
        ],
        calibration=state.calibration,
        baseline=state.baseline,
        baseline_session_id=state.baseline_session_id,
    )


@router.get("/api/onboarding", operation_id="getOnboarding")
def get_onboarding(
    readiness: Annotated[ReadinessReport, Depends(get_readiness_report)],
    calibration: Annotated[CalibrationStore, Depends(get_calibration_store)],
    baselines: Annotated[BaselineStore, Depends(get_baseline_store)],
    attempts: Annotated[AttemptRepository, Depends(get_attempt_repository)],
) -> OnboardingOut:
    state = onboarding_state(
        readiness=readiness,
        calibration=calibration,
        baselines=baselines,
        daily_sessions=attempts.count_sessions(DAILY_KIND),
    )
    return _out(state)
