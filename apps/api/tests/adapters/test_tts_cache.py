"""The clip cache over a fake synthesizer and the real repository, in a temporary data dir."""

import os
import re
import stat
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from factories import FixedClock
from provider_fakes import FakeSpeechSynthesizer
from sqlalchemy import Engine
from wavs import make_wav

from nosolear.adapters.tts_cache import CachedSynthesizer
from nosolear.domain.speech import SynthesizedAudio
from nosolear.domain.ssml import tts_hash
from nosolear.persistence.tts_cache import TtsCacheRepository

JENNY = "en-US-JennyNeural"
T0 = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
HEX_PATH = re.compile(r"tts/[0-9a-f]{64}\.wav")


def audio() -> SynthesizedAudio:
    return SynthesizedAudio(
        wav=make_wav(1.0, freq=None), word_timings=(), voice=JENNY, billed_chars=9
    )


def cache_over(inner, engine: Engine, data_dir: Path) -> CachedSynthesizer:
    return CachedSynthesizer(
        inner,
        store=TtsCacheRepository(engine),
        data_dir=data_dir,
        voice=JENNY,
        clock=FixedClock(T0),
    )


def test_miss_writes_owner_only_clip_and_row(db_engine, tmp_path):
    inner = FakeSpeechSynthesizer(results=[audio()])
    clip = cache_over(inner, db_engine, tmp_path).synthesize("vest", rate_percent=0)
    digest = tts_hash("vest", voice=JENNY, rate_percent=0)
    target = tmp_path / "tts" / f"{digest}.wav"
    assert clip.path == f"tts/{digest}.wav"
    assert target.is_file()
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(tmp_path / "tts").st_mode) == 0o700
    assert TtsCacheRepository(db_engine).get(digest) == clip


def test_hit_does_not_call_inner(db_engine, tmp_path):
    inner = FakeSpeechSynthesizer(results=[audio()])
    cached = cache_over(inner, db_engine, tmp_path)
    first = cached.synthesize("vest", rate_percent=0)
    second = cached.synthesize("vest", rate_percent=0)
    assert second == first
    assert len(inner.calls) == 1


def test_missing_clip_file_is_regenerated(db_engine, tmp_path):
    inner = FakeSpeechSynthesizer(results=[audio()])
    cached = cache_over(inner, db_engine, tmp_path)
    clip = cached.synthesize("vest", rate_percent=0)
    (tmp_path / clip.path).unlink()
    cached.synthesize("vest", rate_percent=0)
    assert len(inner.calls) == 2
    assert (tmp_path / clip.path).is_file()


def test_concurrent_same_text_synthesizes_once(db_engine, tmp_path):
    class SlowSynthesizer(FakeSpeechSynthesizer):
        def synthesize(self, text, *, rate_percent):
            time.sleep(0.05)
            return super().synthesize(text, rate_percent=rate_percent)

    inner = SlowSynthesizer(results=[audio()])
    cached = cache_over(inner, db_engine, tmp_path)
    threads = [
        threading.Thread(target=cached.synthesize, args=("vest",), kwargs={"rate_percent": 0})
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(inner.calls) == 1


def test_text_never_shapes_the_path(db_engine, tmp_path):
    inner = FakeSpeechSynthesizer(results=[audio()])
    clip = cache_over(inner, db_engine, tmp_path).synthesize("../../etc/passwd", rate_percent=0)
    assert HEX_PATH.fullmatch(clip.path)
    assert (tmp_path / clip.path).resolve().is_relative_to(tmp_path.resolve())
