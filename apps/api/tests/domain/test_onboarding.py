"""The first-run path: the next step, and the readiness rows that block it."""

import pytest

from nosolear.domain.onboarding import (
    OnboardingFacts,
    OnboardingStep,
    next_step,
    readiness_blockers,
)
from nosolear.domain.readiness import (
    Component,
    ReadinessReport,
    ReadinessRow,
    ReadinessStatus,
)

READY = ReadinessStatus.READY


def F(
    blockers: tuple[str, ...] = (),
    calibration: str = "not_run",
    baseline: str = "not_started",
    daily_sessions: int = 0,
) -> OnboardingFacts:
    return OnboardingFacts(
        blockers=blockers,
        calibration=calibration,  # type: ignore[arg-type]
        baseline=baseline,  # type: ignore[arg-type]
        daily_sessions=daily_sessions,
    )


@pytest.mark.parametrize(
    ("facts", "step"),
    [
        (F(blockers=("anthropic",)), OnboardingStep.READINESS),
        (F(), OnboardingStep.CALIBRATION),
        (F(calibration="running"), OnboardingStep.CALIBRATION),
        (F(calibration="skipped"), OnboardingStep.BASELINE),
        (F(calibration="done", baseline="open"), OnboardingStep.BASELINE),
        (F(calibration="done", baseline="completed"), OnboardingStep.REPORT),
        # A re-calibration after the baseline never sends onboarding back.
        (F(calibration="running", baseline="completed"), OnboardingStep.REPORT),
        (
            F(calibration="skipped", baseline="completed", daily_sessions=1),
            OnboardingStep.DAILY_PLAN,
        ),
    ],
)
def test_next_step(facts: OnboardingFacts, step: OnboardingStep) -> None:
    assert next_step(facts) is step


def _report(**statuses: ReadinessStatus) -> ReadinessReport:
    rows = [
        ReadinessRow(component, statuses.get(component.value, READY), "reason", None)
        for component in Component
    ]
    return ReadinessReport(rows=tuple(rows))


def test_phone_probe_and_usage_never_block() -> None:
    report = _report(phone_probe=ReadinessStatus.NOT_INSTALLED, usage=ReadinessStatus.DEGRADED)
    assert readiness_blockers(report) == ()


def test_unprobed_azure_capabilities_block() -> None:
    report = _report(azure_capabilities=ReadinessStatus.NOT_PROBED)
    assert readiness_blockers(report) == ("azure_capabilities",)


def test_missing_transcriber_blocks_but_degraded_does_not() -> None:
    assert readiness_blockers(_report(transcriber=ReadinessStatus.NOT_INSTALLED)) == (
        "transcriber",
    )
    assert readiness_blockers(_report(transcriber=ReadinessStatus.DEGRADED)) == ()


def test_degraded_azure_speech_blocks() -> None:
    assert readiness_blockers(_report(azure_speech=ReadinessStatus.DEGRADED)) == ("azure_speech",)


def test_blockers_come_in_row_order() -> None:
    report = _report(
        anthropic=ReadinessStatus.MISSING,
        azure_speech=ReadinessStatus.MISSING,
    )
    names = readiness_blockers(report)
    assert names == ("azure_speech", "anthropic")
    assert names == tuple(
        row.component.value for row in report.rows if row.component.value in names
    )
