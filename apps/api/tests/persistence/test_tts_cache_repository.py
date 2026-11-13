from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError

from nosolear.domain.speech import SynthesizedClip, WordTiming
from nosolear.persistence.models import tts_cache
from nosolear.persistence.tts_cache import TtsCacheRepository

HASH = "ab" * 32
T0 = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


def clip(path: str | None = None) -> SynthesizedClip:
    return SynthesizedClip(
        hash=HASH,
        path=path if path is not None else f"tts/{HASH}.wav",
        voice="en-US-JennyNeural",
        rate_percent=-25,
        word_timings=(WordTiming("hello", 0, 400), WordTiming("world", 500, 900)),
        duration_ms=1234,
    )


def row_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(tts_cache)).scalar_one()


def test_round_trip(db_engine):
    repo = TtsCacheRepository(db_engine)
    assert repo.get(HASH) is None
    repo.put(clip(), text="hello world", created_at=T0)
    assert repo.get(HASH) == clip()


def test_a_second_put_for_the_same_hash_keeps_one_row(db_engine):
    repo = TtsCacheRepository(db_engine)
    repo.put(clip(), text="hello world", created_at=T0)
    repo.put(clip(), text="hello world", created_at=T0)
    assert row_count(db_engine) == 1


def test_a_path_that_is_not_the_clip_file_for_its_hash_is_refused(db_engine):
    with pytest.raises(IntegrityError):
        TtsCacheRepository(db_engine).put(
            clip(path="../../etc/passwd"), text="hello world", created_at=T0
        )
    assert row_count(db_engine) == 0
