from collections.abc import Callable
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any, TextIO, cast

import httpx
import pytest
from factories import FixedClock, loopback_client, make_settings
from fakes import FakeStep
from sqlalchemy import Engine
from wavs import make_wav

from nosolear.api.app import create_app
from nosolear.app.steps import StepRegistry
from nosolear.cli import main
from nosolear.cli_client import GENERIC_ERROR, ApiClient, CliError, CliTimeout
from nosolear.domain.jobs import JobKind
from nosolear.persistence.repositories import AttemptRepository

ATTEMPT = "attempt-1"
JOB = "job-1"
BASE = "http://127.0.0.1:8000"
NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
STEP_NAMES = ("score", "transcribe", "probe", "coach", "extract")

Handler = Callable[[httpx.Request], httpx.Response]


def _transport(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url=BASE, transport=httpx.MockTransport(handler))


def _client(handler: Handler) -> ApiClient:
    return ApiClient(_transport(handler))


def _job(status: str, states: dict[str, str], progress: float) -> dict[str, Any]:
    return {
        "id": JOB,
        "kind": "analyze",
        "attempt_id": ATTEMPT,
        "status": status,
        "step": None,
        "progress": progress,
        "tries": 1,
        "steps": [
            {
                "name": name,
                "state": states.get(name, "pending"),
                "error_code": None,
                "message": None,
            }
            for name in STEP_NAMES
        ],
    }


class _NoSleep(ApiClient):
    """The real client with the wait between polls skipped; the timeout is counted in sleeps."""

    def follow_job(
        self,
        job_id: str,
        *,
        out: TextIO | None = None,
        sleep: Callable[[float], None] | None = None,
        timeout_s: float = 600.0,
        interval_s: float = 0.5,
    ) -> dict[str, Any]:
        return super().follow_job(
            job_id, out=out, sleep=lambda _: None, timeout_s=timeout_s, interval_s=interval_s
        )


def test_upload_wav_posts_audio_wav_body(tmp_path: Path) -> None:
    wav = tmp_path / "take.wav"
    wav.write_bytes(make_wav(0.5))
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(
            method=request.method,
            path=request.url.path,
            content_type=request.headers["content-type"],
            length=request.headers["content-length"],
            body=request.read(),
        )
        return httpx.Response(202, json={"recording_id": "r", "job_id": JOB, "duration_ms": 500})

    assert _client(handler).upload_wav(ATTEMPT, wav) == JOB
    assert seen["method"] == "POST"
    assert seen["path"] == f"/api/attempts/{ATTEMPT}/recording"
    assert seen["content_type"] == "audio/wav"
    assert seen["length"] == str(wav.stat().st_size)
    assert seen["body"] == wav.read_bytes()


def test_upload_error_surfaces_error_body_only(tmp_path: Path) -> None:
    wav = tmp_path / "take.wav"
    wav.write_bytes(make_wav(0.5))

    def too_large(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            413, json={"code": "invalid_audio", "message": "The recording is too large."}
        )

    def server_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Traceback: sk-planted-text inside the server")

    with pytest.raises(CliError) as too_large_info:
        _client(too_large).upload_wav(ATTEMPT, wav)
    assert str(too_large_info.value) == "The recording is too large."

    with pytest.raises(CliError) as server_info:
        _client(server_error).upload_wav(ATTEMPT, wav)
    assert str(server_info.value) == GENERIC_ERROR
    assert "sk-planted" not in str(server_info.value)


def test_unreachable_api_gives_a_generic_message() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(CliError) as info:
        _client(refuse).get_job(JOB)
    assert "127.0.0.1" not in str(info.value)
    assert "nosolear serve" in str(info.value)


def test_follow_job_prints_progress_and_returns_the_final_body() -> None:
    bodies = iter(
        [
            _job("running", {"score": "running"}, 0.0),
            _job("running", {"score": "done", "transcribe": "running"}, 0.2),
            _job("running", {"score": "done", "transcribe": "running"}, 0.2),
            _job("running", {"score": "done", "transcribe": "done", "coach": "running"}, 0.6),
            _job("done", {name: "done" for name in STEP_NAMES}, 1.0),
        ]
    )
    sleeps: list[float] = []
    out = StringIO()
    client = _client(lambda request: httpx.Response(200, json=next(bodies)))

    final = client.follow_job(JOB, out=out, sleep=sleeps.append, interval_s=0.5)

    assert final["status"] == "done"
    assert out.getvalue().splitlines() == [
        "score        running   0%",
        "score        done     20%",
        "transcribe   running  20%",
        "transcribe   done     60%",
        "coach        running  60%",
        "probe        done     100%",
        "coach        done     100%",
        "extract      done     100%",
    ]
    assert sleeps == [0.5, 0.5, 0.5, 0.5]


def test_follow_job_times_out() -> None:
    client = _client(lambda request: httpx.Response(200, json=_job("running", {}, 0.0)))
    with pytest.raises(CliTimeout):
        client.follow_job(JOB, sleep=lambda _: None, timeout_s=2.0, interval_s=0.5)


def test_main_job_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    done = _client(lambda request: httpx.Response(200, json=_job("done", {}, 1.0)))
    assert main(["job", JOB, "--follow"], client=done) == 0
    assert f"job {JOB} done" in capsys.readouterr().out

    failed_body = _job("failed", {"coach": "failed"}, 0.8)
    failed_body["steps"][3]["error_code"] = "provider_unavailable"
    failed_body["steps"][3]["message"] = "The provider is unavailable."
    failed = _client(lambda request: httpx.Response(200, json=failed_body))
    assert main(["job", JOB, "--follow"], client=failed) == 1
    assert (
        f"job {JOB} failed: coach: provider_unavailable (The provider is unavailable.)"
        in capsys.readouterr().out
    )

    running = _NoSleep(
        _transport(lambda request: httpx.Response(200, json=_job("running", {}, 0.0)))
    )
    assert main(["job", JOB, "--follow"], client=running) == 3


