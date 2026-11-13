"""`nosolear baseline start|status|complete|report`, through the API client."""

from collections.abc import Callable

from baseline_fixtures import small_baseline_content
from harness import Harness

from nosolear.cli import main
from nosolear.cli_client import ApiClient
from nosolear.domain.coach import Rubric


def _api(h: Harness) -> ApiClient:
    # TestClient is an httpx client at runtime; the stub is typed narrower than it is.
    return ApiClient(h.client)  # pyright: ignore[reportArgumentType]


def test_cli_baseline_runs_the_session_and_prints_the_report(
    make_harness: Callable[..., Harness], capsys
) -> None:
    h = make_harness(
        content=small_baseline_content(), rubric=Rubric(structure=3, clarity=3, concision=3)
    )
    h.voice.user_errors["v"] = "w"
    api = _api(h)

    assert main(["baseline", "start"], client=api) == 0
    started = capsys.readouterr().out.splitlines()
    assert len(started) == 6
    assert started[0].startswith("  0  ") and "read_aloud" in started[0]
    assert "Seven vans came." in started[0]

    assert main(["baseline", "status"], client=api) == 0
    assert "Recorded 0 of 6 baseline items." in capsys.readouterr().out

    assert main(["baseline", "complete"], client=api) == 2
    assert "Record every baseline item" in capsys.readouterr().err

    body = h.client.get("/api/baseline").json()
    for item in body["items"]:
        h.upload(item["attempt_id"], item["stand_in_text"])
    h.drain()

    assert main(["baseline", "complete"], client=api) == 0
    out = capsys.readouterr().out
    assert "1. /v/ said as /w/  " in out and "provisional" in out
    assert "sounds  " in out
    assert main(["baseline", "report"], client=api) == 0
    assert "1. /v/ said as /w/  " in capsys.readouterr().out
