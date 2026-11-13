"""Response body of `GET /api/onboarding` (ARCHITECTURE.md section 13, Phase 0e)."""

from pydantic import BaseModel


class OnboardingBlockerOut(BaseModel):
    component: str
    status: str
    fix: str | None


class OnboardingOut(BaseModel):
    step: str
    blockers: list[OnboardingBlockerOut]
    calibration: str
    baseline: str
    baseline_session_id: str | None
