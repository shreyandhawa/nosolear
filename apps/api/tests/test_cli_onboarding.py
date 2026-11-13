"""`nosolear onboarding` prints the next step and its hint; `stand-in` refuses a closed session."""

from collections.abc import Callable

from baseline_fixtures import small_baseline_content
from harness import Harness

from nosolear.cli import main
from nosolear.cli_client import ApiClient
from nosolear.domain.onboarding import Component
from nosolear.domain.readiness import ReadinessReport, ReadinessRow, ReadinessStatus


def _api(h: Harness) -> ApiClient:
    return ApiClient(h.client)  # pyright: ignore[reportArgumentType]


def test_onboarding_prints_the_calibration_hint(
    make_harness: Callable[..., Harness], capsys
) -> None:
    h = make_harness(content=small_baseline_content())
    assert main(["onboarding"], client=_api(h)) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == [
        "Next: calibration",
        "  nosolear calibrate start (or nosolear calibrate skip)",
    ]


def test_onboarding_prints_each_blocker_fix(make_harness: Callable[..., Harness], capsys) -> None:
    rows = tuple(
        ReadinessRow(
            component,
            ReadinessStatus.MISSING if component is Component.ANTHROPIC else ReadinessStatus.READY,
            "reason",
            "set NOSOLEAR_ANTHROPIC_API_KEY in .env" if component is Component.ANTHROPIC else None,
        )
        for component in Component
    )
    h = make_harness(readiness=ReadinessReport(rows=rows))
    assert main(["onboarding"], client=_api(h)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Next: readiness",
        "  set NOSOLEAR_ANTHROPIC_API_KEY in .env",
    ]


def test_stand_in_refuses_a_closed_session_with_a_safe_message(
    make_harness: Callable[..., Harness], capsys
) -> None:
    h = make_harness(content=small_baseline_content())
    assert main(["stand-in", "baseline"], client=_api(h), synthesizer=h.synthesizer) == 2
    assert "No baseline exists yet." in capsys.readouterr().err
