import re
import struct
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx
import pytest
from factories import FixedClock, loopback_client, make_settings
from fakes import FakeStep
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from wavs import make_wav, raw_wav

from nosolear.adapters.filesystem_audio_store import FilesystemAudioStore
from nosolear.api.app import create_app
from nosolear.api.deps import Services
from nosolear.app.steps import StepRegistry
from nosolear.domain.audio import parse_wav
from nosolear.domain.jobs import JobKind
from nosolear.persistence.repositories import AttemptRepository, RecordingRepository
from nosolear.ports.audio import PendingUpload

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
STEPS = ("score", "transcribe", "probe", "coach", "extract")
RECORDING_NAME = re.compile(r"^recordings/[0-9a-f-]{36}\.wav$")
TOO_LARGE_BYTES = 10 * 1024 * 1024
URL = "/api/attempts/{}/recording"


def _app(tmp_path: Path) -> FastAPI:
    registry = StepRegistry()
    for name in STEPS:
        registry.register(JobKind.ANALYZE, FakeStep(name))
    return create_app(
        make_settings(data_dir=tmp_path),
        step_registry=registry,
        start_runner=False,
        clock=FixedClock(NOW),
    )


def _engine(client: TestClient) -> Engine:
    return cast(Engine, client.app.state.engine)  # pyright: ignore[reportAttributeAccessIssue]


def _attempt(
    client: TestClient, *, reference_text: str | None = None, scripted: bool = False
) -> str:
    return AttemptRepository(_engine(client)).create_attempt(
        session_kind="daily",
        step="speak",
        reference_text=reference_text,
        scripted=scripted,
        now=NOW,
    )


def _wav_post(
    client: TestClient, attempt_id: str, body: bytes | Iterator[bytes], **headers: str
) -> httpx.Response:
    merged = {"Content-Type": "audio/wav", **headers}
    return client.post(URL.format(attempt_id), content=body, headers=merged)


def _chunked(data: bytes, size: int = 1024 * 1024) -> Iterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


def _store_is_clean(tmp_path: Path) -> None:
    store = tmp_path / "recordings"
    assert not list(store.glob("*.wav"))
    assert list((store / ".incoming").iterdir()) == []


def test_upload_happy_path_end_to_end(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with loopback_client(app) as client:
        attempt_id = _attempt(client)
        response = _wav_post(client, attempt_id, make_wav(1.0, rate=48000))
        assert response.status_code == 202
        body = response.json()
        assert body["duration_ms"] == 1000
        stored = RecordingRepository(_engine(client), FixedClock(NOW)).for_attempt(attempt_id)
        assert stored is not None
        assert RECORDING_NAME.match(stored.path)
        audio = parse_wav((tmp_path / stored.path).read_bytes())
        assert audio.sample_rate == 16000
        cast(Services, app.state.services).runner.run_pending()
        job = client.get(f"/api/jobs/{body['job_id']}").json()
    assert job["status"] == "done"
    assert job["kind"] == "analyze"


def test_attempt_reader_get_returns_step_and_reference(tmp_path: Path) -> None:
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client, reference_text="hello there", scripted=True)
        reader = AttemptRepository(_engine(client))
        info = reader.get(attempt_id)
        assert info is not None
        assert (info.id, info.step, info.reference_text, info.scripted) == (
            attempt_id,
            "speak",
            "hello there",
            True,
        )
        assert info.session_id
        assert reader.get("nope") is None
        assert reader.exists(attempt_id) and not reader.exists("nope")


def test_rejects_non_wav_content_types(tmp_path: Path) -> None:
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        wav = make_wav(0.5)
        multipart = client.post(
            URL.format(attempt_id),
            content=wav,
            headers={"Content-Type": "multipart/form-data; boundary=x"},
        )
        octet = _wav_post(client, attempt_id, wav, **{"Content-Type": "application/octet-stream"})
        missing = client.post(URL.format(attempt_id), content=wav)
    for response in (multipart, octet, missing):
        assert response.status_code == 415
    _store_is_clean(tmp_path)


def test_content_type_parameters_and_case_are_ignored(tmp_path: Path) -> None:
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        response = _wav_post(
            client, attempt_id, make_wav(0.5), **{"Content-Type": "Audio/WAV; rate=16000"}
        )
    assert response.status_code == 202


def test_unknown_attempt_is_404_and_writes_nothing(tmp_path: Path) -> None:
    with loopback_client(_app(tmp_path)) as client:
        response = _wav_post(client, "nope", make_wav(0.5))
    assert response.status_code == 404
    assert response.json() == {
        "code": "unknown_attempt",
        "message": "No attempt has this id.",
    }
    _store_is_clean(tmp_path)


def test_oversize_content_length_is_413_up_front(tmp_path: Path) -> None:
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        response = _wav_post(
            client, attempt_id, b"RIFF", **{"Content-Length": str(TOO_LARGE_BYTES + 1)}
        )
    assert response.status_code == 413
    _store_is_clean(tmp_path)


