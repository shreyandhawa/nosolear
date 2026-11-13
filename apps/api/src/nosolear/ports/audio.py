"""The audio storage port: untrusted upload bytes in, a validated 16 kHz recording out."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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
