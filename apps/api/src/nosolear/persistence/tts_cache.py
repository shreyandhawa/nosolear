"""SQLAlchemy adapter for the TTS clip cache (`TtsCacheStore`)."""

import json
from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nosolear.domain.speech import SynthesizedClip, WordTiming
from nosolear.persistence.models import tts_cache


class TtsCacheRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, hash: str) -> SynthesizedClip | None:
        stmt = select(tts_cache).where(tts_cache.c.hash == hash)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).one_or_none()
        if row is None:
            return None
        stored = json.loads(row.word_timings_json)
        return SynthesizedClip(
            hash=row.hash,
            path=row.path,
            voice=row.voice,
            rate_percent=row.rate,
            word_timings=tuple(
                WordTiming(text=word, start_ms=start, end_ms=end)
                for word, start, end in stored["words"]
            ),
            duration_ms=stored["duration_ms"],
        )

    def put(self, clip: SynthesizedClip, *, text: str, created_at: datetime) -> None:
        """One row per hash. A later put for the same hash replaces the row, so a regenerated file
        keeps the voice and timings that match it. A path that is not `tts/<hash>.wav` is refused by
        the table's CHECK constraint, which still raises."""
        stored = {
            "duration_ms": clip.duration_ms,
            "words": [[w.text, w.start_ms, w.end_ms] for w in clip.word_timings],
        }
        values = {
            "hash": clip.hash,
            "text": text,
            "voice": clip.voice,
            "rate": clip.rate_percent,
            "path": clip.path,
            "word_timings_json": json.dumps(stored, ensure_ascii=False, separators=(",", ":")),
            "created_at": created_at,
        }
        stmt = (
            sqlite_insert(tts_cache)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["hash"],
                set_={key: value for key, value in values.items() if key != "hash"},
            )
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
