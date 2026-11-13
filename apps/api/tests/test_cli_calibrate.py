"""`nosolear calibrate` talks to the API and prints what the session needs."""

from calibration_fixtures import small_content
from harness import Harness

from nosolear.cli import main
from nosolear.cli_client import ApiClient


def _api(h: Harness) -> ApiClient:
    return ApiClient(h.client)  # pyright: ignore[reportArgumentType]


def test_cli_calibrate_start_lists_tokens(make_harness, capsys):
    h = make_harness(content=small_content())
    assert main(["calibrate", "start"], client=_api(h)) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 30
    assert all("Say " in line for line in lines)


def test_cli_calibrate_skip(make_harness, capsys):
    h = make_harness(content=small_content())
    assert main(["calibrate", "skip"], client=_api(h)) == 0
    assert (
        "Calibration skipped. Scores stay provisional until you calibrate."
        in capsys.readouterr().out
    )
