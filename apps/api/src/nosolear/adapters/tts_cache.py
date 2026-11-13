"""The clip cache in front of the paid synthesizer (ARCHITECTURE.md sections 5.2 and 11).

A cached clip is found by its hash and served only when both its row and its file exist. A miss
synthesizes once per hash (a lock per hash), writes the WAV to a temporary file and moves it into
`tts/<hash>.wav`, so a reader never sees a partial file. The path is built from the hash alone,
never from the text, so no input can name a file outside `data_dir/tts`.
"""

import os
import tempfile
import threading
from pathlib import Path

from nosolear.adapters.azure_speech import wav_duration_ms
from nosolear.adapters.private_fs import FILE_MODE, ensure_private_dir
from nosolear.budget.compose import PortWrapper
from nosolear.domain.speech import SynthesizedClip
from nosolear.domain.ssml import tts_hash
from nosolear.ports.clock import Clock
from nosolear.ports.providers import SpeechSynthesizer
from nosolear.ports.stores import TtsCacheStore

TTS_DIR = "tts"

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(digest: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(digest, threading.Lock())


class CachedSynthesizer(PortWrapper[SpeechSynthesizer]):
    layer = "cache"

    def __init__(
        self,
        inner: SpeechSynthesizer,
        *,
        store: TtsCacheStore,
        data_dir: Path,
        voice: str,
        clock: Clock,
    ) -> None:
        super().__init__(inner)
        self._store = store
        self._data_dir = data_dir.resolve()
        self._voice = voice
        self._clock = clock

    def synthesize(self, text: str, *, rate_percent: int = 0) -> SynthesizedClip:
        digest = tts_hash(text, voice=self._voice, rate_percent=rate_percent)
        hit = self._hit(digest)
        if hit is not None:
            return hit
        with _lock_for(digest):
            hit = self._hit(digest)
            if hit is not None:
                return hit
            audio = self.inner.synthesize(text, rate_percent=rate_percent)
            duration_ms = wav_duration_ms(audio.wav)
            clip = SynthesizedClip(
                hash=digest,
                path=f"{TTS_DIR}/{digest}.wav",
                voice=audio.voice,
                rate_percent=rate_percent,
                word_timings=audio.word_timings,
                duration_ms=duration_ms,
            )
            self._write(digest, audio.wav)
            self._store.put(clip, text=text, created_at=self._clock.now())
            return clip

    def _hit(self, digest: str) -> SynthesizedClip | None:
        clip = self._store.get(digest)
        if clip is None or not self._target(digest).is_file():
            return None
        return clip

    def _target(self, digest: str) -> Path:
        target = (self._data_dir / TTS_DIR / f"{digest}.wav").resolve()
        if not target.is_relative_to(self._data_dir):
            raise ValueError("the clip path must stay inside the data directory")
        return target

    def _write(self, digest: str, wav: bytes) -> None:
        tts_dir = self._data_dir / TTS_DIR
        ensure_private_dir(tts_dir)
        fd, temp_name = tempfile.mkstemp(dir=tts_dir, prefix=".clip-", suffix=".tmp")
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(wav)
            os.chmod(temp, FILE_MODE)
            os.replace(temp, self._target(digest))
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
