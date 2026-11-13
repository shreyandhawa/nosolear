"""The audio storage port: untrusted upload bytes in, a validated 16 kHz recording out."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nosolear.domain.jobs import Job

RECORDING_PATH_PATTERN = re.compile(r"^recordings/[0-9a-f-]{36}\.wav$")


def is_recording_path(path: str) -> bool:
    return RECORDING_PATH_PATTERN.fullmatch(path) is not None


@dataclass(frozen=True, slots=True)
class StoredRecording:
    path: str  # always "recordings/<uuid>.wav", relative to the data dir
    duration_ms: int
    sample_rate: int  # always 16000
    sha256: str  # hex digest of the stored file


@dataclass(frozen=True, slots=True)
class Recording:
    """A row of the recordings table."""

    id: str
    attempt_id: str
    path: str
    duration_ms: int
    sample_rate: int
    sha256: str


class PendingUpload(Protocol):
    """One upload in progress. After `commit` or `abort` (or a failed `write`) it is finished:
    `abort` stays a no-op, while `write` and `commit` raise `RuntimeError` and store nothing."""

    def write(self, chunk: bytes) -> None:
        """Raises `InvalidAudio("too_large")` once the cap is passed; the upload is then aborted."""
        ...

    def commit(self) -> StoredRecording:
        """Validate, resample and store. Raises `InvalidAudio`. The temp file is always removed."""
        ...

    def abort(self) -> None: ...


class AudioStore(Protocol):
    def begin_upload(self) -> PendingUpload: ...

    def read(self, path: str) -> bytes: ...

    def resolve(self, path: str) -> Path:
        """Absolute path for libraries that need a file. Raises `ValueError` for anything that
        is not a stored recording path."""
        ...

    def delete(self, path: str) -> None: ...


@dataclass(frozen=True, slots=True)
class NewRecording:
    attempt_id: str
    stored: StoredRecording


@dataclass(frozen=True, slots=True)
class AttemptInfo:
    id: str
    session_id: str
    step: str
    reference_text: str | None
    scripted: bool


class RecordingExists(ValueError):
    """The attempt already has a recording (HTTP 409)."""


class UnknownAttempt(ValueError):
    """No attempt has this id (HTTP 404)."""


class SessionAlreadyCompleted(ValueError):
    """The attempt's session is closed, so it takes no recording (HTTP 409)."""


class AttemptReader(Protocol):
    def exists(self, attempt_id: str) -> bool: ...

    def session_completed(self, attempt_id: str) -> bool:
        """True when the attempt's session is closed. An unknown attempt is not completed."""
        ...

    def get(self, attempt_id: str) -> AttemptInfo | None:
        """The attempt's step, reference text and scripted flag (read by the analysis steps)."""
        ...


class RecordingStore(Protocol):
    def add_and_enqueue(self, new: NewRecording) -> tuple[Recording, Job]:
        """The recordings row and a queued ANALYZE job, in one transaction.

        Raises `RecordingExists` if the attempt already has a recording."""
        ...

    def for_attempt(self, attempt_id: str) -> Recording | None: ...
