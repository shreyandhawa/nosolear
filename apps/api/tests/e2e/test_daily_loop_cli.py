"""The daily loop through the CLI: `daily run` does the whole day, and tomorrow's `plan` shows
the focus for today's worst miss. The runner is real and threaded, so `follow_job` sees the job end
on its own. Oracle providers and fakes only; no paid call."""

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from e2e.test_daily_loop import SPOKEN, MovableClock, NoScorer, _coach, _speaker
from factories import T0
from harness import Harness

from nosolear.cli import main
from nosolear.cli_client import ApiClient

CARD_PREFIXES = ("sounds:", "on_the_spot:", "articulate:")


def _record_wav(h: Harness, tmp_path: Path) -> Path:
    clip = h.synthesizer.synthesize(SPOKEN)
    wav = tmp_path / "speech.wav"
    wav.write_bytes((h.data_dir / clip.path).read_bytes())
    return wav


def _api(h: Harness) -> ApiClient:
    # TestClient is an httpx client at runtime; the stub is typed narrower than it is.
    return ApiClient(h.client)  # pyright: ignore[reportArgumentType]


def test_daily_run_through_cli(
    make_harness: Callable[..., Harness],
    tmp_path: Path,
    capsys: Any,
) -> None:
    clock = MovableClock(T0)
    h = make_harness(start_runner=True, clock=clock, coach=_coach())
    _speaker(h)
    wav = _record_wav(h, tmp_path)
    capsys.readouterr()

    assert main(["daily", "run", str(wav)], client=_api(h)) == 0

    out = capsys.readouterr().out
    cards = [line for line in out.splitlines() if line.startswith(CARD_PREFIXES)]
    assert len(cards) == 3, out
    assert "was already completed" not in out
    assert " completed at " in out

    clock.advance(timedelta(days=1))
    assert main(["plan"], client=_api(h)) == 0
    plan_out = capsys.readouterr().out
    assert plan_out, "the plan printed nothing"
    plan_lines = plan_out.splitlines()
    assert plan_lines[0].startswith("sounds: sound.sub.v.w (")


def test_daily_run_with_a_failed_scorer_still_finishes_the_day(
    make_harness: Callable[..., Harness],
    tmp_path: Path,
    capsys: Any,
) -> None:
    """A failed analysis is not the end of the day: the job error is printed, the sounds card
    says not scored, the other two cards are given, and the session completes. The exit code
    still reports the failure."""
    h = make_harness(start_runner=True, coach=_coach(), scorer=NoScorer())  # pyright: ignore[reportArgumentType]
    _speaker(h)
    wav = _record_wav(h, tmp_path)
    capsys.readouterr()

    assert main(["daily", "run", str(wav)], client=_api(h)) == 1

    lines = capsys.readouterr().out.splitlines()
    assert any("failed: score" in line for line in lines)
    assert "sounds: not scored today" in lines
    assert sum(line.startswith(("on_the_spot:", "articulate:")) for line in lines) == 2
    assert any(line.startswith("session ") and " completed at " in line for line in lines)
