"""The first run on real TTS audio: calibration, then baseline, through the CLI, with the real
adapters and the user's ledger. Live: excluded by default and run with `make test-live`."""

from collections.abc import Callable
from typing import Any

import pytest
from baseline_fixtures import small_baseline_content
from live_support import LiveHarness, require_keys
from sqlalchemy import select

from nosolear.cli import main
from nosolear.cli_client import ApiClient
from nosolear.persistence.models import profile_snapshots
from nosolear.settings import Settings


@pytest.mark.live
def test_first_run_on_tts_audio(
    live_settings: Settings,
    make_live_harness: Callable[..., LiveHarness],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_keys(live_settings, "azure")
    require_keys(live_settings, "anthropic")
    h = make_live_harness(content=small_baseline_content())
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(live_settings.data_dir))

    def cli(*argv: str) -> int:
        # TestClient is an httpx client at runtime; the stub is typed narrower than it is.
        client: Any = ApiClient(h.client)  # pyright: ignore[reportArgumentType]
        return main(list(argv), client=client, synthesizer=h.synthesizer)

    assert cli("calibrate", "start") == 0
    assert cli("stand-in", "calibration") == 0
    assert cli("calibrate", "finish") == 0
    assert cli("baseline", "start") == 0
    assert cli("stand-in", "baseline") == 0
    assert cli("baseline", "complete") == 0

    report: dict[str, Any] = h.client.get("/api/baseline/report").json()
    assert report["skill_scores"], "the baseline report carries skill scores"
    with h.engine.connect() as conn:
        assert conn.execute(select(profile_snapshots.c.id)).first() is not None
