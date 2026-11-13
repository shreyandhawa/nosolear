"""`nosolear rescore` posts the job and follows it to the end."""

from collections.abc import Callable

from harness import Harness

from nosolear.cli import main
from nosolear.cli_client import ApiClient


def test_cli_rescore_follows_job(make_harness: Callable[..., Harness], capsys) -> None:
    h = make_harness(start_runner=True)
    # TestClient is an httpx client at runtime; the stub is typed narrower than it is.
    api = ApiClient(h.client)  # pyright: ignore[reportArgumentType]
    assert main(["rescore"], client=api) == 0
    assert "Re-scoring done: job " in capsys.readouterr().out
