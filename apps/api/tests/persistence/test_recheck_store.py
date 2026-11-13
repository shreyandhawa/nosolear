from datetime import timedelta

from factories import NOW, TAX, entry, profile_of
from sqlalchemy import Engine, inspect

from nosolear.domain.profile import Profile
from nosolear.domain.rechecks import RecheckState
from nosolear.domain.status import Status
from nosolear.persistence.repositories import ProfileRepository, RecheckRepository
from nosolear.ports.plan import RecheckStore

KEY = "sound.sub.v.w"
STATE = RecheckState(stage=2, next_at=NOW + timedelta(days=8))


def mastered_profile(a: float = 2, b: float = 80) -> Profile:
    return profile_of([entry(KEY, a=a, b=b, status=Status.MASTERED)])


def test_save_then_load_roundtrip(db_engine: Engine) -> None:
    ProfileRepository(db_engine, TAX).save(mastered_profile(), session_id=None, reason="rebuild")
    store: RecheckStore = RecheckRepository(db_engine)
    store.save({KEY: STATE})
    assert store.load() == {KEY: STATE}


def test_save_clears_keys_missing_from_the_mapping(db_engine: Engine) -> None:
    ProfileRepository(db_engine, TAX).save(mastered_profile(), session_id=None, reason="rebuild")
    store = RecheckRepository(db_engine)
    store.save({KEY: STATE})
    store.save({})
    assert store.load() == {}


def test_profile_save_carries_schedule_for_still_mastered_keys(db_engine: Engine) -> None:
    profiles = ProfileRepository(db_engine, TAX)
    profiles.save(mastered_profile(), session_id=None, reason="rebuild")
    RecheckRepository(db_engine).save({KEY: STATE})
    rebuilt = mastered_profile(a=3, b=70)
    profiles.save(rebuilt, session_id=None, reason="rebuild")
    assert RecheckRepository(db_engine).load() == {KEY: STATE}
    assert profiles.latest() == rebuilt


def test_profile_replace_carries_schedule_for_still_mastered_keys(db_engine: Engine) -> None:
    profiles = ProfileRepository(db_engine, TAX)
    profiles.replace(mastered_profile())
    RecheckRepository(db_engine).save({KEY: STATE})
    profiles.replace(mastered_profile(a=3, b=70))
    assert RecheckRepository(db_engine).load() == {KEY: STATE}


def test_profile_save_drops_schedule_when_key_no_longer_mastered(db_engine: Engine) -> None:
    profiles = ProfileRepository(db_engine, TAX)
    profiles.save(mastered_profile(), session_id=None, reason="rebuild")
    RecheckRepository(db_engine).save({KEY: STATE})
    relapsed = profile_of([entry(KEY, a=40, b=60, status=Status.ACTIVE)])
    profiles.save(relapsed, session_id=None, reason="rebuild")
    assert RecheckRepository(db_engine).load() == {}


def test_schema_has_nullable_recheck_columns(db_engine: Engine) -> None:
    columns = {c["name"]: c for c in inspect(db_engine).get_columns("profile_entries")}
    assert columns["next_recheck_at"]["nullable"] is True
    assert columns["recheck_stage"]["nullable"] is True
