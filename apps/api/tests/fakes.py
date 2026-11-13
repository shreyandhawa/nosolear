"""In-memory fakes for the ports. Domain builders live in factories.py."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

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


class _FakeUpload:
    def __init__(self, store: FakeAudioStore) -> None:
        self._store = store
        self._chunks: list[bytes] = []
        self._size = 0
        self._finished = False

    def write(self, chunk: bytes) -> None:
        if self._finished:
            raise RuntimeError("The upload is already finished.")
        self._size += len(chunk)
        if self._size > self._store.limits.max_bytes:
            self.abort()
            raise InvalidAudio("too_large")
        self._chunks.append(chunk)

    def commit(self) -> StoredRecording:
        if self._finished:
            raise RuntimeError("The upload is already finished.")
        data = b"".join(self._chunks)
        self.abort()
        audio = parse_wav(data, self._store.limits)
        samples = to_16k(audio)
        if len(samples) == 0:
            raise InvalidAudio("empty")
        encoded = encode_wav(samples, TARGET_RATE)
        path = f"recordings/{uuid.uuid4()}.wav"
        self._store.files[path] = encoded
        return StoredRecording(
            path=path,
            duration_ms=duration_ms(len(samples), TARGET_RATE),
            sample_rate=TARGET_RATE,
            sha256=hashlib.sha256(encoded).hexdigest(),
        )

    def abort(self) -> None:
        self._finished = True
        self._chunks = []


class FakeAudioStore:
    def __init__(self, limits: AudioLimits = DEFAULT_LIMITS) -> None:
        self.limits = limits
        self.files: dict[str, bytes] = {}

    def begin_upload(self) -> PendingUpload:
        return _FakeUpload(self)

    def read(self, path: str) -> bytes:
        self.resolve(path)
        return self.files[path]

    def resolve(self, path: str) -> Path:
        if not is_recording_path(path):
            raise ValueError("Not a stored recording path.")
        return Path("/fake-audio-store") / path

    def delete(self, path: str) -> None:
        self.resolve(path)
        self.files.pop(path, None)
