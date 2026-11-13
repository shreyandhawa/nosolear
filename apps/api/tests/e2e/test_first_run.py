"""The first run end to end, through the API and the CLI, with TTS audio standing in for a voice.

Every provider is an oracle, so no test makes a paid call or needs keys. The oracle's user error
applies to every word it hears, so a calibration runs on a clean voice (as the baseline tests do).
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

import pytest
from factories import T0, TAX
from harness import Harness

from nosolear.cli import main
from nosolear.cli_client import ApiClient
from nosolear.domain.coach import Rubric
from nosolear.persistence.repositories import ObservationRepository
from nosolear.persistence.scoring_repository import ScoringConfigRepository

RUBRIC = Rubric(structure=3, clarity=3, concision=3)


class SteppingClock:
    """Each reading is a second later. A fixed clock would give a re-started calibration run the
    same start time as the one it replaces, and the newest run would then be a tie."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


@pytest.fixture
def first_run(make_harness: Callable[..., Harness], monkeypatch: pytest.MonkeyPatch) -> Harness:
    h = make_harness(start_runner=True, rubric=RUBRIC, clock=SteppingClock(T0))
    # The CLI reads its data directory from the environment, as it does for a real run.
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(h.data_dir))
    return h


def cli(h: Harness, *argv: str) -> int:
    # TestClient is an httpx client at runtime; the stub is typed narrower than it is.
    client: Any = ApiClient(h.client)  # pyright: ignore[reportArgumentType]
    return main(list(argv), client=client, synthesizer=h.synthesizer)


def step(h: Harness) -> str:
    body: dict[str, Any] = h.client.get("/api/onboarding").json()
    return str(body["step"])


@contextmanager
def clean_voice(h: Harness) -> Iterator[None]:
    saved = dict(h.voice.user_errors)
    h.voice.user_errors.clear()
    try:
        yield
    finally:
        h.voice.user_errors.update(saved)


def _vw(report: dict[str, Any]) -> dict[str, Any]:
    return next(i for i in report["items"] if i["error_key"] == "sound.sub.v.w")


def test_first_run_through_api_and_cli(first_run: Harness):
    h = first_run
    assert step(h) == "calibration"
    assert cli(h, "calibrate", "start") == 0
    with clean_voice(h):
        assert cli(h, "stand-in", "calibration") == 0
        assert cli(h, "calibrate", "finish") == 0
    assert step(h) == "baseline"

    h.voice.user_errors["v"] = "w"
    assert cli(h, "baseline", "start") == 0
    assert cli(h, "stand-in", "baseline") == 0
    assert cli(h, "baseline", "complete") == 0

    report = h.client.get("/api/baseline/report").json()
    vw = _vw(report)
    assert vw["provisional"] is False and vw["clips"]
    assert {s["skill"] for s in report["skill_scores"]} == {"sounds", "on_the_spot", "articulate"}
    assert step(h) == "report"


def test_skip_then_calibrate_later_rescores_without_provider_calls(first_run: Harness):
    h = first_run
    assert cli(h, "calibrate", "skip") == 0
    assert step(h) == "baseline"

    h.voice.user_errors["v"] = "w"
    assert cli(h, "baseline", "start") == 0
    assert cli(h, "stand-in", "baseline") == 0
    assert cli(h, "baseline", "complete") == 0
    assert _vw(h.client.get("/api/baseline/report").json())["provisional"] is True
    assert step(h) == "report"

    with clean_voice(h):
        assert cli(h, "calibrate", "start") == 0
        assert cli(h, "stand-in", "calibration") == 0
        assert cli(h, "calibrate", "finish") == 0
    h.client.app.state.services.runner.wait_idle()  # pyright: ignore[reportAttributeAccessIssue]

    calls_before = dict(h.voice.calls)
    ledger_before = h.ledger_rows()
    assert cli(h, "rescore") == 0
    h.client.app.state.services.runner.wait_idle()  # pyright: ignore[reportAttributeAccessIssue]
    assert dict(h.voice.calls) == calls_before
    assert h.ledger_rows() == ledger_before

    assert _vw(h.client.get("/api/baseline/report").json())["provisional"] is False
    newest = ScoringConfigRepository(h.engine, TAX).newest().id
    baseline_ids = {i["attempt_id"] for i in h.client.get("/api/baseline").json()["items"]}
    scored = {
        o.scoring_config_id
        for o in ObservationRepository(h.engine).current()
        if o.attempt_id in baseline_ids
    }
    assert scored == {newest}
    assert step(h) == "report"
