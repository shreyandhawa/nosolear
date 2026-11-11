import json
import re
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from factories import NPT, SAMPLE_OBS, T0, TAX, count, mk
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, StatementError

from nosolear.domain.observations import Context, Outcome
from nosolear.domain.profile import build_profile
from nosolear.domain.taxonomy import Detector
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository

MISS = Outcome.MISS


def test_observation_roundtrip_keeps_utc_and_evidence(db_engine: Engine) -> None:
    o = mk(
        "sound.sub.v.w",
        MISS,
        datetime(2026, 11, 12, 13, 45, tzinfo=NPT),
        evidence={"word": "vest", "start_ms": 120},
    )
    repo = ObservationRepository(db_engine)
    repo.add_many([o])
    (back,) = repo.all()
    assert back == o
    assert back.observed_at.utcoffset() == UTC.utcoffset(None)
    assert back.evidence == {"word": "vest", "start_ms": 120}


def test_observation_roundtrip_all_enums(db_engine: Engine) -> None:
    o = mk("fluency.filler", Outcome.OK, T0, Context.UNSCRIPTED, Detector.ASR_METRICS, 0.3)
    repo = ObservationRepository(db_engine)
    repo.add_many([o])
    assert repo.all() == [o]


def test_all_orders_by_observed_at_then_insertion(db_engine: Engine) -> None:
    late = mk("sound.sub.v.w", MISS, T0)
    early = mk("sound.sub.θ.t", MISS, T0.replace(day=1))
    tie = mk("sound.sub.v.w", Outcome.OK, T0)
    repo = ObservationRepository(db_engine)
    repo.add_many([late, tie, early])
    assert repo.all() == [early, late, tie]


def test_naive_datetime_is_rejected(db_engine: Engine) -> None:
    naive = replace(SAMPLE_OBS[0], observed_at=datetime(2026, 11, 12, 8, 0))
    with pytest.raises(StatementError, match="aware"):
        ObservationRepository(db_engine).add_many([naive])


def test_profile_save_and_latest_roundtrip(db_engine: Engine) -> None:
    p = build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX)
    repo = ProfileRepository(db_engine, TAX)
    repo.save(p, session_id=None, reason="rebuild")
    assert repo.latest() == p


def test_save_returns_hex_id_and_stores_snapshot(db_engine: Engine) -> None:
    p = build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX)
    snap_id = ProfileRepository(db_engine, TAX).save(p, session_id=None, reason="baseline")
    assert len(snap_id) == 32
    int(snap_id, 16)
    with db_engine.connect() as conn:
        row = conn.execute(text("SELECT reason, entries_json FROM profile_snapshots")).one()
    assert row.reason == "baseline"
    assert "sound.sub.v.w" in row.entries_json


def test_save_replaces_entries_and_appends_snapshot(db_engine: Engine) -> None:
    repo = ProfileRepository(db_engine, TAX)
    repo.save(build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX), session_id=None, reason="rebuild")
    p2 = build_profile(SAMPLE_OBS[:1], as_of=T0, taxonomy=TAX)
    assert len(p2.entries) < 3
    repo.save(p2, session_id=None, reason="rebuild")
    assert repo.latest() == p2
    assert count(db_engine, "profile_snapshots") == 2
    assert count(db_engine, "profile_entries") == len(p2.entries)


def test_latest_is_none_on_empty_db(db_engine: Engine) -> None:
    assert ProfileRepository(db_engine, TAX).latest() is None


def test_latest_is_none_after_saving_empty_profile(db_engine: Engine) -> None:
    repo = ProfileRepository(db_engine, TAX)
    repo.save(build_profile([], as_of=T0, taxonomy=TAX), session_id=None, reason="rebuild")
    assert count(db_engine, "profile_snapshots") == 1
    assert repo.latest() is None


def test_invalid_reason_is_rejected(db_engine: Engine) -> None:
    p = build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX)
    with pytest.raises(IntegrityError):
        ProfileRepository(db_engine, TAX).save(p, session_id=None, reason="nope")
    assert count(db_engine, "profile_entries") == 0


def test_snapshot_json_datetimes_use_the_stored_utc_format(db_engine: Engine) -> None:
    """Same fixed-width UTC text with microseconds as the UTCDateTime columns, offsets folded."""
    p = build_profile(SAMPLE_OBS, as_of=T0.astimezone(NPT), taxonomy=TAX)
    ProfileRepository(db_engine, TAX).save(p, session_id=None, reason="rebuild")
    with db_engine.connect() as conn:
        raw = conn.execute(text("SELECT entries_json FROM profile_snapshots")).scalar_one()
        stored = {
            r.error_key: r
            for r in conn.exec_driver_sql(
                "SELECT error_key, updated_at, last_seen_at FROM profile_entries"
            )
        }
    entries = json.loads(raw)
    assert len(entries) == len(stored) > 0
    for entry in entries:
        for field in ("updated_at", "last_seen_at"):
            assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00", entry[field])
            assert entry[field] == getattr(stored[entry["error_key"]], field)
