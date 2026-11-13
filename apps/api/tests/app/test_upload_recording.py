import sqlite3
from datetime import UTC, datetime

import pytest
from factories import FixedClock
from fakes import FakeAttemptReader, FakeAudioStore, FakeJobQueue, FakeRecordingStore
from sqlalchemy.exc import OperationalError
from wavs import make_wav

from nosolear.app.upload_recording import upload_recording
from nosolear.domain.audio import parse_wav
from nosolear.domain.jobs import Job, JobKind, JobStatus
from nosolear.ports.audio import (
    AttemptInfo,
    NewRecording,
    Recording,
    RecordingExists,
    UnknownAttempt,
)

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
ATTEMPT = AttemptInfo(
    id="attempt-1", session_id="session-1", step="speak", reference_text=None, scripted=False
)


def _chunks(data: bytes, size: int = 4096) -> list[bytes]:
    return [data[i : i + size] for i in range(0, len(data), size)]


def _upload(audio: FakeAudioStore, data: bytes):
    pending = audio.begin_upload()
    for chunk in _chunks(data):
        pending.write(chunk)
    return pending


class _Setup:
    def __init__(self) -> None:
        clock = FixedClock(NOW)
        self.audio = FakeAudioStore()
        self.jobs = FakeJobQueue(clock)
        self.recordings = FakeRecordingStore(self.jobs)
        self.attempts = FakeAttemptReader([ATTEMPT])


def test_upload_stores_recording_and_queues_analyze_job() -> None:
    setup = _Setup()
    upload = _upload(setup.audio, make_wav(1.0, rate=48000))

    result = upload_recording(
        attempt_id="attempt-1",
        upload=upload,
        attempts=setup.attempts,
        recordings=setup.recordings,
        audio=setup.audio,
    )

    assert result.duration_ms == 1000
    recording = setup.recordings.for_attempt("attempt-1")
    assert recording is not None
    assert recording.id and recording.sample_rate == 16000
    assert recording.path in setup.audio.files
    assert parse_wav(setup.audio.files[recording.path]).sample_rate == 16000
    job = setup.jobs.get(result.job_id)
    assert job is not None
    assert job.kind is JobKind.ANALYZE
    assert job.status is JobStatus.QUEUED
    assert job.attempt_id == "attempt-1"


def test_unknown_attempt_raises_before_storing() -> None:
    setup = _Setup()
    upload = _upload(setup.audio, make_wav(1.0))

    with pytest.raises(UnknownAttempt):
        upload_recording(
            attempt_id="nope",
            upload=upload,
            attempts=setup.attempts,
            recordings=setup.recordings,
            audio=setup.audio,
        )
    assert setup.audio.files == {}


def test_second_upload_for_attempt_is_rejected_and_first_file_survives() -> None:
    setup = _Setup()
    first = upload_recording(
        attempt_id="attempt-1",
        upload=_upload(setup.audio, make_wav(1.0)),
        attempts=setup.attempts,
        recordings=setup.recordings,
        audio=setup.audio,
    )
    assert first.job_id
    stored = setup.recordings.for_attempt("attempt-1")
    assert stored is not None
    first_path = stored.path

    with pytest.raises(RecordingExists):
        upload_recording(
            attempt_id="attempt-1",
            upload=_upload(setup.audio, make_wav(2.0)),
            attempts=setup.attempts,
            recordings=setup.recordings,
            audio=setup.audio,
        )
    assert set(setup.audio.files) == {first_path}


class _FailingRecordings:
    def add_and_enqueue(self, new: NewRecording) -> tuple[Recording, Job]:
        raise OperationalError(
            "INSERT INTO recordings", {}, sqlite3.OperationalError("disk I/O error")
        )

    def for_attempt(self, attempt_id: str) -> Recording | None:
        return None


def test_database_failure_deletes_stored_file() -> None:
    setup = _Setup()
    with pytest.raises(OperationalError):
        upload_recording(
            attempt_id="attempt-1",
            upload=_upload(setup.audio, make_wav(1.0)),
            attempts=setup.attempts,
            recordings=_FailingRecordings(),
            audio=setup.audio,
        )
    assert setup.audio.files == {}
