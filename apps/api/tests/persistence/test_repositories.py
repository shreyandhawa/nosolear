import json
import re
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from factories import NEUTRAL, NPT, PACK, SAMPLE_OBS, T0, TAX, FixedClock, count, mk
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, StatementError

from nosolear.domain.analyses import AnalysisKind, NewAnalysis
from nosolear.domain.observations import Context, Outcome
from nosolear.domain.profile import build_profile
from nosolear.domain.taxonomy import Detector
from nosolear.persistence.models import format_utc
from nosolear.persistence.repositories import (
    AnalysisRepository,
    ObservationRepository,
    ProfileRepository,
)

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
    p = build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX, pack=PACK)
    repo = ProfileRepository(db_engine, TAX)
    repo.save(p, session_id=None, reason="rebuild")
    assert repo.latest() == p


def test_save_returns_hex_id_and_stores_snapshot(db_engine: Engine) -> None:
    p = build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX, pack=PACK)
    snap_id = ProfileRepository(db_engine, TAX).save(p, session_id=None, reason="baseline")
    assert len(snap_id) == 32
    int(snap_id, 16)
    with db_engine.connect() as conn:
        row = conn.execute(text("SELECT reason, entries_json FROM profile_snapshots")).one()
    assert row.reason == "baseline"
    assert "sound.sub.v.w" in row.entries_json


def test_save_replaces_entries_and_appends_snapshot(db_engine: Engine) -> None:
    repo = ProfileRepository(db_engine, TAX)
    repo.save(
        build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX, pack=PACK),
        session_id=None,
        reason="rebuild",
    )
    p2 = build_profile(SAMPLE_OBS[:1], as_of=T0, taxonomy=TAX, pack=PACK)
    assert len(p2.entries) < 3
    repo.save(p2, session_id=None, reason="rebuild")
    assert repo.latest() == p2
    assert count(db_engine, "profile_snapshots") == 2
    assert count(db_engine, "profile_entries") == len(p2.entries)


def test_latest_is_none_on_empty_db(db_engine: Engine) -> None:
    assert ProfileRepository(db_engine, TAX).latest() is None


def test_latest_is_none_after_saving_empty_profile(db_engine: Engine) -> None:
    repo = ProfileRepository(db_engine, TAX)
    repo.save(
        build_profile([], as_of=T0, taxonomy=TAX, pack=PACK), session_id=None, reason="rebuild"
    )
    assert count(db_engine, "profile_snapshots") == 1
    assert repo.latest() is None


def test_invalid_reason_is_rejected(db_engine: Engine) -> None:
    p = build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX, pack=PACK)
    with pytest.raises(IntegrityError):
        ProfileRepository(db_engine, TAX).save(p, session_id=None, reason="nope")
    assert count(db_engine, "profile_entries") == 0


def test_snapshot_json_datetimes_use_the_stored_utc_format(db_engine: Engine) -> None:
    """Same fixed-width UTC text with microseconds as the UTCDateTime columns, offsets folded."""
    p = build_profile(SAMPLE_OBS, as_of=T0.astimezone(NPT), taxonomy=TAX, pack=PACK)
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


def test_pack_id_roundtrips_and_is_stored_on_the_snapshot(db_engine: Engine) -> None:
    repo = ProfileRepository(db_engine, TAX)
    assert repo.latest_pack_id() is None
    p = build_profile(SAMPLE_OBS, as_of=T0, taxonomy=TAX, pack=NEUTRAL)
    repo.save(p, session_id=None, reason="rebuild")
    assert repo.latest_pack_id() == "neutral"
    latest = repo.latest()
    assert latest is not None and latest.pack_id == "neutral"
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT pack_id FROM profile_snapshots")).scalar_one() == "neutral"


# ---- analyses ------------------------------------------------------------------------------

ATTEMPT = "attempt-1"


def _insert_attempt(engine: Engine, attempt_id: str) -> None:
    """An attempt row, so analyses can reference it through the foreign key."""
    stamp = format_utc(T0)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT OR IGNORE INTO sessions (id, kind, protocol_version, started_at, "
                "completed_at) VALUES ('session-1', 'daily', 1, :stamp, NULL)"
            ),
            {"stamp": stamp},
        )
        conn.execute(
            text(
                "INSERT INTO attempts (id, session_id, step, reference_text, scripted, "
                "created_at) VALUES (:id, 'session-1', 'speak', NULL, 1, :stamp)"
            ),
            {"id": attempt_id, "stamp": stamp},
        )


def _new(kind: AnalysisKind, attempt_id: str = ATTEMPT, **raw: object) -> NewAnalysis:
    return NewAnalysis(
        attempt_id=attempt_id,
        kind=kind,
        provider="azure",
        provider_version="2026-01",
        adapter="azure_pa",
        adapter_version=1,
        raw=raw or {"score": 82.5, "words": ["vest", "west"]},
    )


def test_analysis_put_then_get_round_trips_raw(db_engine: Engine) -> None:
    _insert_attempt(db_engine, ATTEMPT)
    repo = AnalysisRepository(db_engine, FixedClock(T0))
    stored = repo.put(_new(AnalysisKind.PRONUNCIATION))
    assert stored.raw == {"score": 82.5, "words": ["vest", "west"]}
    assert repo.get(ATTEMPT, AnalysisKind.PRONUNCIATION) == stored
    assert stored.created_at == T0


