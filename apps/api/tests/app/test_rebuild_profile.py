from factories import NOW, PACK, SAMPLE_OBS, T0, TAX, FixedClock, count, mk
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


def test_rebuild_reads_only_current_observations(db_engine: Engine) -> None:
    # Attempt "a" was scored under v0 (a miss), then under a calibrated config (an ok).
    # The profile must count only the calibrated ok.
    from sqlalchemy import text

    from nosolear.domain.observations import Outcome
    from nosolear.domain.profile import build_profile
    from nosolear.domain.scoring import (
        CALIBRATED_THRESHOLDS,
        V0_CONFIG,
        ConfigKind,
        ScoringConfig,
    )
    from nosolear.domain.taxonomy import Detector
    from nosolear.persistence.scoring_repository import (
        ExtractionRepository,
        ScoringConfigRepository,
    )

    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sessions (id, kind, protocol_version, started_at) "
                "VALUES ('s', 'daily', 1, '2026-11-12T00:00:00.000000+00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO attempts (id, session_id, step, scripted, created_at) "
                "VALUES ('a', 's', 'speak', 1, '2026-11-12T00:00:00.000000+00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO calibration_runs (id, session_id, status, scoring_config_id, "
                "started_at, completed_at) VALUES ('r1', NULL, 'done', NULL, "
                "'2026-11-12T00:00:00.000000+00:00', NULL)"
            )
        )
    calibrated = ScoringConfig(
        id="c1",
        kind=ConfigKind.CALIBRATED,
        calibration_run_id="r1",
        thresholds=CALIBRATED_THRESHOLDS,
        family_rules=V0_CONFIG.family_rules,
        key_rules=(),
    )
    ScoringConfigRepository(db_engine, TAX).add(calibrated, capabilities={}, created_at=T0)
    miss = mk("sound.sub.v.w", Outcome.MISS, NOW, attempt_id="a")
    ok = mk("sound.sub.v.w", Outcome.OK, NOW, attempt_id="a", scoring_config_id="c1")
    ex = ExtractionRepository(db_engine)
    ex.write(
        attempt_id="a",
        scoring_config_id="v0",
        detector=Detector.AZURE_PA,
        observations=[miss],
        created_at=T0,
    )
    ex.write(
        attempt_id="a",
        scoring_config_id="c1",
        detector=Detector.AZURE_PA,
        observations=[ok],
        created_at=T0,
    )

    rebuilt = rebuild_profile(
        observations=ObservationRepository(db_engine),
        profiles=ProfileRepository(db_engine, TAX),
        taxonomy=TAX,
        pack=PACK,
        clock=FixedClock(NOW),
    )
    expected = build_profile([ok], as_of=NOW, taxonomy=TAX, pack=PACK)
    assert rebuilt == expected
