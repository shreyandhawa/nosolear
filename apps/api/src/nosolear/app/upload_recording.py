"""Stores an uploaded recording for an attempt and queues its ANALYZE job."""

import contextlib
from dataclasses import dataclass

from nosolear.ports.audio import (
    AttemptReader,
    AudioStore,
    NewRecording,
    PendingUpload,
    RecordingStore,
    SessionAlreadyCompleted,
    UnknownAttempt,
)


@dataclass(frozen=True, slots=True)
class UploadResult:
    recording_id: str
    job_id: str
    duration_ms: int


def upload_recording(
    *,
    attempt_id: str,
    upload: PendingUpload,
    attempts: AttemptReader,
    recordings: RecordingStore,
    audio: AudioStore,
) -> UploadResult:
    """The caller aborts `upload` on any exception raised here; the stored file is removed on
    every failure after it was written."""
    if not attempts.exists(attempt_id):
        raise UnknownAttempt("No attempt has this id.")
    # A closed session is final: its snapshot and re-checks are already taken, so a late recording
    # would be analysed but never seen by them.
    if attempts.session_completed(attempt_id):
        raise SessionAlreadyCompleted("This session is already completed.")
    stored = upload.commit()
    try:
        recording, job = recordings.add_and_enqueue(
            NewRecording(attempt_id=attempt_id, stored=stored)
        )
    except BaseException:
        # the original error matters more than a file that could not be removed
        with contextlib.suppress(OSError):
            audio.delete(stored.path)
        raise
    return UploadResult(recording_id=recording.id, job_id=job.id, duration_ms=stored.duration_ms)
