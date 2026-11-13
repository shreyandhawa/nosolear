"""The content repository: seed sync, retirement, immutable ids and the startup sync."""

from datetime import UTC, datetime

import pytest
from factories import count
from harness import Harness
from sqlalchemy import Engine, select

from nosolear.adapters.content_files import load_pack, load_seed_content
from nosolear.domain.content import ContentItem, ContentKind, seed_items
from nosolear.persistence.content_repository import ContentRepository
from nosolear.persistence.models import content_items
from nosolear.ports.content_store import ContentConflict
from nosolear.settings import CONTENT_DIR

NOW = datetime(2026, 11, 13, tzinfo=UTC)
A = ContentItem("ba-ft-01", ContentKind.PROMPT, "Describe a place.", (), "seed")
B = ContentItem("ba-ar-01", ContentKind.PROMPT, "Give one point.", (), "seed")


def test_sync_inserts_then_retires(db_engine: Engine):
    repo = ContentRepository(db_engine)
    assert repo.sync_seed([A, B], now=NOW).added == 2
    summary = repo.sync_seed([A], now=NOW)
    assert (summary.added, summary.retired) == (0, 1)
    assert repo.get("ba-ar-01") == B, "a retired item is still readable by its id"


def test_sync_refuses_a_changed_text_for_an_existing_id(db_engine: Engine):
    repo = ContentRepository(db_engine)
    repo.sync_seed([A], now=NOW)
    changed = ContentItem("ba-ft-01", ContentKind.PROMPT, "Describe a city.", (), "seed")
    with pytest.raises(ContentConflict):
        repo.sync_seed([changed], now=NOW)
    assert repo.get("ba-ft-01") == A


def test_sync_refuses_changed_keys_for_an_existing_id(db_engine: Engine):
    repo = ContentRepository(db_engine)
    repo.sync_seed([A], now=NOW)
    changed = ContentItem("ba-ft-01", ContentKind.PROMPT, "Describe a place.", ("x",), "seed")
    with pytest.raises(ContentConflict):
        repo.sync_seed([changed], now=NOW)


def test_coach_rows_are_never_retired(db_engine: Engine):
    repo = ContentRepository(db_engine)
    coach = ContentItem("coach-1", ContentKind.DRILL_SENTENCE, "Say the word.", (), "coach")
    repo.sync_seed([coach], now=NOW)
    repo.sync_seed([], now=NOW)
    with db_engine.connect() as conn:
        retired = conn.execute(
            select(content_items.c.retired_at).where(content_items.c.id == "coach-1")
        ).scalar()
    assert retired is None


def test_app_startup_syncs_committed_content(harness: Harness):
    content = load_seed_content(CONTENT_DIR, load_pack(CONTENT_DIR / "packs", "neutral"))
    stored = count(harness.engine, "content_items")
    assert stored == len(seed_items(content))
    assert ContentRepository(harness.engine).get("cal:sound.sub.v.w:vest") is not None
    assert ContentRepository(harness.engine).get("ba-rq-05") is not None
