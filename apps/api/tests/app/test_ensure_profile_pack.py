from factories import NEPALI, NEUTRAL, NOW, SAMPLE_OBS, TAX, FixedClock, count
from sqlalchemy import Engine

from nosolear.app.ensure_profile_pack import ensure_profile_pack
from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.domain.packs import LanguagePack
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository


def _ensure(engine: Engine, pack: LanguagePack) -> bool:
    return ensure_profile_pack(
        observations=ObservationRepository(engine),
        profiles=ProfileRepository(engine, TAX),
        taxonomy=TAX,
        pack=pack,
        clock=FixedClock(NOW),
    )


def _build_under(engine: Engine, pack: LanguagePack) -> None:
    rebuild_profile(
        observations=ObservationRepository(engine),
        profiles=ProfileRepository(engine, TAX),
        taxonomy=TAX,
        pack=pack,
        clock=FixedClock(NOW),
    )


def test_no_profile_yet_writes_nothing(db_engine: Engine) -> None:
    assert _ensure(db_engine, NEUTRAL) is False
    assert count(db_engine, "profile_snapshots") == 0


def test_same_pack_does_nothing(db_engine: Engine) -> None:
    ObservationRepository(db_engine).add_many(SAMPLE_OBS)
    _build_under(db_engine, NEPALI)
    assert _ensure(db_engine, NEPALI) is False
    assert count(db_engine, "profile_snapshots") == 1


def test_different_pack_rebuilds(db_engine: Engine) -> None:
    ObservationRepository(db_engine).add_many(SAMPLE_OBS)
    _build_under(db_engine, NEPALI)
    assert _ensure(db_engine, NEUTRAL) is True
    assert count(db_engine, "profile_snapshots") == 2
    latest = ProfileRepository(db_engine, TAX).latest()
    assert latest is not None and latest.pack_id == "neutral"
