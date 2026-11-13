import pytest
from factories import T0, TAX, count, mk
from sqlalchemy import Engine, text

from nosolear.domain.observations import Outcome
from nosolear.domain.scoring import (
    CALIBRATED_THRESHOLDS,
    V0_CONFIG,
    ConfigKind,
    KeyRule,
    ScoringConfig,
    TrialCounts,
)
from nosolear.domain.taxonomy import Detector
from nosolear.persistence.repositories import ObservationRepository
from nosolear.persistence.scoring_repository import ExtractionRepository, ScoringConfigRepository

MISS, OK = Outcome.MISS, Outcome.OK
TS = "2026-11-12T00:00:00.000000+00:00"
COUNTS = TrialCounts(
    errors=10, hits=8, controls=10, false_alarms=1, correct_takes=4, correct_flags=0
)
CAL_CONFIG = ScoringConfig(
    id="c1",
    kind=ConfigKind.CALIBRATED,
    calibration_run_id="r1",
    thresholds=CALIBRATED_THRESHOLDS,
    family_rules=V0_CONFIG.family_rules,
    key_rules=(KeyRule(Detector.AZURE_PA, "sound.sub.v.w", True, CALIBRATED_THRESHOLDS, COUNTS),),
)


def _seed_attempt(engine: Engine, attempt_id: str = "a") -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO sessions (id, kind, protocol_version, started_at) "
                f"VALUES ('s', 'daily', 1, '{TS}')"
            )
        )
        c.execute(
            text(
                "INSERT INTO attempts (id, session_id, step, scripted, created_at) "
                f"VALUES (:id, 's', 'speak', 1, '{TS}')"
            ),
            {"id": attempt_id},
        )


def _seed_run(engine: Engine, run_id: str = "r1") -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO calibration_runs (id, session_id, status, scoring_config_id, "
                f"started_at, completed_at) VALUES (:id, NULL, 'done', NULL, '{TS}', NULL)"
            ),
            {"id": run_id},
        )


def test_v0_is_oldest_and_newest_until_calibrated(db_engine: Engine) -> None:
    repo = ScoringConfigRepository(db_engine, TAX)
    assert repo.newest() == V0_CONFIG
    assert repo.order() == ["v0"]
    _seed_run(db_engine)
    repo.add(CAL_CONFIG, capabilities={"azure_pa": {"nbest_phonemes": True}}, created_at=T0)
    assert repo.newest() == CAL_CONFIG
    assert repo.order() == ["v0", CAL_CONFIG.id]
    assert repo.get(CAL_CONFIG.id) == CAL_CONFIG


def test_write_is_once_per_attempt_config_and_detector(db_engine: Engine) -> None:
    _seed_attempt(db_engine)
    ex = ExtractionRepository(db_engine)
    obs = mk("sound.sub.v.w", MISS, T0, attempt_id="a")
    args = {"attempt_id": "a", "scoring_config_id": "v0", "detector": Detector.AZURE_PA}
    assert ex.write(**args, observations=[obs], created_at=T0)
    assert not ex.write(**args, observations=[obs], created_at=T0)
    assert count(db_engine, "observations") == 1


def test_write_rejects_observations_that_do_not_match_the_marker(db_engine: Engine) -> None:
    _seed_attempt(db_engine)
    ex = ExtractionRepository(db_engine)
    stray = mk("sound.sub.v.w", MISS, T0, attempt_id="other")
    with pytest.raises(ValueError):
        ex.write(
            attempt_id="a",
            scoring_config_id="v0",
            detector=Detector.AZURE_PA,
            observations=[stray],
            created_at=T0,
        )
    assert count(db_engine, "extractions") == 0


def test_current_drops_older_config_even_when_newer_wrote_nothing(db_engine: Engine) -> None:
    _seed_attempt(db_engine)
    _seed_run(db_engine)
    ex = ExtractionRepository(db_engine)
    obs_v0 = mk("sound.sub.v.w", MISS, T0, attempt_id="a")
    ex.write(
        attempt_id="a",
        scoring_config_id="v0",
        detector=Detector.AZURE_PA,
        observations=[obs_v0],
        created_at=T0,
    )
    ScoringConfigRepository(db_engine, TAX).add(CAL_CONFIG, capabilities={}, created_at=T0)
    ex.write(
        attempt_id="a",
        scoring_config_id=CAL_CONFIG.id,
        detector=Detector.AZURE_PA,
        observations=[],
        created_at=T0,
    )
    assert ObservationRepository(db_engine).current() == []
    assert len(ObservationRepository(db_engine).all()) == 1  # append-only: nothing deleted


def test_current_keeps_the_newer_config_observations(db_engine: Engine) -> None:
    _seed_attempt(db_engine)
    _seed_run(db_engine)
    ex = ExtractionRepository(db_engine)
    ex.write(
        attempt_id="a",
        scoring_config_id="v0",
        detector=Detector.AZURE_PA,
        observations=[mk("sound.sub.v.w", MISS, T0, attempt_id="a")],
        created_at=T0,
    )
    ScoringConfigRepository(db_engine, TAX).add(CAL_CONFIG, capabilities={}, created_at=T0)
    newer = mk("sound.sub.v.w", OK, T0, attempt_id="a", scoring_config_id=CAL_CONFIG.id)
    ex.write(
        attempt_id="a",
        scoring_config_id=CAL_CONFIG.id,
        detector=Detector.AZURE_PA,
        observations=[newer],
        created_at=T0,
    )
    assert ObservationRepository(db_engine).current() == [newer]


def test_scored_lists_every_marker(db_engine: Engine) -> None:
    _seed_attempt(db_engine)
    ExtractionRepository(db_engine).write(
        attempt_id="a",
        scoring_config_id="v0",
        detector=Detector.COACH,
        observations=[],
        created_at=T0,
    )
    assert ExtractionRepository(db_engine).scored() == [("a", "v0")]
