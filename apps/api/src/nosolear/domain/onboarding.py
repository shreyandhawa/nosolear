"""The first-run path: the step a learner is on, and the readiness rows that block it. Pure: no
I/O. Blocking is decided here so the routes, the CLI and the tests read one rule."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from nosolear.domain.readiness import Component, ReadinessReport, ReadinessStatus


class OnboardingStep(StrEnum):
    READINESS = "readiness"
    CALIBRATION = "calibration"
    BASELINE = "baseline"
    REPORT = "report"
    DAILY_PLAN = "daily_plan"


_NOT_READY: frozenset[str] = frozenset(
    status.value for status in ReadinessStatus if status is not ReadinessStatus.READY
)

BLOCKING: Mapping[str, frozenset[str]] = {
    Component.AZURE_SPEECH.value: _NOT_READY,
    Component.ANTHROPIC.value: _NOT_READY,
    Component.LANGUAGE_PACK.value: _NOT_READY,
    Component.DATA_DIR.value: _NOT_READY,
    Component.AZURE_CAPABILITIES.value: frozenset(
        {ReadinessStatus.MISSING.value, ReadinessStatus.NOT_PROBED.value}
    ),
    Component.TRANSCRIBER.value: frozenset(
        {ReadinessStatus.MISSING.value, ReadinessStatus.NOT_INSTALLED.value}
    ),
}
"""Component to the statuses that block onboarding. The phone probe and usage never block."""


def readiness_blockers(report: ReadinessReport) -> tuple[str, ...]:
    """The blocking components' names, in row order."""
    return tuple(
        row.component.value
        for row in report.rows
        if row.status.value in BLOCKING.get(row.component.value, frozenset())
    )


@dataclass(frozen=True, slots=True)
class OnboardingFacts:
    blockers: tuple[str, ...]
    calibration: Literal["not_run", "running", "done", "skipped"]
    baseline: Literal["not_started", "open", "completed"]
    daily_sessions: int


def next_step(f: OnboardingFacts) -> OnboardingStep:
    """Checked in order: blockers first, then a completed baseline, then calibration, then the
    baseline. Re-calibrating after a baseline never sends the learner back."""
    if f.blockers:
        return OnboardingStep.READINESS
    if f.baseline == "completed":
        return OnboardingStep.DAILY_PLAN if f.daily_sessions > 0 else OnboardingStep.REPORT
    if f.calibration in ("not_run", "running"):
        return OnboardingStep.CALIBRATION
    return OnboardingStep.BASELINE
