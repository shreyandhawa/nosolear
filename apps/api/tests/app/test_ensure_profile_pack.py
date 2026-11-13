from factories import NEPALI, NEUTRAL, NOW, SAMPLE_OBS, TAX, FixedClock, count
from fakes import FakeProfileStore
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


def test_fake_profile_store_stored_under_other_pack_is_rebuilt_once(db_engine: Engine) -> None:
    ObservationRepository(db_engine).add_many(SAMPLE_OBS)
    store = FakeProfileStore(stored_pack_id="nepali")
    observations = ObservationRepository(db_engine)
    clock = FixedClock(NOW)

    def ensure() -> bool:
        return ensure_profile_pack(
            observations=observations, profiles=store, taxonomy=TAX, pack=NEUTRAL, clock=clock
        )

    assert ensure() is True
    assert [(profile.pack_id, reason) for profile, _, reason in store.saved] == [
        ("neutral", "rebuild")
    ]
    assert ensure() is False
    assert len(store.saved) == 1
