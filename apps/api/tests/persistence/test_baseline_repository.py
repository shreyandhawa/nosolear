"""The baseline repository: sessions, protocol attempts, scores, and profile snapshots."""

from datetime import UTC, datetime, timedelta

import pytest
from baseline_fixtures import PROTOCOL
from calibration_fixtures import SMALL_SET
from factories import PACK, count, mk
from sqlalchemy import Engine, text

from nosolear.domain.content import seed_items
from nosolear.domain.observations import Outcome
from nosolear.domain.profile import build_profile
from nosolear.domain.skill_scores import SkillScore
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX
from nosolear.domain.taxonomy import Skill
from nosolear.persistence.baseline_repository import BaselineRepository
from nosolear.persistence.content_repository import ContentRepository
from nosolear.persistence.repositories import ProfileRepository

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


@pytest.fixture
def store(db_engine: Engine) -> BaselineRepository:
    from nosolear.domain.content import SeedContent

    ContentRepository(db_engine).sync_seed(seed_items(SeedContent(SMALL_SET, PROTOCOL)), now=NOW)
    return BaselineRepository(db_engine)


def test_create_writes_one_attempt_per_protocol_item_in_order(
    store: BaselineRepository, db_engine: Engine
) -> None:
    store.create(session_id="s1", protocol=PROTOCOL, now=NOW)
    items = store.items("s1")
    assert [i.item_id for i in items] == [
        "bl:read:1",
        "bl:read:2",
        "bl:word:1",
        "bl:free:1",
        "bl:rapid:1",
        "bl:art:1",
    ]
    assert [i.order for i in items] == list(range(6))
    assert [i.scripted for i in items] == [True, True, True, False, False, False]
    assert [i.step for i in items] == [
        "read_aloud",
        "read_aloud",
        "word_list",
        "speak",
        "quick_answer",
        "articulate",
    ]
    with db_engine.connect() as conn:
        kinds = conn.execute(text("SELECT kind, protocol_version FROM sessions")).one()
        refs = conn.execute(
            text("SELECT reference_text FROM attempts ORDER BY created_at LIMIT 4")
        ).all()
    assert tuple(kinds) == ("baseline", 1)
    assert [r.reference_text for r in refs] == [
        "Seven vans came.",
        "Five fine fans.",
        "vest",
        None,
    ]


def test_open_then_completed(store: BaselineRepository) -> None:
    store.create(session_id="s1", protocol=PROTOCOL, now=NOW)
    open_session = store.open_session()
    assert open_session is not None and open_session.id == "s1"
    assert open_session.completed_at is None
    assert store.latest_completed() is None
    done_at = NOW + timedelta(minutes=20)
    store.complete("s1", completed_at=done_at)
    assert store.open_session() is None
    latest = store.latest_completed()
    assert latest is not None and latest.completed_at == done_at
    assert [s.id for s in store.completed_sessions()] == ["s1"]


def test_items_report_recorded_and_job_status(store: BaselineRepository) -> None:
    store.create(session_id="s1", protocol=PROTOCOL, now=NOW)
    items = store.items("s1")
    assert all(not i.recorded and i.job_status is None for i in items)


def _score(skill: Skill, value: float) -> SkillScore:
    return SkillScore(skill=skill, score=value, values={"x": 1.0}, scores={"x": value})


def test_save_scores_upserts_and_reads_back_in_skill_order(store: BaselineRepository) -> None:
    store.create(session_id="s1", protocol=PROTOCOL, now=NOW)
    store.save_scores("s1", [_score(Skill.ARTICULATE, 75.0), _score(Skill.SOUNDS, 60.0)])
    store.save_scores("s1", [_score(Skill.SOUNDS, 80.0)])
    scores = store.scores("s1")
    assert [(s.skill, s.score) for s in scores] == [
        (Skill.SOUNDS, 80.0),
        (Skill.ARTICULATE, 75.0),
    ]
    assert scores[0].values == {"x": 1.0} and scores[0].scores == {"x": 80.0}


def test_profile_snapshot_appends_without_touching_entries(
    store: BaselineRepository, db_engine: Engine
) -> None:
    profiles = ProfileRepository(db_engine, TAX)
    store.create(session_id="s1", protocol=PROTOCOL, now=NOW)
    current = build_profile(
        [mk("sound.sub.v.w", Outcome.MISS, NOW)], as_of=NOW, taxonomy=TAX, pack=PACK
    )
    profiles.replace(current)
    before = count(db_engine, "profile_entries")
    snapshot_id = profiles.snapshot(current, session_id="s1", reason="baseline")
    assert count(db_engine, "profile_entries") == before
    assert count(db_engine, "profile_snapshots") == 1
    found = profiles.latest_snapshot("s1", "baseline")
    assert found is not None
    found_id, restored = found
    assert found_id == snapshot_id
    assert [e.definition.key for e in restored.entries] == ["sound.sub.v.w"]
    assert restored.entries[0].estimate == current.entries[0].estimate
    assert restored.pack_id == PACK.id and restored.as_of == NOW


def test_latest_snapshot_is_none_without_one(db_engine: Engine, store: BaselineRepository) -> None:
    store.create(session_id="s1", protocol=PROTOCOL, now=NOW)
    assert ProfileRepository(db_engine, TAX).latest_snapshot("s1", "baseline") is None