def test_lying_content_length_is_capped_while_streaming(tmp_path: Path) -> None:
    body = make_wav(1.0)
    big = b"\x00" * (TOO_LARGE_BYTES + 1024 * 1024)
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        lying = _wav_post(client, attempt_id, _chunked(big), **{"Content-Length": "100"})
        chunked = client.post(
            URL.format(attempt_id),
            content=_chunked(big),
            headers={"Content-Type": "audio/wav"},
        )
        malformed = _wav_post(client, attempt_id, body, **{"Content-Length": "abc"})
    assert lying.status_code == 413
    assert chunked.status_code == 413
    assert malformed.status_code == 400
    _store_is_clean(tmp_path)


def test_rate_zero_header_is_400_not_500(tmp_path: Path) -> None:
    pcm = b"\x00\x00" * 1600
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        responses = [
            _wav_post(client, attempt_id, raw_wav(rate=rate, pcm=pcm)) for rate in (0, 8000, 96000)
        ]
    for response in responses:
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_audio"
    _store_is_clean(tmp_path)


def test_malformed_wavs_are_400(tmp_path: Path) -> None:
    pcm = b"\x00\x00" * 16000
    data_chunk = b"data" + struct.pack("<I", 4) + b"\x00\x00\x00\x00"
    bad = {
        "stereo": raw_wav(rate=16000, pcm=pcm, channels=2),
        "8-bit": raw_wav(rate=16000, pcm=pcm, bits=8),
        "float": raw_wav(rate=16000, pcm=pcm, fmt_tag=3),
        "two data chunks": raw_wav(rate=16000, pcm=pcm, extra_chunks=data_chunk),
        "truncated header": b"RIFF\x00\x00\x00\x00WAVEfm ",
        "zero frames": raw_wav(rate=16000, pcm=b""),
        "121 seconds": make_wav(121.0, rate=16000),
    }
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        statuses = {name: _wav_post(client, attempt_id, body) for name, body in bad.items()}
    for name, response in statuses.items():
        assert response.status_code == 400, name
    _store_is_clean(tmp_path)


def test_truncated_body_with_big_declared_length_uses_received_frames(tmp_path: Path) -> None:
    pcm = b"\x01\x00" * 16000 * 2
    declared = 100 * 16000 * 2
    body = raw_wav(rate=16000, pcm=pcm, declared_data=declared)
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        response = _wav_post(client, attempt_id, body)
    assert response.status_code == 202
    assert response.json()["duration_ms"] == 2000


def test_client_filename_and_query_are_ignored(tmp_path: Path) -> None:
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        response = client.post(
            URL.format(attempt_id) + "?path=../../escape&filename=../../escape",
            content=make_wav(0.5),
            headers={
                "Content-Type": "audio/wav",
                "Content-Disposition": 'attachment; filename="../../escape.wav"',
            },
        )
        stored = RecordingRepository(_engine(client), FixedClock(NOW)).for_attempt(attempt_id)
    assert response.status_code == 202
    assert stored is not None
    assert RECORDING_NAME.match(stored.path)
    assert (tmp_path / stored.path).is_file()
    assert not (tmp_path.parent / "escape.wav").exists()
    assert not (tmp_path / "escape.wav").exists()


def test_second_upload_is_409(tmp_path: Path) -> None:
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        first = _wav_post(client, attempt_id, make_wav(0.5))
        second = _wav_post(client, attempt_id, make_wav(1.0))
        stored = RecordingRepository(_engine(client), FixedClock(NOW)).for_attempt(attempt_id)
    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json() == {
        "code": "recording_exists",
        "message": "This attempt already has a recording.",
    }
    assert stored is not None
    assert len(list((tmp_path / "recordings").glob("*.wav"))) == 1


def test_upload_error_bodies_contain_no_internals(tmp_path: Path) -> None:
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        responses = [
            client.post(
                URL.format(attempt_id), content=b"x", headers={"Content-Type": "text/plain"}
            ),
            _wav_post(client, attempt_id, b"not a wav at all"),
            _wav_post(client, "nope", make_wav(0.5)),
        ]
    for response in responses:
        assert set(response.json()) == {"code", "message"}
        assert str(tmp_path) not in response.text


def test_openapi_describes_audio_wav_body(tmp_path: Path) -> None:
    operation = _app(tmp_path).openapi()["paths"][URL.format("{attempt_id}")]["post"]
    assert operation["operationId"] == "uploadRecording"
    assert "audio/wav" in operation["requestBody"]["content"]
    assert "202" in operation["responses"]


def test_second_upload_is_rejected_before_any_body_is_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with loopback_client(_app(tmp_path)) as client:
        attempt_id = _attempt(client)
        assert _wav_post(client, attempt_id, make_wav(0.5)).status_code == 202
        begun: list[object] = []
        original = FilesystemAudioStore.begin_upload

        def counting(self: FilesystemAudioStore) -> PendingUpload:
            begun.append(self)
            return original(self)

        monkeypatch.setattr(FilesystemAudioStore, "begin_upload", counting)
        second = _wav_post(client, attempt_id, make_wav(1.0))
    assert second.status_code == 409
    assert begun == []
