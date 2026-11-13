"""Recordings on the local disk, under the data dir only."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from nosolear.adapters.private_fs import FILE_MODE, ensure_private_dir
from nosolear.domain.audio import (
    DEFAULT_LIMITS,
    TARGET_RATE,
    AudioLimits,
    duration_ms,
    encode_wav,
    parse_wav,
    to_16k,
)
from nosolear.domain.errors import InvalidAudio
from nosolear.ports.audio import PendingUpload, StoredRecording, is_recording_path


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


class _FilesystemUpload:
    def __init__(self, store: FilesystemAudioStore) -> None:
        self._store = store
        self._temp = store.incoming_dir / f"{uuid.uuid4()}.part"
        self._fd: int | None = os.open(self._temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        self._size = 0

    def write(self, chunk: bytes) -> None:
        if self._fd is None:
            raise RuntimeError("The upload is already finished.")
        self._size += len(chunk)
        if self._size > self._store.limits.max_bytes:
            self.abort()
            raise InvalidAudio("too_large")
        try:
            _write_all(self._fd, chunk)
        except BaseException:
            self.abort()
            raise

    def commit(self) -> StoredRecording:
        if self._fd is None:
            raise RuntimeError("The upload is already finished.")
        try:
            os.close(self._fd)
            self._fd = None
            data = self._temp.read_bytes()
            return self._store.store(data)
        finally:
            self.abort()

    def abort(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self._temp.unlink(missing_ok=True)


class FilesystemAudioStore:
    def __init__(self, data_dir: Path, *, limits: AudioLimits = DEFAULT_LIMITS) -> None:
        self.limits = limits
        self._data_dir = data_dir
        self._recordings = data_dir / "recordings"
        self.incoming_dir = self._recordings / ".incoming"
        ensure_private_dir(self._recordings)
        ensure_private_dir(self.incoming_dir)
        for stale in self.incoming_dir.iterdir():
            if stale.is_file() or stale.is_symlink():
                stale.unlink(missing_ok=True)

    def begin_upload(self) -> PendingUpload:
        return _FilesystemUpload(self)

    def store(self, data: bytes) -> StoredRecording:
        audio = parse_wav(data, self.limits)
        samples = to_16k(audio)
        if len(samples) == 0:
            raise InvalidAudio("empty")
        encoded = encode_wav(samples, TARGET_RATE)
        relative = f"recordings/{uuid.uuid4()}.wav"
        target = self._data_dir / relative
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        try:
            try:
                _write_all(fd, encoded)
            finally:
                os.close(fd)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return StoredRecording(
            path=relative,
            duration_ms=duration_ms(len(samples), TARGET_RATE),
            sample_rate=TARGET_RATE,
            sha256=hashlib.sha256(encoded).hexdigest(),
        )

    def resolve(self, path: str) -> Path:
        if not is_recording_path(path):
            raise ValueError("Not a stored recording path.")
        resolved = (self._data_dir / path).resolve()
        if not resolved.is_relative_to(self._recordings.resolve()) or (
            resolved.parent != self._recordings.resolve()
        ):
            raise ValueError("Not a stored recording path.")
        return resolved

    def read(self, path: str) -> bytes:
        return self.resolve(path).read_bytes()

    def delete(self, path: str) -> None:
        self.resolve(path).unlink(missing_ok=True)
