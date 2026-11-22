"""`nosolear onboarding` prints the next step and its hint; `stand-in` refuses a closed session."""

from collections.abc import Callable

from baseline_fixtures import small_baseline_content
from harness import Harness

from nosolear.cli import main
from nosolear.cli_client import ApiClient
from nosolear.domain.onboarding import Component
from nosolear.domain.readiness import ReadinessReport, ReadinessRow, ReadinessStatus
from nosolear.settings import REPO_ROOT


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
            ReadinessStatus.MISSING
            if component is Component.AZURE_SPEECH
            else ReadinessStatus.READY,
            "reason",
            "set NOSOLEAR_AZURE_SPEECH_KEY in .env"
            if component is Component.AZURE_SPEECH
            else None,
        )
        for component in Component
    )
    h = make_harness(readiness=ReadinessReport(rows=rows))
    assert main(["onboarding"], client=_api(h)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Next: readiness",
        "  set NOSOLEAR_AZURE_SPEECH_KEY in .env",
    ]


def test_stand_in_refuses_a_closed_session_with_a_safe_message(
    make_harness: Callable[..., Harness], capsys
) -> None:
    h = make_harness(content=small_baseline_content())
    assert main(["stand-in", "baseline"], client=_api(h), synthesizer=h.synthesizer) == 2
    assert "No baseline exists yet." in capsys.readouterr().err


def test_stand_in_daily_answers_todays_attempt_and_completes_the_session(
    make_harness: Callable[..., Harness], capsys, monkeypatch
) -> None:
    h = make_harness()
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(h.data_dir))

    class DrainingApi(ApiClient):
        def follow_job(self, job_id, **kwargs):  # type: ignore[no-untyped-def]
            h.drain()  # no runner thread in the harness: run the queued job before polling
            return super().follow_job(job_id, **kwargs)

    api = DrainingApi(h.client)  # pyright: ignore[reportArgumentType]
    assert main(["stand-in", "daily"], client=api, synthesizer=h.synthesizer) == 0
    out = capsys.readouterr().out
    assert "prompt: " in out and "completed at" in out


def test_first_run_commands_build_their_own_client_from_the_settings(
    make_harness: Callable[..., Harness], tmp_path, monkeypatch, capsys
) -> None:
    """Only some parsers define `--base-url`; the rest must fall back to the settings, not crash."""
    h = make_harness(content=small_baseline_content())
    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o700)
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(data_dir))
    monkeypatch.setenv("NOSOLEAR_PORT", "8123")
    urls: list[str] = []

    def client(*, base_url: str, timeout: float) -> object:
        urls.append(base_url)
        return h.client

    monkeypatch.setattr("nosolear.cli.httpx.Client", client)
    assert main(["onboarding"]) == 0
    assert urls == ["http://127.0.0.1:8123"]
    assert capsys.readouterr().out.startswith("Next: calibration")


def test_stand_in_daily_refuses_the_real_data_dir(monkeypatch, capsys) -> None:
    """It would answer and complete today's real session with synthesized audio."""
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(REPO_ROOT / "data"))
    assert main(["stand-in", "daily"]) == 2
    assert "refusing to answer today's real session" in capsys.readouterr().err