def test_main_upload_refuses_new_attempt_on_real_data_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wav = tmp_path / "take.wav"
    wav.write_bytes(make_wav(0.5))
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    assert main(["upload", str(wav), "--new-attempt"], client=_client(handler)) == 2
    assert "refusing" in capsys.readouterr().err
    assert calls == []


def test_main_upload_missing_file_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client = _client(lambda request: httpx.Response(500))
    assert main(["upload", str(tmp_path / "nope.wav"), "--attempt-id", ATTEMPT], client=client) == 2
    assert "cannot read" in capsys.readouterr().err


def test_job_command_resume_posts_resume() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json=_job("queued", {}, 0.0))

    assert main(["job", JOB, "--resume"], client=_client(handler)) == 0
    assert seen == [("POST", f"/api/jobs/{JOB}/resume"), ("GET", f"/api/jobs/{JOB}")]


def test_upload_no_follow_prints_job_and_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wav = tmp_path / "take.wav"
    wav.write_bytes(make_wav(0.5))
    accepted = {"recording_id": "r", "job_id": JOB, "duration_ms": 500}
    client = _client(lambda request: httpx.Response(202, json=accepted))
    assert main(["upload", str(wav), "--attempt-id", ATTEMPT, "--no-follow"], client=client) == 0
    assert JOB in capsys.readouterr().out


def test_cli_upload_end_to_end_with_fake_steps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = StepRegistry()
    for name in STEP_NAMES:
        registry.register(JobKind.ANALYZE, FakeStep(name))
    app = create_app(
        make_settings(data_dir=tmp_path), step_registry=registry, clock=FixedClock(NOW)
    )
    wav = tmp_path / "take.wav"
    wav.write_bytes(make_wav(1.0, rate=48000))
    with loopback_client(app) as http:
        engine = cast(Engine, app.state.engine)
        attempt_id = AttemptRepository(engine).create_attempt(
            session_kind="daily", step="speak", reference_text=None, scripted=False, now=NOW
        )
        code = main(
            ["upload", str(wav), "--attempt-id", attempt_id],
            client=ApiClient(cast(httpx.Client, http)),
        )
    lines = capsys.readouterr().out.splitlines()
    assert code == 0
    assert lines[-1].startswith("job ") and lines[-1].endswith(" done")


def test_upload_to_unknown_attempt_prints_the_api_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wav = tmp_path / "take.wav"
    wav.write_bytes(make_wav(0.5))
    unknown = {"code": "unknown_attempt", "message": "No attempt has this id."}
    client = _client(lambda request: httpx.Response(404, json=unknown))
    assert main(["upload", str(wav), "--attempt-id", "nope"], client=client) == 2
    assert "upload failed: No attempt has this id." in capsys.readouterr().err


def test_upload_new_attempt_creates_the_attempt_in_the_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NOSOLEAR_DATA_DIR", str(tmp_path))
    app = create_app(make_settings(data_dir=tmp_path), start_runner=False, clock=FixedClock(NOW))
    wav = tmp_path / "take.wav"
    wav.write_bytes(make_wav(0.5))
    with loopback_client(app) as http:
        code = main(
            ["upload", str(wav), "--new-attempt", "--no-follow"],
            client=ApiClient(cast(httpx.Client, http)),
        )
        engine = cast(Engine, app.state.engine)
        first_line = capsys.readouterr().out.splitlines()[0]
        attempt_id = first_line.removeprefix("attempt ")
        assert AttemptRepository(engine).exists(attempt_id)
    assert code == 0


@pytest.mark.parametrize(
    "body",
    [
        {"status": "running"},
        {"status": 5, "progress": 0.1, "steps": []},
        {"status": "running", "progress": "high", "steps": []},
        {"status": "running", "progress": 0.1, "steps": ["x"]},
        {"status": "running", "progress": 0.1, "steps": [{"name": "score"}]},
        {
            "status": "failed",
            "progress": 1.0,
            "steps": [{"name": "a", "state": "failed", "error_code": 7, "message": "secret"}],
        },
        ["not", "a", "job"],
    ],
)
def test_a_2xx_body_that_is_not_a_job_gives_the_generic_message(
    body: object, capsys: pytest.CaptureFixture[str]
) -> None:
    client = _client(lambda request: httpx.Response(200, json=body))
    with pytest.raises(CliError) as info:
        client.get_job(JOB)
    assert str(info.value) == GENERIC_ERROR
    with pytest.raises(CliError) as info:
        client.follow_job(JOB, sleep=lambda _: None)
    assert str(info.value) == GENERIC_ERROR

    assert main(["job", JOB], client=client) == 2
    assert main(["job", JOB, "--follow"], client=client) == 2
    captured = capsys.readouterr()
    assert GENERIC_ERROR in captured.err
    assert "secret" not in captured.out + captured.err


def test_follow_prints_a_skipped_steps_reason() -> None:
    body = _job("done", {name: "done" for name in STEP_NAMES}, 1.0)
    body["steps"][2]["state"] = "skipped"
    body["steps"][2]["message"] = "not_available"
    out = StringIO()
    _client(lambda request: httpx.Response(200, json=body)).follow_job(JOB, out=out)
    assert "probe        skipped  100% (not_available)" in out.getvalue().splitlines()
