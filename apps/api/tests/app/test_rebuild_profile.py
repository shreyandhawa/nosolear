from factories import NOW, PACK, SAMPLE_OBS, TAX, FixedClock, count
from sqlalchemy import Engine

from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository


def test_rebuild_uses_clock_and_saves_snapshot(db_engine: Engine) -> None:
    obs_repo = ObservationRepository(db_engine)
    obs_repo.add_many(SAMPLE_OBS)
    prof_repo = ProfileRepository(db_engine, TAX)
    p = rebuild_profile(
        observations=obs_repo, profiles=prof_repo, taxonomy=TAX, pack=PACK, clock=FixedClock(NOW)
    )
    assert p.as_of == NOW
    assert prof_repo.latest() == p
    assert count(db_engine, "profile_snapshots") == 1


def test_rebuild_with_no_observations(db_engine: Engine) -> None:
    p = rebuild_profile(
        observations=ObservationRepository(db_engine),
        profiles=ProfileRepository(db_engine, TAX),
        taxonomy=TAX,
        pack=PACK,
        clock=FixedClock(NOW),
    )
    assert p.entries == ()