def test_analysis_put_is_idempotent(db_engine: Engine) -> None:
    _insert_attempt(db_engine, ATTEMPT)
    repo = AnalysisRepository(db_engine, FixedClock(T0))
    first = repo.put(_new(AnalysisKind.TRANSCRIPT, score=1))
    second = repo.put(_new(AnalysisKind.TRANSCRIPT, score=2))
    assert second == first
    assert second.raw == {"score": 1}
    assert count(db_engine, "analyses") == 1


def test_analysis_for_attempt_lists_all_kinds(db_engine: Engine) -> None:
    _insert_attempt(db_engine, ATTEMPT)
    repo = AnalysisRepository(db_engine, FixedClock(T0))
    for kind in AnalysisKind:
        repo.put(_new(kind))
    assert sorted(a.kind for a in repo.for_attempt(ATTEMPT)) == sorted(AnalysisKind)
    assert repo.get("missing", AnalysisKind.COACH) is None


def test_analysis_for_unknown_attempt_raises_integrity_error(db_engine: Engine) -> None:
    repo = AnalysisRepository(db_engine, FixedClock(T0))
    with pytest.raises(IntegrityError):
        repo.put(_new(AnalysisKind.COACH, attempt_id="no-such-attempt"))


def _seed_attempt(engine: Engine, attempt_id: str = "a") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sessions (id, kind, protocol_version, started_at) "
                "VALUES ('s', 'daily', 1, '2026-11-12T00:00:00.000000+00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO attempts (id, session_id, step, scripted, created_at) "
                "VALUES (:id, 's', 'speak', 1, '2026-11-12T00:00:00.000000+00:00')"
            ),
            {"id": attempt_id},
        )


def test_observation_roundtrip_keeps_config_and_provisional(db_engine: Engine) -> None:
    _seed_attempt(db_engine)
    o = mk(
        "sound.sub.f.p",
        MISS,
        T0,
        attempt_id="a",
        scoring_config_id="v0",
        provisional=True,
    )
    ObservationRepository(db_engine).add_many([o])
    [stored] = ObservationRepository(db_engine).all()
    assert stored.scoring_config_id == "v0"
    assert stored.provisional is True
    assert stored == o


def test_profile_roundtrip_keeps_provisional(db_engine: Engine) -> None:
    obs = [
        mk("sound.sub.f.p", MISS, T0, provisional=True),
        mk("fluency.filler", MISS, T0, detector=Detector.ASR_METRICS),
    ]
    profile = build_profile(obs, as_of=T0, taxonomy=TAX, pack=PACK)
    repo = ProfileRepository(db_engine, TAX)
    snapshot_id = repo.save(profile, session_id=None, reason="rebuild")
    latest = repo.latest()
    assert latest == profile
    assert latest is not None
    assert {e.definition.key: e.provisional for e in latest.entries} == {
        "sound.sub.f.p": True,
        "fluency.filler": False,
    }
    with db_engine.connect() as conn:
        entries_json = conn.execute(
            text("SELECT entries_json FROM profile_snapshots WHERE id = :id"), {"id": snapshot_id}
        ).scalar_one()
    assert all("provisional" in entry for entry in json.loads(entries_json))


def _two_sessions(engine: Engine) -> None:
    stamp = format_utc(T0)
    with engine.begin() as conn:
        for session_id in ("s-one", "s-two"):
            conn.execute(
                text(
                    "INSERT INTO sessions (id, kind, protocol_version, started_at) "
                    "VALUES (:id, 'daily', 1, :stamp)"
                ),
                {"id": session_id, "stamp": stamp},
            )
        for attempt_id, session_id in (("a-one", "s-one"), ("a-two", "s-two")):
            conn.execute(
                text(
                    "INSERT INTO attempts (id, session_id, step, scripted, created_at) "
                    "VALUES (:id, :session, 'speak', 1, :stamp)"
                ),
                {"id": attempt_id, "session": session_id, "stamp": stamp},
            )


def test_for_session_only_returns_that_sessions_observations_with_ids(db_engine: Engine) -> None:
    _two_sessions(db_engine)
    late = mk("sound.sub.v.w", MISS, T0.replace(hour=9), attempt_id="a-one", evidence={"w": "late"})
    early = mk("sound.sub.θ.t", MISS, T0, attempt_id="a-one", evidence={"w": "early"})
    other = mk("sound.sub.v.w", MISS, T0, attempt_id="a-two", evidence={"w": "other"})
    repo = ObservationRepository(db_engine)
    repo.add_many([late, other, early])
    with db_engine.connect() as conn:
        rows = conn.execute(text("SELECT id, evidence_json FROM observations")).all()
    id_of = {json.loads(evidence)["w"]: row_id for row_id, evidence in rows}
    found = repo.for_session("s-one")
    assert [s.observation for s in found] == [early, late]
    assert [s.id for s in found] == [id_of["early"], id_of["late"]]
    assert repo.for_session("nobody") == []
